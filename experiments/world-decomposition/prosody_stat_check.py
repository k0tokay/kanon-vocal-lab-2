"""Leakage controls for prosody_stat.py (GBM).    python prosody_stat_check.py out/prosody-jvs.pkl texts.json"""
import sys,json,pickle,warnings; warnings.filterwarnings("ignore"); sys.path.insert(0,'.')
import numpy as np
from prosody_stat import *
from sklearn.ensemble import GradientBoostingRegressor
R=reference(pickle.load(open(sys.argv[1],'rb'))); T=json.load(open(sys.argv[2]))
X,Y,F={}, {}, {}
for u in sorted(R):
    m,f=features(T[u]["text"]); F[u]=(m,f); o,_=lev([KEY(*q) for q in R[u]["mora"]],[KEY(x.consonant,x.vowel) for x in m]); ix=[(a,b) for a,b in enumerate(o) if b is not None and R[u]["ok"][a]]
    X[u]=f[[b for _,b in ix]]; y=R[u]["mean"][[a for a,_ in ix]]; Y[u]=y-y.mean()
odd=[u for u in sorted(R) if int(u)%2]; even=[u for u in sorted(R) if int(u)%2==0]
G=lambda:GradientBoostingRegressor(n_estimators=300,max_depth=4,learning_rate=.05,subsample=.7,min_samples_leaf=8,random_state=0)
def corr(a,b): return np.corrcoef(a,b)[0,1]
def ev(g,sel=slice(None)): return corr(np.concatenate([g.predict(X[u])-g.predict(X[u]).mean() for u in even]),np.concatenate([Y[u] for u in even]))
tr=np.vstack([X[u] for u in odd]); ty=np.concatenate([Y[u] for u in odd])
print("as before",round(ev(G().fit(tr,ty)),3))
rng=np.random.default_rng(0); print("targets shuffled over moras",round(ev(G().fit(tr,rng.permutation(ty))),3))
# train on 25 women, test on the mean of the other 26, different sentences
A,B=np.arange(0,25),np.arange(25,51)
def half(u,w):
    o,_=lev([KEY(*q) for q in R[u]["mora"]],[KEY(x.consonant,x.vowel) for x in F[u][0]]); ix=[a for a,b in enumerate(o) if b is not None and R[u]["ok"][a]]
    w=w[w<len(R[u]["Y"])]; y=R[u]["Y"][w][:,ix].mean(0); return y-y.mean()
g=G().fit(tr,np.concatenate([half(u,A) for u in odd]))
print("train women 1-25 -> test women 26-51, other sentences",round(corr(np.concatenate([g.predict(X[u])-g.predict(X[u]).mean() for u in even]),np.concatenate([half(u,B) for u in even])),3))
# which feature groups matter
names=["k","L-k","L","type","heiban","k-nuc","after","isnuc","hl","hl-1","hl+1","min4","k1","k2","q","Q-q","inbr","nbr","nbr-","br","nb","b0","brest","bn","pos","acc","pvL","pvT","pvacc","nxL","nxT","voiced","cons"]+list("aiueoN")+["dev"]
imp=sorted(zip(g.feature_importances_,names),reverse=True)[:14]; print([(n,round(i,2)) for i,n in imp])
