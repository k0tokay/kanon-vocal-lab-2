"""Join the split components of the checked eps graph by paths on the band.

Boruvka-style rounds: every component tries the closest untried pair
(one vertex inside, one outside) and walks between them; the walk's interior
points are pulled back onto the band by minimum-norm Gauss-Newton steps on
the log formants and every segment between consecutive points is checked.
Successful walks merge components; a component gives up after `--attempts`
failed pairs since its last merge. A failure only means this path
construction failed; it does not prove the components are separate.
"""
import argparse
import multiprocessing as mp
import os
from pathlib import Path
from time import perf_counter

import numpy as np
from scipy.cluster.hierarchy import DisjointSet

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
    parser.add_argument("--attempts", type=int, default=6, help="failed pairs before a component gives up")
    args = parser.parse_args()
    args.edges = args.edges or args.samples.with_name(f"samples-edges-{args.eps}.npz")
    data, graph = np.load(args.samples), np.load(args.edges)
    vowel = str(data["vowel"]) if "vowel" in data else "a"
    points = data["points"][data["errors"] <= args.eps]
    edges, path = graph["edges"], graph["path_errors"]
    assert edges.max() < len(points), "edge file was built for a different band"
    n = len(points)
    sets = DisjointSet(range(n))
    for i, j in edges[path <= args.eps]:
        sets.merge(int(i), int(j))
    D = np.linalg.norm(points[:, None, :]-points[None, :, :], axis=2)
    def summary():
        sizes = sorted((len(c) for c in sets.subsets()), reverse=True)
        return f"components={len(sizes)} largest={sizes[:5]} singletons={sizes.count(1)}"
    print(f"eps={args.eps} points={n} checked edges: {summary()}", flush=True)
    pool = mp.get_context("spawn").Pool(args.workers, init, (args.lib.resolve(), vowel, args.eps))
    start, tried, fails, rows, done = perf_counter(), set(), {}, [], set()
    for step in range(1, 100):
        jobs, seen = [], set()
        for members in sets.subsets():
            idx = np.array(sorted(members))
            root = sets[idx[0]]
            if len(idx) == n or fails.get(root, 0) >= args.attempts:
                continue
            outside = np.setdiff1d(np.arange(n), idx)
            sub = D[np.ix_(idx, outside)]
            for flat in np.argsort(sub, axis=None):
                i, j = int(idx[flat // len(outside)]), int(outside[flat % len(outside)])
                if (i, j) not in tried:
                    break
            else:
                continue
            if frozenset((i, j)) in seen:
                continue
            seen.add(frozenset((i, j)))
            tried.add((i, j))
            jobs.append((i, j, root))
        if not jobs:
            break
        results = pool.map(connect, [(points[i], points[j]) for i, j, _ in jobs], chunksize=1)
        for (i, j, root), r in zip(jobs, results):
            rows.append((i, j, D[i, j], *r, step))
            if r[0]:
                if not sets.connected(i, j):
                    sets.merge(i, j)
                    fails.pop(root, None)
                    fails.pop(sets[j], None)
            else:
                fails[root] = fails.get(root, 0)+1
        # a merged component starts afresh
        fails = {sets[r]: f for r, f in fails.items() if sets[r] == r}
        print(f"round {step}: paths={len(jobs)} joined={sum(r[0] for r in results)} "
              f"seconds={perf_counter()-start:.0f} {summary()}", flush=True)
    pool.close()
    rows = np.array(rows, float)
    good = rows[rows[:, 3] > 0]
    print(f"paths tried={len(rows)} succeeded={len(good)}; length / straight gap median "
          f"{np.median(good[:, 4]/good[:, 2]):.2f}, max {np.max(good[:, 4]/good[:, 2]):.2f}")
    print("final", summary())
    rest = [sorted(c) for c in sets.subsets() if len(c) < n/2]
    errors = data["errors"][data["errors"] <= args.eps]
    for c in rest:
        print(f"  left out: size={len(c)} worst error={errors[c].max():.4f} "
              f"at box edge={bool(np.any((points[c] < .01) | (points[c] > .99)))}")
    np.savez(args.edges.with_name(f"connect-{args.eps}.npz"), rows=rows,
             columns=np.array(["i", "j", "gap", "ok", "length", "npoints", "worst", "round"]))
