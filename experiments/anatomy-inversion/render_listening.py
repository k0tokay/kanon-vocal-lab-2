"""Renders the same Japanese phrase with the anatomy of selected synthetic speakers.

Run from this directory: python3 render_listening.py [SPEAKER ...]
Writes results/listening/*.wav (16 kHz) and an index. Every file uses the same f0 contour,
so only the anatomy (and the articulation adapted to it by VTL) differs.
"""
import json
import sys
from pathlib import Path

import numpy as np
from scipy.io.wavfile import write

import synth
from gen_dataset import f0_contour

DATA = Path("data/synth-v1")
OUT = Path("results/listening")
PHRASE = [("", 0.1), ("k", 0.06), ("o", 0.1), ("N", 0.08), ("n", 0.05), ("i", 0.09), ("tS", 0.08), ("i", 0.09),
          ("w", 0.05), ("a", 0.15), ("", 0.12), ("w", 0.05), ("a", 0.1), ("t", 0.06), ("a", 0.09), ("S", 0.09),
          ("i", 0.09), ("w", 0.05), ("a", 0.1), ("k", 0.06), ("a", 0.09), ("n", 0.05), ("o", 0.1), ("N", 0.08),
          ("d", 0.05), ("e", 0.09), ("s", 0.1), ("M", 0.12), ("", 0.1)]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    meta = json.loads((DATA / "meta.json").read_text())
    speakers = [int(s) for s in sys.argv[1:]] or [37, 42, 14, 31, 21, 13]
    synth._init()
    vtl = synth._vtl
    f0_index = vtl.glottis_names.index("f0")
    contour_rng = np.random.default_rng(1)
    entries = [("reference", np.array(meta["anatomy_reference"]))]
    entries += [(f"spk{s:03d}", np.load(DATA / f"spk{s:03d}.npz")["anatomy"]) for s in speakers]
    contour = None
    gap = np.zeros(int(0.5 * synth.AUDIO_RATE), dtype=np.float32)
    joined, index = [], []
    for label, anatomy in entries:
        applied, tract, glottis, _, _ = synth._score_frames((anatomy, PHRASE))
        if contour is None:
            contour = f0_contour(contour_rng, len(glottis), 220.0)
        n = min(len(contour), len(glottis))
        tract, glottis = tract[:n], glottis[:n].copy()
        glottis[:, f0_index] = contour[:n]
        audio = synth._render(applied, tract, glottis)
        peak = float(np.max(np.abs(audio)))
        scaled = audio / max(peak, 1e-9) * 0.8
        write(OUT / f"phrase-{label}.wav", synth.AUDIO_RATE, (scaled * 32767).astype(np.int16))
        # The speaker's own first corpus utterance (with its own f0), for comparison.
        if label != "reference":
            d = np.load(DATA / f"{label}.npz")
            own = d["audio"][: d["audio_len"][0]]
            write(OUT / f"corpus-{label}.wav", synth.AUDIO_RATE,
                  (own / max(np.max(np.abs(own)), 1e-9) * 0.8 * 32767).astype(np.int16))
        joined += [scaled, gap]
        index.append({"label": label, "peak_raw": peak, "anatomy": dict(zip(meta["anatomy_names"], np.round(applied, 3).tolist()))})
    write(OUT / "phrase-all.wav", synth.AUDIO_RATE, (np.concatenate(joined) * 32767).astype(np.int16))
    (OUT / "index.json").write_text(json.dumps(index, indent=1))
    print(json.dumps([{k: e[k] for k in ("label", "peak_raw")} for e in index]))


if __name__ == "__main__":
    main()
