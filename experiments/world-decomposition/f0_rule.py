"""Rule F0 (accent.py) against the JVS women at forced-aligned vowel centres, and how much of the gap
Fujisaki parameters and accent types can close when fitted to the mean contour (in-sample).

    ALIGN=<align.pkl> python f0_rule.py
"""
from factor import *
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
plt.rcParams["font.family"]=["Hiragino Sans"]
al=pickle.load(open(os.environ["ALIGN"],"rb"))["align"]
names=sorted({n for n,_ in al}); c0=lambda v:v-np.nanmean(v)
fig,ax=plt.subplots(4,1,figsize=(15,15)); D=[]
for a,u in zip(ax,UTT):
    t=SENTENCES[u]; units=accent.parse(t); segs,spans=accent.to_segments(units); ph,ac=accent.commands(units,spans,accent.Fujisaki())
    moras=[(m,sp) for m,sp in zip(units,spans) if isinstance(m,accent.Mora)]
    # vowel of each mora: rule F0 at the last 60 % of the mora, and the HMM vowel centre in the recordings
    R=12*np.log2(accent.f0_curve(np.array([sp[0]+.65*(sp[1]-sp[0]) for _,sp in moras]),ph,ac,accent.Fujisaki())/100)
    P=[]
    for n in names:
        if (n,u) not in al: continue
        p=[q for q in al[n,u] if q[0]!="sil"]; k=0; y=[]
        x=load_jvs(n,[u]).get(u)
        f=clean_f0(analyse(x)["f0"])
        for m,_ in moras:
            k+=1 if m.consonant else 0
            q=p[k]; k+=1
            y.append(12*np.log2(f[min(int((q[1]+q[2])/2*200),len(f)-1)]/100))
        assert k==len(p); P.append(c0(np.array(y)))
    P=np.array(P); J=P.mean(0); R=c0(R); x=np.arange(len(R))
    d=lambda v:v-np.polyval(np.polyfit(x,v,1),x)
    lc=lambda A,B:{l:round(np.corrcoef(A[max(0,l):len(A)+min(0,l)],B[max(0,-l):len(B)+min(0,-l)])[0,1],2) for l in(-2,-1,0,1,2)}
    ind=[np.corrcoef(p,(J*len(P)-p)/(len(P)-1))[0,1] for p in P]
    print(u,len(P),"corr rule-mean",round(np.corrcoef(R,J)[0,1],2),"detr",round(np.corrcoef(d(R),d(J))[0,1],2),"speaker-vs-rest mean",round(np.mean(ind),2),"min",round(min(ind),2),"| sd rule",round(R.std(),2),"mean-of-51",round(J.std(),2),"indiv",round(P.std(1).mean(),2),"lag",lc(R,J))
    a.fill_between(x,*np.percentile(P,[10,90],0),color="#2a78d6",alpha=.2,lw=0,label="10〜90%")
    a.plot(x,J,color="#2a78d6",lw=2.5,label="JVS女性の平均"); a.plot(x,R,"k",lw=2,label="rule")
    D.append((u,units,spans,moras,J))
    prev=None; lab=[]
    for m,_ in moras:
        lab.append((m.consonant or "")+(m.vowel)+("" if m.phrase_id==prev else "\n%d(%d)"%(m.phrase_id,m.accent_type))); prev=m.phrase_id
    a.set_xticks(x); a.set_xticklabels(lab,fontsize=7); a.set_title(u+" "+t); a.grid(alpha=.3); a.legend(fontsize=8)

fig.tight_layout(); fig.savefig(HERE/"results/f0-rule.png",dpi=90)
from scipy.optimize import minimize
F=accent.Fujisaki
def model(q,acc,ph_,u,units,spans,moras):
    p=F(ap_first=q[0],ap_next=q[1],aa=q[2],alpha=q[3],beta=q[4],lead=q[5])
    ph,ac=accent.commands(units,spans,p)
    return c0(12*np.log2(accent.f0_curve(np.array([sp[0]+.65*(sp[1]-sp[0]) for _,sp in moras]),ph,ac,p)/100))
q0=[.32,.22,.30,3.,20.,.05]
def loss(q): return sum(((model(q,0,0,*d[:4])-d[4])**2).sum() for d in D)/sum(len(d[4]) for d in D)
tot=sum((d[4]**2).sum() for d in D)/sum(len(d[4]) for d in D)
print("variance of mean F0",round(tot,2),"rule default rmse",round(loss(q0)**.5,2))
best=min((minimize(loss,np.array(q0)*np.random.default_rng(k).uniform(.6,1.4,6),method="Nelder-Mead",options=dict(maxiter=1500,maxfev=1500)) for k in range(6)),key=lambda r:r.fun)
print("fitted params, same accent labels",best.x.round(2),"rmse",round(best.fun**.5,2))
for d in D: print(d[0],"corr fitted",round(np.corrcoef(model(best.x,0,0,*d[:4]),d[4])[0,1],2))
# oracle upper bound of the label system: per-phrase accent type chosen to fit the mean (given fitted params)
import copy as cp
def relabel(d,q):
    u,units,spans,moras,J=d; units=cp.deepcopy(units); moras=[(a,b) for a,b in zip(units,spans) if isinstance(a,accent.Mora)]
    pids=sorted({m.phrase_id for m,_ in moras}); n={p:sum(m.phrase_id==p for m,_ in moras) for p in pids}
    err=lambda: ((model(q,0,0,u,units,spans,moras)-J)**2).mean()
    e=err(); ch=1
    while ch:
        ch=0
        for p in pids:
            old=next(m.accent_type for m,_ in moras if m.phrase_id==p)
            for t in range(n[p]+1):
                for m,_ in moras:
                    if m.phrase_id==p: m.accent_type=t
                e2=err()
                if e2<e-1e-6: e,best_t,ch=e2,t,1; old=t
            for m,_ in moras:
                if m.phrase_id==p: m.accent_type=old
    return (u,units,spans,moras,J),e
q=best.x; D2=D
for it in range(3):
    D2=[relabel(d,q)[0] for d in D2]
    D=D2
    r=min((minimize(loss,q*np.random.default_rng(k).uniform(.8,1.2,6),method="Nelder-Mead",options=dict(maxiter=1500,maxfev=1500)) for k in range(2)),key=lambda r:r.fun); q=r.x
print("labels refit too",q.round(2),"rmse",round(r.fun**.5,2))
for d in D2:
    print(d[0],"corr",round(np.corrcoef(model(q,0,0,*d[:4]),d[4])[0,1],2),[(m.phrase_id,m.accent_type) for m in {m.phrase_id:m for m,_ in d[3]}.values()])
