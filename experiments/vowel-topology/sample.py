"""Replica exchange over shapes whose F1-F3 stay near Kanon's static /a/.

Writes the accepted shapes in range-normalised coordinates of the movable
parameters together with their maximum absolute log-formant error.
"""
import argparse
import ctypes
import multiprocessing as mp
import os
import xml.etree.ElementTree as ET
from pathlib import Path
from time import perf_counter

import numpy as np

root = Path(__file__).resolve().parents[2]
speaker = root / "speakers/fulkhisa-kanon/fulkhisa-kanon-v0-8-vowel-variation.speaker"
xml = ET.parse(speaker)
params = sorted(xml.findall(".//vocal_tract_model/anatomy/param"), key=lambda p: int(p.get("index")))
names = np.array([p.get("name") for p in params])
vowel = {p.get("name"): float(p.get("value")) for p in xml.findall(".//vocal_tract_model/shapes/shape[@name='a']/param")}
base = np.array([vowel[n] for n in names])
low, high = [np.array([float(p.get(k)) for p in params]) for k in ("min", "max")]
active = (high > low) & ~np.isin(names, ["VO", "TRX", "TRY"])
lib = target = None


def load(path):
    # Each process owns its native tract and acoustic model.
    global lib, target
    lib = ctypes.CDLL(str(path))
    pointer = np.ctypeslib.ndpointer(np.float64, ndim=1, flags="C_CONTIGUOUS")
    lib.evaluate.argtypes = [pointer, pointer]
    lib.init.argtypes = [ctypes.c_char_p]
    lib.init.restype = None
    lib.init(str(speaker).encode())
    target = formants(base)
    assert target is not None


def formants(x):
    f = np.zeros(3)
    return f if lib.evaluate(x, f) and np.all(f > 0) else None


def error(z):
    x = base.copy()
    x[active] = low[active] + z * (high-low)[active]
    f = formants(x)
    return np.inf if f is None else np.max(np.abs(np.log(f/target)))


def run(job):
    seed, steps, keep = job
    rng = np.random.default_rng(seed)
    temps = np.geomspace(.004, .4, 6)
    ref = (base[active]-low[active])/(high-low)[active]
    states = np.tile(ref, (len(temps), 1))
    errors = np.array([error(q) for q in states])
    samples = [ref]
    for step in range(steps):
        for i, t in enumerate(temps):
            trial = rng.random(len(ref)) if rng.random() < .08 else 1-abs((states[i]+rng.normal(0, .025+t/3, len(ref))) % 2-1)
            e = error(trial)
            if np.log(rng.random()) < (errors[i]-e)/t:
                states[i], errors[i] = trial, e
        for i in range(step % 2, len(temps)-1, 2):
            j = i+1
            if np.log(rng.random()) < (1/temps[i]-1/temps[j])*(errors[i]-errors[j]):
                states[[i, j]], errors[[i, j]] = states[[j, i]], errors[[j, i]]
        if step % 10 == 0:
            samples.extend(states[errors <= keep].copy())
    return samples


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--lib", type=Path, default=root / "build-mac/measure.so")
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parent / "results/kanon-a/samples.npz")
    parser.add_argument("--seeds", type=int, nargs="+", default=[42, 43, 44])
    parser.add_argument("--steps", type=int, default=600)
    parser.add_argument("--keep", type=float, default=.05, help="largest error stored")
    parser.add_argument("--workers", type=int, default=os.cpu_count())
    args = parser.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    start = perf_counter()
    jobs = [(seed, args.steps, args.keep) for seed in args.seeds]
    with mp.get_context("spawn").Pool(min(args.workers, len(jobs)), load, (args.lib.resolve(),)) as pool:
        samples = np.unique([s for batch in pool.imap(run, jobs) for s in batch], axis=0)
    load(args.lib.resolve())
    errors = np.array([error(z) for z in samples])
    np.savez(args.out, points=samples, errors=errors, names=names[active], seeds=args.seeds, steps=args.steps)
    print(f"points={len(samples)} seconds={perf_counter()-start:.1f} -> {args.out}", flush=True)
