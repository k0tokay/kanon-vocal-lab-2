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


def init(lib, vowel, band):
    global eps
    sample.load(lib, vowel)
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
    parser.add_argument("--edges", type=Path, help="default: samples-edges-<eps>.npz next to the samples")
    parser.add_argument("--eps", type=float, default=.01)
    parser.add_argument("--lib", type=Path, default=sample.root / "build-mac/measure.so")
    parser.add_argument("--workers", type=int, default=os.cpu_count())
    parser.add_argument("--targets", type=int, default=3, help="retry targets per failed component")
    parser.add_argument("--fresh", action="store_true", help="redo the first pass even if saved")
    args = parser.parse_args()
    args.edges = args.edges or args.samples.with_name(f"samples-edges-{args.eps}.npz")
    data, graph = np.load(args.samples), np.load(args.edges)
    vowel = str(data["vowel"]) if "vowel" in data else "a"
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
    saved = args.edges.with_name(f"connect-{args.eps}.npz")
    pool = mp.get_context("spawn").Pool(args.workers, init, (args.lib.resolve(), vowel, args.eps))
    start = perf_counter()
    if saved.exists() and not args.fresh:
        rows = [tuple(r) for r in np.load(saved)["rows"]]
    else:
        # First pass: closest pair between each component and the largest one.
        jobs, members = [], []
        for c in np.flatnonzero(np.arange(count) != giant):
            mine = points[label == c]
            d = np.linalg.norm(mine[:, None, :]-core[None, :, :], axis=2)
            i, j = np.unravel_index(d.argmin(), d.shape)
            jobs.append((mine[i], core[j]))
            members.append((c, sizes[c], d[i, j]))
        rows = [(c, size, gap, *r) for (c, size, gap), r in zip(members, pool.map(connect, jobs, chunksize=1))]
    # Retry failures against the grown core: several targets, both directions.
    grown = np.isin(label, [giant] + [int(r[0]) for r in rows if r[3]])
    jobs, owners = [], []
    for k, r in enumerate(rows):
        if r[3]:
            continue
        mine, core = points[label == int(r[0])], points[grown]
        d = np.linalg.norm(mine[:, None, :]-core[None, :, :], axis=2)
        for flat in np.argsort(d, axis=None)[:args.targets]:
            i, j = np.unravel_index(flat, d.shape)
            jobs += [(mine[i], core[j]), (core[j], mine[i])]
            owners += [k, k]
    for k, result in zip(owners, pool.map(connect, jobs, chunksize=1)):
        if result[0] and not rows[k][3]:
            rows[k] = (*rows[k][:3], *result)
    pool.close()
    print(f"seconds={perf_counter()-start:.0f} retried_paths={len(jobs)}", flush=True)
    joined = sum(size for c, size, gap, good, *_ in rows if good)
    failed = [(c, size, gap) for c, size, gap, good, *_ in rows if not good]
    print(f"joined {sum(bool(r[3]) for r in rows)}/{len(rows)} components; points in largest after joining: {sizes[giant]+joined:.0f}/{n}")
    ratio = np.array([length/gap for _, _, gap, good, length, *_ in rows if good])
    if len(ratio):
        print(f"  corrected path length / straight gap: median {np.median(ratio):.2f}, max {ratio.max():.2f}")
    print(f"  failed: {len(failed)} components, sizes {np.bincount(np.array([s for _, s, _ in failed], int)).tolist() if failed else []} (index = size), straight gaps median {np.median([g for *_, g in failed]) if failed else 0:.3f}")
    np.savez(saved, rows=np.array(rows, float))
