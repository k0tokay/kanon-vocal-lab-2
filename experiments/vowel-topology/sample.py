"""Replica exchange over shapes whose F1-F3 stay near Kanon's static /a/.

Writes the accepted shapes in range-normalised coordinates of the movable
parameters together with their maximum absolute log-formant error.
"""
import argparse
import ctypes
import json
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
low, high = [np.array([float(p.get(k)) for p in params]) for k in ("min", "max")]
active = (high > low) & ~np.isin(names, ["VO", "TRX", "TRY"])
lib = target = base = None


def shape(vowel):
    values = {p.get("name"): float(p.get("value")) for p in xml.findall(f".//vocal_tract_model/shapes/shape[@name='{vowel}']/param")}
    return np.array([values[n] for n in names])


def load(path, vowel="a"):
    """Each process owns its native tract and acoustic model; the target is the speaker's static vowel."""
    global lib, target, base
    base = shape(vowel)
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
    """Advance one replica-exchange chain, starting fresh or from a saved state."""
    seed, steps, keep, chain = job
    temps = np.geomspace(.004, .4, 6)
    rng = np.random.default_rng(seed)
    if chain is None:
        ref = (base[active]-low[active])/(high-low)[active]
        states = np.tile(ref, (len(temps), 1))
        errors = np.array([error(q) for q in states])
        first, samples = 0, [ref]
    else:
        rng.bit_generator.state = chain["rng"]
        states, errors = np.array(chain["states"]), np.array(chain["errors"])
        first, samples = chain["step"], []
    start, evaluations = perf_counter(), 0
    for step in range(first, first+steps):
        for i, t in enumerate(temps):
            trial = rng.random(states.shape[1]) if rng.random() < .08 else 1-abs((states[i]+rng.normal(0, .025+t/3, states.shape[1])) % 2-1)
            e = error(trial)
            evaluations += 1
            if np.log(rng.random()) < (errors[i]-e)/t:
                states[i], errors[i] = trial, e
        for i in range(step % 2, len(temps)-1, 2):
            j = i+1
            if np.log(rng.random()) < (1/temps[i]-1/temps[j])*(errors[i]-errors[j]):
                states[[i, j]], errors[[i, j]] = states[[j, i]], errors[[j, i]]
        if step % 10 == 0:
            samples.extend(states[errors <= keep].copy())
    chain = {"step": first+steps, "states": states.tolist(), "errors": errors.tolist(), "rng": rng.bit_generator.state}
    return seed, samples, chain, evaluations, perf_counter()-start


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Running again with the same --out continues every saved chain and adds new seeds.")
    parser.add_argument("--lib", type=Path, default=root / "build-mac/measure.so")
    parser.add_argument("--vowel", default="a", help="vocal-tract shape in the speaker file")
    parser.add_argument("--out", type=Path, help="default: results/kanon-<vowel>/samples.npz")
    parser.add_argument("--seeds", type=int, nargs="+", default=[42, 43, 44])
    parser.add_argument("--steps", type=int, default=600, help="steps added to each chain in this run")
    parser.add_argument("--keep", type=float, default=.05, help="largest error stored")
    parser.add_argument("--workers", type=int, default=os.cpu_count())
    parser.add_argument("--fresh", action="store_true", help="ignore saved chains and samples")
    args = parser.parse_args()
    args.out = args.out or Path(__file__).resolve().parent / f"results/kanon-{args.vowel}/samples.npz"
    args.out.parent.mkdir(parents=True, exist_ok=True)
    chains_file = args.out.with_suffix(".chains.json")
    chains, points = {}, np.empty((0, int(active.sum())))
    if args.out.exists() and not args.fresh:
        chains = {int(k): v for k, v in json.loads(chains_file.read_text()).items()}
        saved = np.load(args.out)
        assert (str(saved["vowel"]) if "vowel" in saved else "a") == args.vowel, "saved samples are for another vowel"
        points = saved["points"]
    seeds = sorted(set(args.seeds) | set(chains))
    start = perf_counter()
    jobs = [(seed, args.steps, args.keep, chains.get(seed)) for seed in seeds]
    found, evaluations, busy = [], 0, 0.
    with mp.get_context("spawn").Pool(min(args.workers, len(jobs)), load, (args.lib.resolve(), args.vowel)) as pool:
        for seed, samples, chain, count, seconds in pool.imap_unordered(run, jobs):
            found += samples
            chains[seed] = chain
            evaluations += count
            busy += seconds
    wall = perf_counter()-start
    load(args.lib.resolve(), args.vowel)
    before = len(points)
    points = np.unique(np.vstack([points, *found]) if found else points, axis=0)
    errors = np.array([error(z) for z in points])
    np.savez(args.out, points=points, errors=errors, names=names[active], vowel=args.vowel)
    chains_file.write_text(json.dumps(chains))
    new = len(points)-before
    print(f"chains={len(chains)} steps={[chains[s]['step'] for s in seeds]} evaluations={evaluations} "
          f"ms_per_evaluation={1e3*busy/evaluations:.2f} wall_seconds={wall:.1f} new_points={new} total_points={len(points)} "
          f"cpu_seconds_per_new_point={busy/max(new, 1):.2f}", flush=True)
    for tolerance in (.005, .01, .02, .05):
        print(f"  error<={tolerance}: {np.sum(errors <= tolerance)} points", flush=True)
