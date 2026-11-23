"""Look for bottlenecks in the error band instead of asking whether it is connected.

Graph: the band's points (error <= --eps) joined by the checked edges of
paths.py whose interior stays within --cap. On the largest component, the
balanced Fiedler sweep finds the cut with the lowest conductance
(cut edges / smaller side's degree sum, both sides >= 20%). A thin neck gives a
conductance well below that of a band without one; the reference is the same
sweep on random subsets of a reference vowel's points of the same size (the
induced subgraph then has about the same mean degree).
"""
import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.linalg import eigh
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components, laplacian


def load(samples, eps, cap):
    data = np.load(samples)
    points = data["points"][data["errors"] <= eps]
    graph = np.load(samples.with_name(f"samples-edges-{eps}.npz"))
    edges = graph["edges"][graph["path_errors"] <= cap]
    n = len(points)
    A = coo_matrix((np.ones(len(edges)), (edges[:, 0], edges[:, 1])), shape=(n, n))
    return points, ((A+A.T) > 0).astype(float).toarray(), list(data["names"])


def giant(A):
    _, label = connected_components(A)
    return np.flatnonzero(label == np.argmax(np.bincount(label)))


def sweep(A, smallest=.2):
    """Lowest-conductance balanced cut along the Fiedler vector: (conductance, mask of one side)."""
    _, V = eigh(laplacian(A, normed=True), subset_by_index=[0, 1])
    degree = A.sum(1)
    order = np.argsort(V[:, 1]/np.sqrt(degree))
    side, best = np.zeros(len(A), bool), (np.inf, None)
    cut, volume, total = 0., 0., degree.sum()
    for t, k in enumerate(order[:-1]):
        cut += degree[k]-2*A[k, side].sum()
        side[k] = True
        volume += degree[k]
        if smallest*len(A) <= t+1 <= (1-smallest)*len(A):
            best = min(best, (cut/min(volume, total-volume), side.copy()), key=lambda b: b[0])
    return best


if __name__ == "__main__":
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser()
    parser.add_argument("samples", type=Path, nargs="?", default=here / "results/kanon-o/samples.npz")
    parser.add_argument("--reference", type=Path, default=here / "results/kanon-a/samples.npz")
    parser.add_argument("--eps", type=float, default=.01)
    parser.add_argument("--cap", type=float, default=.02, help="largest error inside an edge")
    parser.add_argument("--draws", type=int, default=20)
    args = parser.parse_args()

    X, A, names = load(args.samples, args.eps, args.cap)
    keep = giant(A)
    X, A = X[keep], A[np.ix_(keep, keep)]
    phi, side = sweep(A)
    print(f"{args.samples.parent.name}: points={len(keep)} mean degree={A.sum(1).mean():.1f} "
          f"cut edges={int(A[np.ix_(side, ~side)].sum())} sides={side.sum()}/{(~side).sum()} conductance={phi:.4f}")
    diff = X[side].mean(0)-X[~side].mean(0)
    for k in np.argsort(-abs(diff))[:5]:
        print(f"  {names[k]:4s} {X[side, k].mean():.2f} vs {X[~side, k].mean():.2f}")

    R, B, _ = load(args.reference, args.eps, args.cap)
    n = int(np.sum(np.load(args.samples)["errors"] <= args.eps))
    rng = np.random.default_rng(0)
    null = []
    for _ in range(args.draws):
        s = rng.choice(len(R), min(n, len(R)), replace=False)
        sub = B[np.ix_(s, s)]
        g = giant(sub)
        null.append((sweep(sub[np.ix_(g, g)])[0], sub[np.ix_(g, g)].sum(1).mean()))
    null = np.array(null)
    print(f"reference {args.reference.parent.name}, {args.draws} subsets of {n} points: mean degree {null[:, 1].mean():.1f}, "
          f"conductance median {np.median(null[:, 0]):.4f} range {null[:, 0].min():.4f}-{null[:, 0].max():.4f}")

    fig, axes = plt.subplots(1, 2, figsize=(10, 4), constrained_layout=True)
    a, b = names.index("JA"), names.index("LP")
    for mask, colour, label in ((side, "tab:orange", f"side A ({side.sum()})"), (~side, "tab:blue", f"side B ({(~side).sum()})")):
        axes[0].scatter(X[mask, a], X[mask, b], s=6, color=colour, label=label)
    i, j = np.nonzero(np.triu(A) * np.outer(side, ~side))
    for p, q in zip(i, j):
        axes[0].plot(X[[p, q], a], X[[p, q], b], color="k", lw=.6)
    axes[0].set(xlabel="JA (larger = jaw more closed)", ylabel="LP (larger = lips more protruded)",
                title="Lowest-conductance cut (black: cut edges)", xlim=(0, 1), ylim=(0, 1))
    axes[0].legend(fontsize=8)
    axes[1].hist(null[:, 0], bins=10, color="gray", label=f"{args.reference.parent.name}, random {n}-point subsets")
    axes[1].axvline(phi, color="tab:red", label=args.samples.parent.name)
    axes[1].set(xlabel="balanced cut conductance", ylabel="count", title="Conductance against a band without a neck")
    axes[1].legend(fontsize=8)
    fig.savefig(args.samples.parent / f"cluster-{args.eps}.png", dpi=160)
