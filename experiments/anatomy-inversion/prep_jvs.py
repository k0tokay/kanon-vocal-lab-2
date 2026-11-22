"""Converts the JVS corpus (normal voice) into the per-speaker npz format that emjem.py reads.

Run from this directory: python3 prep_jvs.py JVS_ROOT OUT_DIR [--subsets parallel100 nonpara30] [--speakers N]
JVS_ROOT is the unpacked jvs_ver1 directory (jvs001/ ... jvs100/, gender_f0range.txt).

Each utterance is resampled to 16 kHz, trimmed to its active part plus 0.1 s, and scaled to the same
active RMS (LEVEL_RMS). The median noise floor of the recordings is stored in meta.json, so that emjem.py
can give the synthesized audio the same level and noise floor.
"""
import argparse
import json
from pathlib import Path

import numpy as np
from scipy.io import wavfile
from scipy.signal import resample_poly

from emjem import active_rms
from vtl import Vtl

RATE = 16000
HOP = RATE // 100
LEVEL_RMS = 0.05
MARGIN = 10  # frames kept before and after the active part


def read_tags(root):
    tags = {}
    path = root / "gender_f0range.txt"
    if path.exists():
        for line in path.read_text().splitlines():
            parts = line.split()
            if len(parts) >= 4 and parts[0].startswith("jvs"):
                tags[parts[0]] = {"gender": parts[1], "f0_min": float(parts[2]), "f0_max": float(parts[3])}
    return tags


def load(path):
    rate, x = wavfile.read(path)
    x = x.astype(np.float64)
    if x.ndim > 1:
        x = x.mean(1)
    x /= 32768.0
    g = np.gcd(rate, RATE)
    return resample_poly(x, RATE // g, rate // g)


def frame_energy(x):
    n = len(x) // HOP
    return np.mean(np.square(x[: n * HOP].reshape(n, HOP)), axis=1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--subsets", nargs="+", default=["parallel100", "nonpara30"])
    parser.add_argument("--speakers", type=int, default=None, help="use only the first N speakers")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    tags = read_tags(args.root)
    names = sorted(p.name for p in args.root.glob("jvs[0-9][0-9][0-9]") if p.is_dir())[: args.speakers]
    floors = []
    for s, name in enumerate(names):
        audio, lengths, frames, texts = [], [], [], []
        for subset in args.subsets:
            for wav in sorted((args.root / name / subset).glob("wav24kHz16bit/*.wav")):
                x = load(wav)
                e = frame_energy(x)
                if len(e) < 20:
                    continue
                scale = LEVEL_RMS / max(active_rms(x, RATE), 1e-9)
                # Noise floor: RMS of the quietest 10 % of the frames.
                floors.append(np.sqrt(np.quantile(e, 0.1)) * scale)
                active = np.flatnonzero(e >= e.max() * 1e-4)
                start, stop = max(0, active[0] - MARGIN), min(len(e), active[-1] + 1 + MARGIN)
                y = (x[start * HOP: stop * HOP] * scale).astype(np.float32)
                audio.append(y); lengths.append(len(y)); frames.append(len(y) // HOP)
                texts.append(f"{subset}/{wav.stem}")
        tag = tags.get(name, {})
        np.savez_compressed(args.out / f"spk{s:03d}.npz", audio=np.concatenate(audio),
                            audio_len=np.array(lengths), frames=np.array(frames), text=np.array(texts),
                            name=name, gender=tag.get("gender", "?"))
        print(f"{name}: {len(lengths)} utterances, {sum(lengths) / RATE:.0f} s", flush=True)

    vtl = Vtl()
    meta = {"real": True, "corpus": "JVS", "subsets": args.subsets, "speakers": len(names),
            "speaker_names": names, "tags": {n: tags.get(n, {}) for n in names},
            "level_rms": LEVEL_RMS, "noise_floor": float(np.median(floors)),
            "anatomy_names": vtl.anatomy_names, "anatomy_min": vtl.anatomy_min.tolist(),
            "anatomy_max": vtl.anatomy_max.tolist(), "anatomy_reference": vtl.anatomy_reference.tolist(),
            "tract_names": vtl.tract_names, "glottis_names": vtl.glottis_names,
            "glottis_min": vtl.glottis_min.tolist(), "glottis_max": vtl.glottis_max.tolist(),
            "frame_rate": 100, "audio_rate": RATE}
    (args.out / "meta.json").write_text(json.dumps(meta, indent=1))
    print(f"noise floor {meta['noise_floor']:.2e} (level {LEVEL_RMS})")


if __name__ == "__main__":
    main()
