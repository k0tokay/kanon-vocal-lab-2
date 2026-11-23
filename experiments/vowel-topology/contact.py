"""Where is each band point narrowest, and does that separate the clusters?

For the points of the band (error <= --eps) in the giant component of the
checked-edge graph, take the lowest-conductance cut of cluster.py and, for
every point, the narrowest centre-line cross-section before VTL's
tongue-side floor (area, position along the tract, midsagittal x/y).
The velum/uvula lies at x < 0 (behind the hard palate), the hard palate at
x > 0. Writes contact-<eps>.png and contact-<eps>.npz next to the samples.
"""
import argparse
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

here = Path(__file__).resolve().parent
sys.path.insert(0, str(here.parent / "vtlmap"))
import vtlmap as vm  # noqa: E402
import cluster  # noqa: E402
import sample  # noqa: E402
from sample import active, high, low  # noqa: E402

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("samples", type=Path)
    parser.add_argument("--eps", type=float, default=.01)
    parser.add_argument("--cap", type=float, default=.02)
    args = parser.parse_args()
    vowel = str(np.load(args.samples)["vowel"])
    base = sample.shape(vowel)

    X, A, names, seeds = cluster.load(args.samples, args.eps, args.cap)
    keep = cluster.giant(A)
    X, A = X[keep], A[np.ix_(keep, keep)]
    phi, side = cluster.sweep(A)

    tract = vm.Tract(sample.speaker)
    rows = []
    for z in X:
        x = base.copy()
        x[active] = low[active] + z * (high - low)[active]
        c = tract.constriction(x)
        rows.append([c["area"], c["pos"], c["x"], c["y"]])
    C = np.array(rows)
    ref = tract.constriction(base)
    np.savez(args.samples.with_name(f"contact-{args.eps}.npz"), points=X, side=side,
             constriction=C, columns=["area", "pos", "x", "y"], names=names, conductance=phi)

    print(f"{args.samples.parent.name}: {len(X)} points in the giant component, conductance {phi:.4f}, "
          f"sides {side.sum()}/{(~side).sum()}")
    print(f"  speaker shape: narrowest {ref['area']:.3f} cm² at x={ref['x']:.2f} y={ref['y']:.2f} ({ref['articulator']})")
    for label, m in (("side A", side), ("side B", ~side)):
        behind = np.mean(C[m, 2] < 0)
        print(f"  {label}: area median {np.median(C[m, 0]):.3f} cm², x median {np.median(C[m, 2]):.2f} cm, "
              f"behind the hard palate (x<0) {100 * behind:.0f}%")
    diff = X[side].mean(0) - X[~side].mean(0)
    for k in np.argsort(-abs(diff))[:5]:
        print(f"    {names[k]:4s} {X[side, k].mean():.2f} vs {X[~side, k].mean():.2f}")

    fig, axes = plt.subplots(1, 3, figsize=(14, 4), constrained_layout=True)
    for m, colour, label in ((side, "tab:orange", f"side A ({side.sum()})"), (~side, "tab:blue", f"side B ({(~side).sum()})")):
        axes[0].scatter(C[m, 2], C[m, 3], s=6, color=colour, label=label)
        axes[1].scatter(C[m, 1], C[m, 0], s=6, color=colour, label=label)
    axes[0].scatter([ref["x"]], [ref["y"]], marker="x", color="k", label=f"speaker /{vowel}/")
    axes[0].axvline(0, color="0.5", lw=.6)
    axes[0].set(xlabel="x [cm] (< 0: velum/uvula, > 0: hard palate)", ylabel="y [cm]",
                title="Midsagittal position of the narrowest section")
    axes[0].legend(fontsize=8)
    axes[1].axhline(.12, color="tab:red", lw=.8, label="contact limit 0.12 cm²")
    axes[1].set(xlabel="position along the tract [cm]", ylabel="area before the tongue-side floor [cm²]",
                title="Narrowest section")
    axes[1].legend(fontsize=8)
    a, b = names.index("TCX"), names.index("TCY")
    for m, colour in ((side, "tab:orange"), (~side, "tab:blue")):
        axes[2].scatter(X[m, a], X[m, b], s=6, color=colour)
    axes[2].set(xlabel="TCX (normalised)", ylabel="TCY (normalised)", title="Tongue body centre")
    fig.suptitle(f"{args.samples.parent.name}, error ≤ {args.eps}, lowest-conductance cut {phi:.4f}")
    fig.savefig(args.samples.with_name(f"contact-{args.eps}.png"), dpi=150)
