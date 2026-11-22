"""H0 over articulatory distance with acoustically checked edges.

Edges are the k nearest neighbours plus the Euclidean minimum spanning tree,
whose edges decide the plain Rips H0. Each straight edge is sampled at
interior points; its value is the largest formant error seen, and sampling
stops once that exceeds --cap. For an error band eps, a vertex enters if its
own error is <= eps and an edge if its whole path is <= eps; the edge then
enters the filtration at its length r.
"""
import argparse
import multiprocessing as mp
import os
from pathlib import Path
from time import perf_counter

import numpy as np
from scipy.cluster.hierarchy import DisjointSet
from scipy.spatial import cKDTree

import sample



def init(lib, edge_cap, edge_order, cloud):
    global cap, order, points
    sample.load(lib)
    cap, order, points = edge_cap, edge_order, cloud


def check(edge):
    i, j = edge
    worst = 0.
    # Bisection order finds a high point early, so failing edges stop sooner.
    for k in order:
        worst = max(worst, sample.error(points[i]+k*(points[j]-points[i])))
        if worst > cap:
            break
    return worst


def bisection(n):
    """Interior fractions k/(n+1), coarsest dyadic levels first."""
    level = lambda k: (k & -k)
    return [k/(n+1) for k in sorted(range(1, n+1), key=lambda k: (-level(k), k))]


def prim(x):
    """Euclidean minimum spanning tree in O(n^2) time and O(n) memory."""
    n = len(x)
    best = np.full(n, np.inf)
    parent = np.zeros(n, int)
    done = np.zeros(n, bool)
    current, tree = 0, []
    for _ in range(n-1):
        done[current] = True
        d = np.linalg.norm(x-x[current], axis=1)
        closer = (d < best) & ~done
        best[closer], parent[closer] = d[closer], current
        best[done] = np.inf
        current = int(np.argmin(best))
        tree.append((int(parent[current]), current))
    return tree


def components(n, alive, edges, radii):
    """Count components of the alive vertices as edges enter by length."""
    sets = DisjointSet(np.flatnonzero(alive))
    counts, k = [], 0
    for r in radii:
        while k < len(edges) and edges[k][2] <= r:
            sets.merge(edges[k][0], edges[k][1])
            k += 1
        counts.append(sets.n_subsets)
    sizes = np.sort([len(s) for s in sets.subsets()])[::-1]
    return counts, sizes


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    here = Path(__file__).resolve().parent
    parser.add_argument("samples", type=Path, nargs="?", default=here / "results/kanon-a/samples.npz")
    parser.add_argument("--lib", type=Path, default=sample.root / "build-mac/measure.so")
    parser.add_argument("--neighbours", type=int, default=8)
    parser.add_argument("--interior", type=int, default=7, help="interior points per edge")
    parser.add_argument("--cap", type=float, default=.05)
    parser.add_argument("--out", type=Path, help="edge file (default: <samples>-edges.npz)")
    parser.add_argument("--limit", type=int, help="use only the first points (for testing)")
    parser.add_argument("--workers", type=int, default=os.cpu_count())
    args = parser.parse_args()
    order = bisection(args.interior)
    data = np.load(args.samples)
    keep = data["errors"] <= args.cap
    points, errors = data["points"][keep][:args.limit], data["errors"][keep][:args.limit]
    out = args.out or args.samples.with_name(args.samples.stem + "-edges.npz")
    tree = cKDTree(points)
    _, nn = tree.query(points, args.neighbours+1)
    edges = {tuple(sorted((i, int(j)))) for i, row in enumerate(nn) for j in row[1:]}
    # Spanning trees of every band, so the unchecked graph reproduces Rips H0.
    mst = 0
    for eps in (.01, .02, args.cap):
        index = np.flatnonzero(errors <= eps)
        if len(index) > 1:
            span = {tuple(sorted((int(index[a]), int(index[b])))) for a, b in prim(points[index])}
            mst += len(span)
            edges |= span
    edges = np.array(sorted(edges))
    lengths = np.linalg.norm(points[edges[:, 0]]-points[edges[:, 1]], axis=1)
    print(f"points={len(points)} edges={len(edges)} spanning_tree_edges={mst} interior={order}", flush=True)
    start = perf_counter()
    with mp.get_context("spawn").Pool(args.workers, init, (args.lib.resolve(), args.cap, order, points)) as pool:
        worst = np.array(pool.map(check, map(tuple, edges), chunksize=64))
    print(f"edge_seconds={perf_counter()-start:.0f}", flush=True)
    path = np.maximum(worst, np.maximum(errors[edges[:, 0]], errors[edges[:, 1]]))
    np.savez(out, edges=edges, lengths=lengths, path_errors=path, interior=args.interior)

    radii = (.1, .2, .3, .4, .5, .6, .7, .8, 1., np.inf)
    by_length = np.argsort(lengths)
    print("r:", radii)
    for eps in (.01, .02, .05):
        alive = errors <= eps
        both = alive[edges[:, 0]] & alive[edges[:, 1]]
        for label, ok in (("unchecked", both), ("checked", both & (path <= eps))):
            chosen = [(edges[k, 0], edges[k, 1], lengths[k]) for k in by_length if ok[k]]
            counts, sizes = components(len(points), alive, chosen, radii)
            print(f"eps={eps} {label:9s} points={alive.sum()} edges={ok.sum()} components={counts} largest={sizes[:5].tolist()}", flush=True)
