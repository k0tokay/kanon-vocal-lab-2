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
vowel, mode = sys.argv[1:]
folder = out/"integrated"
folder.mkdir(exist_ok=True)
if mode not in ("sensitive","insensitive") or vowel not in ("a","o"):
    raise ValueError("Expected a/o and sensitive/insensitive")
ref = shape(vowel)
ref[labels.index("VO")] = min(0,ref[labels.index("VO")])
span = high-low
# Work in the interior of a face, with room for the same bidirectional step.
active = np.array([j for j,k in enumerate(labels) if k not in ("TRX","TRY","VO")
                   and min(ref[j]-low[j],high[j]-ref[j]) > .052*span[j]])
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
for index in range(24):
    relative=(ref[active]-low[active])/span[active]+z
    mask=(relative>.027)&(relative<.973)
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
    accepted=False
    for step in (.02,.01,.005):
        trial=z+direction*step
        for _ in range(8):
            f,h,x=evaluate(trial)
            if max(abs(f-f0))<.001:break
            correction=np.linalg.pinv(jf)@(f-f0)
            if np.linalg.norm(correction)>.009:break
            trial[mask]-=.7*correction
            if max(abs(trial-z))>.026:break
        if max(abs(trial-z))>.026:continue
        f,h,x=evaluate(trial)
        if max(abs(f-f0))<.002 and min(area(x)[1])>.12:
            accepted=True
            break
    if not accepted:break
    length+=np.linalg.norm(trial-z)
    z=trial
    previous=direction
    path.append(dict(length=length,distance=np.linalg.norm(z),x=x.tolist(),
                     transfer_dB=np.sqrt(np.mean((h-h0)**2)),formant_error_percent=100*max(abs(np.exp(f-f0)-1))))
    if length>=.24:break
assert path
(folder/f"{vowel}-{mode}.json").write_text(json.dumps(path,indent=2)+"\n")
print(vowel,mode,len(path),{k:v for k,v in path[-1].items() if k!="x"},flush=True)
call("vtlClose")
