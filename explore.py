"""Replica exchange on static /a/ and sampled connectivity of straight paths."""
import ctypes
import multiprocessing as mp
import os
from time import perf_counter
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np
from scipy.spatial import cKDTree
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

speaker = Path("speakers/fulkhisa-kanon/fulkhisa-kanon-v0-8-vowel-variation.speaker")
lib = ctypes.CDLL("./measure.so")
pointer = np.ctypeslib.ndpointer(np.float64, ndim=1, flags="C_CONTIGUOUS")
lib.evaluate.argtypes = [pointer, pointer]
lib.init.argtypes = [ctypes.c_char_p]
lib.init.restype = None
lib.init(str(speaker).encode())
xml = ET.parse(speaker)
params = sorted(xml.findall(".//vocal_tract_model/anatomy/param"), key=lambda p: int(p.get("index")))
names = [p.get("name") for p in params]
vowel = {p.get("name"): float(p.get("value")) for p in xml.findall(".//vocal_tract_model/shapes/shape[@name='a']/param")}
base = np.array([vowel[n] for n in names])
low, high = [np.array([float(p.get(k)) for p in params]) for k in ("min", "max")]
active = (high > low) & ~np.isin(names, ["VO", "TRX", "TRY"])
def formants(x):
    f = np.zeros(3)
    return f if lib.evaluate(x, f) and np.all(f > 0) else None

target = formants(base)
assert target is not None
def error(z):
    x = base.copy()
    x[active] = low[active] + z * (high-low)[active]
    f = formants(x)
    return np.inf if f is None else np.max(np.abs(np.log(f/target)))

def run(seed):
    rng = np.random.default_rng(seed)
    temps = np.geomspace(.004, .4, 6)
    ref = (base[active]-low[active])/(high-low)[active]
    states = np.tile(ref, (len(temps), 1))
    errors = np.array([error(q) for q in states])
    samples = [ref]
    for step in range(600):
        for i, t in enumerate(temps):
            trial = rng.random(len(ref)) if rng.random() < .08 else 1-abs((states[i]+rng.normal(0,.025+t/3,len(ref)))%2-1)
            e = error(trial)
            if np.log(rng.random()) < (errors[i]-e)/t:
                states[i], errors[i] = trial, e
        for i in range(step%2, len(temps)-1, 2):
            j = i+1
            if np.log(rng.random()) < (1/temps[i]-1/temps[j])*(errors[i]-errors[j]):
                states[[i,j]], errors[[i,j]] = states[[j,i]], errors[[j,i]]
        if step%10 == 0:
            samples.extend(states[errors <= .05].copy())
    return samples

def measure_edge(pair):
    i, j = pair
    interior = (error(points[i]+t*(points[j]-points[i])) for t in np.linspace(0,1,17)[1:-1])
    return i, j, max(errors[i], errors[j], *interior)

if __name__ == "__main__":
    # Separate processes isolate the mutable native tract and acoustic model.
    workers = max(1, min(int(os.getenv("VTL_WORKERS", "3")), len(os.sched_getaffinity(0))))
    ctx = mp.get_context("fork")
    start = perf_counter()
    samples = []
    with ctx.Pool(min(workers, 3)) as pool:
        for batch in pool.imap(run, (42, 43, 44)):
            samples.extend(batch)
            np.save("samples.npy", np.unique(samples, axis=0))
    print(f"workers={workers} sampling_seconds={perf_counter()-start:.2f}", flush=True)
    points = np.load("samples.npy")
    errors = np.array([error(p) for p in points])
    tree = cKDTree(points)
    edges = set()
    for i, p in enumerate(points):
        for j in np.atleast_1d(tree.query(p, k=min(6,len(points)))[1]):
            if i != j:
                edges.add(tuple(sorted((i, int(j)))))
    with ctx.Pool(workers) as pool:
        paths = pool.map(measure_edge, sorted(edges), chunksize=4)
    print(f"total_seconds={perf_counter()-start:.2f}", flush=True)
    for tolerance in (.005,.01,.02,.05):
        selected = errors <= tolerance
        pairs = [(i,j) for i,j,e in paths if e <= tolerance]
        rows, cols = zip(*pairs) if pairs else ([], [])
        graph = coo_matrix((np.ones(len(rows)),(rows,cols)),shape=(len(points),)*2).tocsr()
        count = connected_components(graph[selected][:,selected], directed=False, return_labels=False)
        print(f"tolerance={tolerance} points={selected.sum()} sampled_graph_components={count}", flush=True)
