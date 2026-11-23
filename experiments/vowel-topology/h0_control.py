"""Exact Rips H0 (MST edge lengths) of thin error bands against random
subsamples of thicker bands with the same number of points.
Usage: python3 h0_control.py results/h0-control.png"""
import sys, numpy as np
from scipy.sparse.csgraph import minimum_spanning_tree
from scipy.spatial.distance import pdist, squareform
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
def mst(X): return np.sort(minimum_spanning_tree(squareform(pdist(X))).data)[::-1]
rng=np.random.default_rng(0); r=np.linspace(0,1.3,400)
fig,axes=plt.subplots(2,2,figsize=(11,7),constrained_layout=True)
for row,v in enumerate("ao"):
    d=np.load(f"results/kanon-{v}/samples.npz"); P,E=d["points"],d["errors"]
    for col,eps in enumerate((.005,.01)):
        ax=axes[row,col]; X=P[E<=eps]; n=len(X); m=mst(X)
        print(f"/{v}/ eps<={eps} n={n} longest MST edges {np.round(m[:8],3)}")
        for ref,c in ((.02,"tab:green"),(.05,"tab:orange")):
            Y=P[E<=ref]; curves=[]; tops=[]
            for s in range(20):
                mm=mst(Y[rng.choice(len(Y),n,replace=False)]); tops.append(mm[:8])
                curves.append([1+(mm>x).sum() for x in r])
            curves=np.array(curves); ax.fill_between(r,curves.min(0),curves.max(0),color=c,alpha=.3,label=f"random {n} of error ≤ {ref} (20 draws)")
            print(f"    control <={ref}: longest MST edges, mean of 20 draws {np.round(np.mean(tops,0),3)}")
        ax.step(r,[1+(m>x).sum() for x in r],"k",where="post",label=f"error ≤ {eps}")
        ax.set(yscale="log",xlabel="r",ylabel="components",title=f"/{v}/ error ≤ {eps}, n={n}"); ax.legend(fontsize=7)
fig.savefig(sys.argv[1],dpi=130)
