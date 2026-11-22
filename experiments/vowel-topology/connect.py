"""Try to join every split component of the checked eps graph to the largest.

For each smaller component, the closest pair (one vertex in it, one in the
largest component) is joined by a path whose interior points are pulled back
onto the band by minimum-norm Gauss-Newton steps on the log formants. Each
segment between consecutive projected points is checked at interior points
and split again where it leaves the band. A failure only means this path
construction failed; it does not prove the components are separate.
"""
import argparse
import multiprocessing as mp
import os
from pathlib import Path
from time import perf_counter

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

import sample
import spectrum

eps = .01


def init(lib, band):
    global eps
    sample.load(lib)
    eps = band


def residual(z):
    f = spectrum.log_formants(z)
    return None if f is None else f-np.log(sample.target)


def project(z, iterations=10, trust=.05):
    """Move z to max|residual| <= eps/2 by damped minimum-norm steps."""
    for _ in range(iterations):
        r = residual(z)
        if r is None:
            return None
        if np.max(np.abs(r)) <= eps/2:
            return z
        J = spectrum.jacobian(z)
        if J is None:
            return None
        step = np.linalg.pinv(J) @ r
        z = np.clip(z-step*min(1, trust/np.linalg.norm(step)), 0, 1)
    return None


def segment_ok(a, b):
    return all(sample.error(a+t*(b-a)) <= eps for t in (.25, .5, .75))


def connect(pair, spacing=.02, halvings=4):
    """Predictor-corrector walk from a towards b on the band.

    Each predictor moves `spacing` straight towards b from the current point,
    the corrector projects it back, and the segment between consecutive
    points is checked; the step is halved on failure.
    Returns (ok, path length, number of path points, worst point error).
    """
    a, b = pair
    z, path = a, [a]
    budget = 4*int(np.ceil(np.linalg.norm(b-a)/spacing))+20
    while len(path) < budget:
        gap = np.linalg.norm(b-z)
        if gap <= spacing and segment_ok(z, b):
            path.append(b)
            P = np.array(path)
            return True, float(np.linalg.norm(np.diff(P, axis=0), axis=1).sum()), len(P), max(sample.error(q) for q in P)
        h = min(spacing, gap)
        for _ in range(halvings+1):
            q = project(z+h*(b-z)/gap)
            if q is not None and segment_ok(z, q) and np.linalg.norm(b-q) < gap:
                break
            h /= 2
        else:
            return False, 0., len(path), float(gap)
        z = q
        path.append(z)
    return False, 0., len(path), float(np.linalg.norm(b-z))


if __name__ == "__main__":
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", type=Path, default=here / "results/kanon-a/samples.npz")
    parser.add_argument("--edges", type=Path, default=here / "results/kanon-a/samples-edges-0.01.npz")
    parser.add_argument("--eps", type=float, default=.01)
    parser.add_argument("--lib", type=Path, default=sample.root / "build-mac/measure.so")
    parser.add_argument("--workers", type=int, default=os.cpu_count())
    args = parser.parse_args()
    data, graph = np.load(args.samples), np.load(args.edges)
    points = data["points"][data["errors"] <= args.eps]
    edges, path = graph["edges"], graph["path_errors"]
    assert edges.max() < len(points), "edge file was built for a different band"
    ok = path <= args.eps
    n = len(points)
    count, label = connected_components(coo_matrix((np.ones(ok.sum()), (edges[ok, 0], edges[ok, 1])), shape=(n, n)), directed=False)
    sizes = np.bincount(label)
    giant = sizes.argmax()
    core = points[label == giant]
    print(f"eps={args.eps} points={n} components={count} largest={sizes[giant]}", flush=True)
    jobs, members = [], []
    for c in np.flatnonzero(np.arange(count) != giant):
        mine = points[label == c]
        d = np.linalg.norm(mine[:, None, :]-core[None, :, :], axis=2)
        i, j = np.unravel_index(d.argmin(), d.shape)
        jobs.append((mine[i], core[j]))
        members.append((c, sizes[c], d[i, j]))
    start = perf_counter()
    with mp.get_context("spawn").Pool(args.workers, init, (args.lib.resolve(), args.eps)) as pool:
        results = pool.map(connect, jobs, chunksize=1)
    print(f"seconds={perf_counter()-start:.0f}", flush=True)
    rows = [(c, size, gap, *r) for (c, size, gap), r in zip(members, results)]
    joined = sum(size for c, size, gap, good, *_ in rows if good)
    failed = [(c, size, gap) for c, size, gap, good, *_ in rows if not good]
    print(f"joined {sum(r[3] for r in rows)}/{len(rows)} components; points in largest after joining: {sizes[giant]+joined}/{n}")
    lengths = np.array([(gap, length) for _, _, gap, good, length, *_ in rows if good])
    if len(lengths):
        print(f"  straight gap median {np.median(lengths[:, 0]):.3f}, corrected path/gap ratio median {np.median(lengths[:, 1]/lengths[:, 0]):.2f}, max {lengths[:, 1].max()/lengths[lengths[:, 1].argmax(), 0]:.2f}")
    print("  failed (component, size, straight gap):", [(int(c), int(s), round(float(g), 3)) for c, s, g in failed][:30])
    np.savez(args.edges.with_name(f"connect-{args.eps}.npz"), rows=np.array([(c, s, g, ok_, L, m, w) for c, s, g, ok_, L, m, w in rows], float))
