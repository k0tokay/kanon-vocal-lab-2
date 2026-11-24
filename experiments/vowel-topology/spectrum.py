"""How flat is the /a/ formant band? PCA per error band and fibre normals.

For a band {x : max|log F_i(x)/F_i*| <= eps} around a nearly linear fibre, the
three normal directions (row space of the log-formant Jacobian J) should be
the same everywhere and the global PCA should show three small variances of
order (eps/sigma(J))^2. Curvature shows up as normals that turn between
sample points.
"""
import argparse
import multiprocessing as mp
import os
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import sample

step = 1e-3


def init(lib, vowel):
    sample.load(lib, vowel)


def log_formants(z):
    x = sample.base.copy()
    x[sample.active] = sample.low[sample.active] + z*(sample.high-sample.low)[sample.active]
    f = sample.formants(x)
    return None if f is None else np.log(f)


def jacobian(z):
    """Central differences in normalised coordinates, one-sided at the box."""
    f0 = log_formants(z)
    if f0 is None:
        return None
    J = np.zeros((3, len(z)))
    for k in range(len(z)):
        lo, hi = z.copy(), z.copy()
        lo[k], hi[k] = max(z[k]-step, 0), min(z[k]+step, 1)
        a, b = log_formants(lo), log_formants(hi)
        if a is None or b is None:
            return None
        J[:, k] = (b-a)/(hi[k]-lo[k])
    return J


if __name__ == "__main__":
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser()
    parser.add_argument("samples", type=Path, nargs="?", default=here / "results/kanon-a/samples.npz")
    parser.add_argument("--lib", type=Path, default=sample.root / "build-mac/measure.so")
    parser.add_argument("--jacobians", type=int, default=400)
    parser.add_argument("--workers", type=int, default=os.cpu_count())
    args = parser.parse_args()
    data = np.load(args.samples)
    points, errors, names = data["points"], data["errors"], data["names"]
    vowel = str(data["vowel"]) if "vowel" in data else "a"
    out = args.samples.parent

    fig, axes = plt.subplots(1, 2, figsize=(11, 3.8), constrained_layout=True)
    print("PCA variance (normalised units^2), largest to smallest")
    for eps in (.005, .01, .02, .05):
        X = points[errors <= eps]
        var = np.linalg.svd(X-X.mean(0), compute_uv=False)**2/(len(X)-1)
        axes[0].semilogy(range(1, len(var)+1), var, "o-", label=f"error ≤ {eps} ({len(X)} pts)")
        print(f"  eps={eps:<5} n={len(X):5d}", np.array2string(var, precision=4, max_line_width=200))
    axes[0].axhline(1/12, color="gray", ls=":", label="uniform on [0,1]")
    axes[0].set(xlabel="Principal component", ylabel="Variance", title="Global PCA per error band")
    axes[0].legend(fontsize=8)

    rng = np.random.default_rng(0)
    chosen = points[errors <= .01][rng.choice(np.sum(errors <= .01), min(args.jacobians, np.sum(errors <= .01)), replace=False)]
    with mp.get_context("spawn").Pool(args.workers, init, (args.lib.resolve(), vowel)) as pool:
        Js = [J for J in pool.map(jacobian, chosen) if J is not None]
    Js = np.array(Js)
    normals = [np.linalg.svd(J, full_matrices=False)[2] for J in Js]   # 3 x 16 orthonormal rows
    sigma = np.array([np.linalg.svd(J, compute_uv=False) for J in Js])
    mean_projector = np.mean([N.T @ N for N in normals], axis=0)
    w, v = np.linalg.eigh(mean_projector)
    print(f"\nJacobians at {len(Js)} points with error <= 0.01")
    print("  singular values of J (median):", np.round(np.median(sigma, 0), 3))
    print("  band half-width along normals at eps=0.01 (0.01/sigma, median):", np.round(np.median(.01/sigma, 0), 4))
    print("  eigenvalues of mean normal projector (3 ones = constant normals):", np.round(w[::-1][:6], 3))
    pairs = rng.integers(0, len(normals), (2000, 2))
    cosines = np.array([np.linalg.svd(normals[i] @ normals[j].T, compute_uv=False) for i, j in pairs if i != j])
    print("  principal-angle cosines between normal spaces of random pairs (median of each):", np.round(np.median(cosines, 0), 3))
    top = v[:, ::-1][:, :3]
    print("  mean normal directions (loadings > 0.2):")
    for k in range(3):
        load = {n: round(float(c), 2) for n, c in zip(names, top[:, k]) if abs(c) > .2}
        print(f"    n{k+1} weight={w[::-1][k]:.2f}", load)
    sens = np.median(np.linalg.norm(Js, axis=1), 0)
    print("  median |d log F / d z_k| per parameter:", {n: round(float(s), 2) for n, s in zip(names, sens)})

    X = points[errors <= .01]
    _, _, vt = np.linalg.svd(X-X.mean(0), full_matrices=False)
    for k in (1, 2, 3, 4, 5):
        c = np.linalg.svd(vt[-k:] @ top, compute_uv=False)
        print(f"  overlap of last {k} global PCs (eps=0.01) with mean normals: cosines {np.round(c, 2)}")

    axes[1].bar(names, sens, color="steelblue")
    axes[1].set(ylabel="median |∂ log F / ∂z|", title="Formant sensitivity per parameter")
    axes[1].tick_params(axis="x", rotation=60)
    fig.savefig(out / "spectrum.png", dpi=160)
