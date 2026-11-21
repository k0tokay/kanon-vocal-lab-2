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
report = {}
for vowel in ["a","o"]:
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
    def jacobian(step):
        columns=[]
        for delta in np.eye(len(active))*step:
            fp,hp,_=evaluate(delta)
            fm,hm,_=evaluate(-delta)
            columns.append(np.r_[fp-fm,hp-hm]/(2*step))
        return np.array(columns).T
    record = {"coordinates":[labels[j] for j in active],"reference_Hz":np.exp(f0).tolist(),"runs":[]}
    for eps in [.002,.004]:
        jac = jacobian(eps)
        jf,jh = jac[:3],jac[3:]
        _,s,vt=np.linalg.svd(jf,full_matrices=True)
        assert s[-1]>s[0]*1e-5
        basis=vt[3:].T
        _,hs,directions=np.linalg.svd(np.einsum("ij,jk->ik",jh,basis),full_matrices=False)
        run={"difference_step":eps,"formant_singular_values":s.tolist(),"directions":[]}
        for name,i in [("sensitive",0),("insensitive",-1)]:
            direction=basis@directions[i]
            direction*=np.sign(direction[np.argmax(abs(direction))])
            z=.045*direction
            for iteration in range(12):
                f,h,x=evaluate(z)
                if np.max(abs(f-f0))<.0002:break
                # Correct only in the local normal space; backtrack on actual error.
                correction=np.linalg.pinv(jf)@(f-f0)
                for shrink in [.8,.4,.2,.1]:
                    trial=z-shrink*correction
                    if np.linalg.norm(trial) < .052 and np.linalg.norm(evaluate(trial)[0]-f0)<np.linalg.norm(f-f0):
                        z=trial
                        break
                else:break
            f,h,x=evaluate(z)
            a0=area(x0)[1];a1=area(x)[1]
            run["directions"].append(dict(name=name,distance=np.linalg.norm(z),max_formant_percent=100*max(abs(np.exp(f-f0)-1)),
              transfer_rms_db=np.sqrt(np.mean((h-h0)**2)),area_section_rms_cm2=np.sqrt(np.mean((a1-a0)**2)),
              direction=direction.tolist(),corrected_coordinates=z.tolist()))
        record["runs"].append(run)
    report[vowel]=record
    for r in record["runs"]:
        print(vowel,len(active),r["difference_step"],[(v['name'],round(v['distance'],4),round(v['max_formant_percent'],3),round(v['transfer_rms_db'],4),round(v['area_section_rms_cm2'],4)) for v in r["directions"]],flush=True)
call("vtlClose")
(out/"level-set.json").write_text(json.dumps(report,indent=2)+"\n")
