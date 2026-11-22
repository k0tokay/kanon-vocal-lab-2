"""Generates a synthetic Japanese-like corpus with known anatomy, articulation and glottis frames.

Run from this directory: python3 gen_dataset.py OUT_DIR [--speakers 64] [--utts 80] [--seed 0]
Each speaker gets a random anatomy (inner 80 % of every VTL range) and a base f0.
Utterances are random mora strings turned into gestural scores with that anatomy.
"""
import argparse
import json
import time
from pathlib import Path

import numpy as np

from synth import Pool
from vtl import Vtl

VOWELS = ["a", "i", "M", "e", "o"]
CONSONANTS = ["k", "g", "s", "z", "t", "d", "n", "h", "m", "j", "w", "p", "b", "4", "S", "tS", "dZ", "ts", "C", "F"]
ALLOWED = {  # Japanese-like consonant/vowel combinations
    "j": ["a", "M", "o"], "w": ["a"], "ts": ["M"], "F": ["M"], "C": ["i"], "S": ["a", "i", "M", "o"],
    "tS": ["a", "i", "M", "o"], "dZ": ["a", "i", "M", "o"], "s": ["a", "M", "e", "o"], "z": ["a", "M", "e", "o"],
    "t": ["a", "e", "o"], "d": ["a", "e", "o"], "h": ["a", "e", "o"],
}


def random_segments(rng):
    segments = [("", 0.1)]
    for _ in range(rng.integers(3, 9)):
        if rng.random() < 0.8:
            c = CONSONANTS[rng.integers(len(CONSONANTS))]
            v = rng.choice(ALLOWED.get(c, VOWELS))
            segments.append((c, rng.uniform(0.045, 0.09)))
        else:
            v = VOWELS[rng.integers(len(VOWELS))]
        segments.append((v, rng.uniform(0.08, 0.16)))
        if rng.random() < 0.08:
            segments.append(("N", rng.uniform(0.07, 0.11)))
    segments.append(("", 0.1))
    return segments


def f0_contour(rng, frames, base):
    """Declining phrase contour with a random accent bump, in Hz."""
    t = np.linspace(0, 1, frames)
    semitones = -rng.uniform(1, 4) * t
    centre, width, height = rng.uniform(0.15, 0.7), rng.uniform(0.08, 0.2), rng.uniform(0, 4)
    semitones += height * np.exp(-0.5 * ((t - centre) / width) ** 2)
    return base * 2 ** (semitones / 12)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("out", type=Path)
    parser.add_argument("--speakers", type=int, default=64)
    parser.add_argument("--utts", type=int, default=80)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    vtl = Vtl()
    rng = np.random.default_rng(args.seed)
    lo, hi = vtl.anatomy_min, vtl.anatomy_max
    anatomies = lo + rng.uniform(0.1, 0.9, (args.speakers, 13)) * (hi - lo)
    base_f0 = np.exp(rng.uniform(np.log(90), np.log(330), args.speakers))
    f0_index = vtl.glottis_names.index("f0")

    pool = Pool()
    start = time.time()
    for s in range(args.speakers):
        segments = [random_segments(rng) for _ in range(args.utts)]
        scored = pool.score_frames([(anatomies[s], seg) for seg in segments])
        jobs, glottis_all = [], []
        for applied, tract, glottis, _, _ in scored:
            glottis = glottis.copy()
            glottis[:, f0_index] = f0_contour(rng, len(glottis), base_f0[s])
            glottis_all.append(glottis)
            jobs.append((applied, tract, glottis))
        audio = pool.render(jobs)
        keep = [i for i, a in enumerate(audio) if a is not None and np.all(np.isfinite(a)) and np.max(np.abs(a)) < 1.0]
        applied, _, _, tract_min, tract_max = scored[0]
        np.savez_compressed(
            args.out / f"spk{s:03d}.npz",
            anatomy=applied, tract_min=tract_min, tract_max=tract_max, base_f0=base_f0[s],
            audio=np.concatenate([audio[i] for i in keep]),
            audio_len=np.array([len(audio[i]) for i in keep]),
            tract=np.concatenate([jobs[i][1] for i in keep]),
            glottis=np.concatenate([glottis_all[i] for i in keep]),
            frames=np.array([len(jobs[i][1]) for i in keep]),
            text=np.array([" ".join(n for n, _ in segments[i] if n) for i in keep]))
        seconds = sum(len(audio[i]) for i in keep) / 16000
        print(f"speaker {s}: {len(keep)}/{args.utts} utterances, {seconds:.0f} s audio, "
              f"elapsed {time.time() - start:.0f} s", flush=True)
    pool.close()
    meta = {"speakers": args.speakers, "utts": args.utts, "seed": args.seed,
            "anatomy_names": vtl.anatomy_names, "anatomy_min": lo.tolist(), "anatomy_max": hi.tolist(),
            "anatomy_reference": vtl.anatomy_reference.tolist(),
            "tract_names": vtl.tract_names, "glottis_names": vtl.glottis_names,
            "glottis_min": vtl.glottis_min.tolist(), "glottis_max": vtl.glottis_max.tolist(),
            "frame_rate": 100, "audio_rate": 16000}
    (args.out / "meta.json").write_text(json.dumps(meta, indent=1))


if __name__ == "__main__":
    main()
