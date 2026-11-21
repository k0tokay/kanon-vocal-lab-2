"""Local formant-preserving directions. Run after the manual vowel experiment."""
import csv
import json
import os
from pathlib import Path

import numpy as np
from scipy.signal import find_peaks

repo = Path(__file__).resolve().parents[2]
os.environ["VTL_EXPERIMENT_SPEAKER"] = str(repo/"speakers/fulkhisa-kanon/fulkhisa-kanon-v0-8-vowel-variation.speaker")
from run import area, call, high, labels, low, out, rate, shape, spectrum

n = 4096
band = (np.arange(n//2)*rate/n >= 200) & (np.arange(n//2)*rate/n <= 8000)
rows = list(csv.DictReader((out/"manual/shapes.csv").open()))
import sys
vowel, mode = sys.argv[1:3]
long_path = "--long" in sys.argv[3:]
folder = out/("integrated-long" if long_path else "integrated")
folder.mkdir(exist_ok=True)
if mode not in ("sensitive","insensitive") or vowel not in ("a","o"):
    raise ValueError("Expected a/o and sensitive/insensitive")
ref = shape(vowel)
ref[labels.index("VO")] = min(0,ref[labels.index("VO")])
span = high-low
# Work in the interior of a face, with room for the same bidirectional step.
active = np.array([j for j,k in enumerate(labels) if k not in ("TRX","TRY","VO")
                   and (long_path or min(ref[j]-low[j],high[j]-ref[j]) > .052*span[j])])
origin = np.zeros(len(active))
expected = next(row for row in rows if row["vowel"]==vowel and row["stage"]=="reference")
anchors = np.array([float(expected[k]) for k in ("F1","F2","F3")])
def evaluate(z):
    x = ref.copy()
    x[active] += z*span[active]
    assert np.all(x[active]>=low[active]) and np.all(x[active]<=high[active])
    db = spectrum(x,n)
    peaks,_ = find_peaks(db)
    ids = np.array([peaks[np.argmin(abs(peaks*rate/n-a))] for a in anchors])
    l,m,r = db[ids-1],db[ids],db[ids+1]
    f = (ids+.5*(l-r)/(l-2*m+r))*rate/n
    assert np.all(abs(f/anchors-1)<.15) and np.all(np.diff(ids)>0)
    return np.log(f),db[band],x
f0,h0,x0 = evaluate(origin)

def jacobian(z, mask):
    columns=[]
    for delta in np.eye(len(z))[mask]*.003:
        fp,hp,_=evaluate(z+delta)
        fm,hm,_=evaluate(z-delta)
        columns.append(np.r_[fp-fm,hp-hm]/.006)
    return np.array(columns).T

z=origin.copy()
previous=None
path=[]
length=0.
checkpoint=folder/f"{vowel}-{mode}.json"
if long_path:
    # Continue the saved short path verbatim. Use a distant fitted solution
    # as a heading, so changing local singular vectors cannot just circle.
    path=json.loads((checkpoint if checkpoint.exists() else out/"integrated"/checkpoint.name).read_text())
    z=(np.asarray(path[-1]["x"])[active]-ref[active])/span[active]
    length=path[-1]["length"]
    table = out/"wide-starts"/f"{vowel}.csv"
    seed = "wide-spread"
    target=next(row for row in csv.DictReader(table.open()) if row["start"]==seed)
    # For /o/, the prior wide-spread shape violates our open-vowel area floor.
    # Redirect both continuations to the open, hand-fitted alternative after
    # their first extension; this rule also reproduces a fresh run.
    open_o=next(row for row in rows if row["vowel"]=="o" and row["stage"]=="fitted")
    heading=(np.array([float(target[labels[j]]) for j in active])-ref[active])/span[active]
for index in range(80 if long_path else 24):
    if long_path and (np.linalg.norm(z)>=.70 or length>=1.8):break
    relative=(ref[active]-low[active])/span[active]+z
    mask=(relative>.027)&(relative<.973)
    if long_path:
        # One-sided derivatives at box boundaries.
        columns=[]
        for j in range(len(z)):
            d=np.zeros_like(z);d[j]=.003
            plus=relative[j]<.997
            minus=relative[j]>.003
            fp,hp,_=evaluate(z+d if plus else z)
            fm,hm,_=evaluate(z-d if minus else z)
            columns.append(np.r_[fp-fm,hp-hm]/(.003*(int(plus)+int(minus))))
        jac=np.array(columns).T
        mask=np.ones(len(z),dtype=bool)
    else:
        jac=jacobian(z,mask)
    jf=jac[:3]
    _,singular,vt=np.linalg.svd(jf,full_matrices=True)
    assert singular[-1]>1e-5*singular[0] and sum(mask)>3
    basis=vt[3:].T
    _,_,right=np.linalg.svd(np.einsum("ij,jk->ik",jac[3:],basis),full_matrices=False)
    direction=np.zeros_like(z)
    direction[mask]=basis@right[0 if mode=="sensitive" else -1]
    sign=direction[np.argmax(abs(direction))] if previous is None else direction@previous
    if sign<0:direction=-direction
    if long_path:
        if vowel=="o" and mode=="sensitive" and length>=.30:
            heading=(np.array([float(open_o[labels[j]]) for j in active])-ref[active])/span[active]
        goal=heading-z
        outward=basis@(basis.T@goal)
        if np.linalg.norm(outward)<1e-7:break
        outward/=np.linalg.norm(outward)
        if direction@outward<0:direction=-direction
        direction=.7*outward+.3*direction
        direction/=np.linalg.norm(direction)
    accepted=False
    for step in ((.045,.025,.012,.006) if long_path else (.02,.01,.005)):
        limit=.065 if long_path else .026
        trial=z+direction*step
        if long_path:trial=np.clip(trial,-(relative-z),1-(relative-z))
        for _ in range(8):
            f,h,x=evaluate(trial)
            if max(abs(f-f0))<.001:break
            correction=np.linalg.pinv(jf)@(f-f0)
            if np.linalg.norm(correction)>(.04 if long_path else .009):break
            trial[mask]-=.7*correction
            if long_path:trial=np.clip(trial,-(relative-z),1-(relative-z))
            if max(abs(trial-z))>limit:break
        if max(abs(trial-z))>limit:continue
        f,h,x=evaluate(trial)
        if max(abs(f-f0))<(.006 if long_path else .002) and min(area(x)[1])>.12:
            accepted=True
            break
    if not accepted and long_path and vowel=="o" and mode=="sensitive":
        # A nearby peak/area boundary can defeat the single normal correction.
        # Fit a small guide step with a bounded local nonlinear correction.
        from scipy.optimize import least_squares
        for stride in (.045,.024):
            q=z+stride*(heading-z)/max(np.linalg.norm(heading-z),stride)
            lb=np.maximum(-(ref[active]-low[active])/span[active],q-.035)
            ub=np.minimum((high[active]-ref[active])/span[active],q+.035)
            def residual(v):
                f,h,x=evaluate(v)
                return np.r_[f-f0,.12*(v-q),max(0.,.125-min(area(x)[1]))]
            seed=np.clip(q,lb+1e-6,ub-1e-6)
            def deriv(v):
                r=residual(v)
                columns=[]
                for j in range(len(v)):
                    w=v.copy()
                    w[j]+=.001 if v[j]+.001<ub[j] else -.001
                    columns.append((residual(w)-r)/(w[j]-v[j]))
                return np.array(columns).T
            fit=least_squares(residual,seed,jac=deriv,bounds=(lb,ub),max_nfev=10)
            trial=fit.x
            f,h,x=evaluate(trial)
            if max(abs(f-f0))<.006 and min(area(x)[1])>.12 and np.linalg.norm(trial-heading)<np.linalg.norm(z-heading):
                accepted=True
                break
    if not accepted:break
    length+=np.linalg.norm(trial-z)
    z=trial
    previous=direction
    path.append(dict(length=length,distance=np.linalg.norm(z),x=x.tolist(),
                     transfer_dB=np.sqrt(np.mean((h-h0)**2)),formant_error_percent=100*max(abs(np.exp(f-f0)-1))))
    if long_path:
        temp=checkpoint.with_suffix(".tmp")
        temp.write_text(json.dumps(path,indent=2)+"\n")
        temp.replace(checkpoint)
        if np.linalg.norm(trial-origin-heading)<.025:break
    elif length>=.24:break
assert path
(folder/f"{vowel}-{mode}.json").write_text(json.dumps(path,indent=2)+"\n")
print(vowel,mode,len(path),{k:v for k,v in path[-1].items() if k!="x"},flush=True)
call("vtlClose")
