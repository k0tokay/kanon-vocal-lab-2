"""Vietoris-Rips persistence of sampled /a/ shapes over articulatory distance.

Each formant-error band fixes the point set; the filtration parameter r is the
Euclidean distance in range-normalised parameters. Edges are not checked
acoustically, so the classes describe the sample, not the exact level set.
"""
import argparse
import csv
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from ripser import ripser

parser = argparse.ArgumentParser()
parser.add_argument("samples", type=Path, nargs="?", default=Path(__file__).resolve().parent / "results/kanon-a/samples.npz")
parser.add_argument("--tolerances", type=float, nargs="+", default=[.01, .02, .05])
parser.add_argument("--maxdim", type=int, default=2)
args = parser.parse_args()
data = np.load(args.samples)
points, errors = data["points"], data["errors"]
out = args.samples.parent

results = {}
for tolerance in args.tolerances:
    cloud = points[errors <= tolerance]
    if len(cloud) < 2:
        print(f"tolerance={tolerance} points={len(cloud)} skipped", flush=True)
        continue
    results[tolerance] = cloud, ripser(cloud, maxdim=args.maxdim)["dgms"]
finite = [b[np.isfinite(b)] for _, dgms in results.values() for b in dgms]
reach = max((b.max() for b in finite if b.size), default=1.0)
radii = np.linspace(0, 1.1*reach, 400)

fig, axes = plt.subplots(1, args.maxdim+1, figsize=(4.3*(args.maxdim+1), 3.6), constrained_layout=True, sharex=True)
with open(out / "rips-bars.csv", "w", newline="") as stream:
    writer = csv.writer(stream)
    writer.writerow(["max_abs_log_formant_error", "points", "dimension", "birth", "death"])
    for tolerance, (cloud, diagrams) in results.items():
        for d, bars in enumerate(diagrams):
            writer.writerows([tolerance, len(cloud), d, b, e] for b, e in bars)
            betti = [np.sum((bars[:, 0] <= r) & (r < bars[:, 1])) for r in radii]
            axes[d].step(radii, betti, where="post", label=f"error ≤ {tolerance} ({len(cloud)} pts)")
            done = bars[np.isfinite(bars[:, 1])]
            longest = np.sort(done[:, 1]-done[:, 0])[::-1][:3]
            print(f"tolerance={tolerance} points={len(cloud)} H{d} bars={len(bars)} longest={np.round(longest, 3)}", flush=True)
for d, ax in enumerate(axes):
    ax.set(title=f"Betti {d}", xlabel="Rips radius r (normalised parameters)", ylabel="Rank")
axes[0].set_yscale("log")
axes[0].legend()
fig.savefig(out / "rips-betti.png", dpi=160)
print(f"-> {out / 'rips-bars.csv'}, {out / 'rips-betti.png'}")
