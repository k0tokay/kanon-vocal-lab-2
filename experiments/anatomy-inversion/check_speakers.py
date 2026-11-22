"""Checks whether VTL's anatomy-adapted shapes still make the intended sounds for each synthetic speaker.

Run from this directory: python3 check_speakers.py
For every speaker of data/synth-v1 (and the reference) it measures
- F1-F3 of the five vowel shapes, and
- the minimum oral cross-section of the closure / fricative / flap shapes (closure means area <= 0.001 cm^2,
  the API's minimum),
and writes results/speaker-check.json and results/speaker-check.png.
"""
import ctypes as ct
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.signal import find_peaks

from vtl import Vtl, _ptr

DATA = Path("data/synth-v1")
OUT = Path("results")
VOWELS = ["a", "i", "M", "e", "o"]
CONSONANTS = ["ll-labial-closure(a)", "tt-alveolar-closure(a)", "tb-velar-closure(a)",
              "tt-alveolar-closure(i)", "tb-velar-closure(i)", "tt-alveolar-flap(a)",
              "tt-alveolar-fricative(a)", "tt-postalveolar-fricative(a)"]


def main():
    vtl = Vtl()
    meta = json.loads((DATA / "meta.json").read_text())

    def formants(x, n=8192):
        mag = vtl.transfer_function(x, n)
        db = 20 * np.log10(np.maximum(mag, 1e-12))
        ids, _ = find_peaks(db, prominence=3)
        freq = ids * vtl.rate / n
        freq = freq[(freq > 150) & (freq < 6000)][:3]
        return np.pad(freq, (0, 3 - len(freq)), constant_values=np.nan)

    def min_oral_area(x):
        lengths, areas = np.empty(vtl.sections), np.empty(vtl.sections)
        arts = (ct.c_int * vtl.sections)()
        scalars = [ct.c_double() for _ in range(3)]
        vtl._call("vtlTractToTube", _ptr(np.ascontiguousarray(x)), _ptr(lengths), _ptr(areas), arts,
                  *map(ct.byref, scalars))
        # The oral part starts behind the velum; use the anterior 60 % of the tube.
        start = int(0.4 * vtl.sections)
        return float(np.min(areas[start:]))

    labels = ["reference"] + [f"spk{s:03d}" for s in range(meta["speakers"])]
    anatomies = [np.array(meta["anatomy_reference"])] + [np.load(DATA / f"{l}.npz")["anatomy"] for l in labels[1:]]
    result = []
    for label, anatomy in zip(labels, anatomies):
        vtl.set_anatomy(anatomy)
        row = {"label": label,
               "formants": {v: formants(vtl.shape(v)).round(0).tolist() for v in VOWELS},
               "min_area_cm2": {c: min_oral_area(vtl.shape(c)) for c in CONSONANTS}}
        result.append(row)
    (OUT / "speaker-check.json").write_text(json.dumps(result, indent=1))

    # Summary: closure success rate per consonant shape and vowel-space plot.
    closed = {c: np.mean([r["min_area_cm2"][c] <= 0.0011 for r in result[1:]]) for c in CONSONANTS}
    print("closure/constriction achieved (area <= 0.0011 cm2) share of speakers:")
    for c in CONSONANTS:
        areas = [r["min_area_cm2"][c] for r in result[1:]]
        print(f"  {c:32s} {closed[c]:.2f}  ref {result[0]['min_area_cm2'][c]:.4f}  "
              f"median {np.median(areas):.4f}  max {np.max(areas):.3f}")
    fig, ax = plt.subplots(figsize=(6, 5))
    colors = dict(zip(VOWELS, ["C0", "C1", "C2", "C3", "C4"]))
    for r in result[1:]:
        for v in VOWELS:
            f1, f2, _ = r["formants"][v]
            ax.scatter(f2, f1, s=8, color=colors[v], alpha=0.5)
    for v in VOWELS:
        f1, f2, _ = result[0]["formants"][v]
        ax.scatter(f2, f1, s=120, color=colors[v], edgecolor="k", marker="*", label=f"/{v}/ reference")
    ax.invert_xaxis(); ax.invert_yaxis()
    ax.set_xlabel("F2 [Hz]"); ax.set_ylabel("F1 [Hz]"); ax.legend(fontsize=8)
    ax.set_title("Vowel shapes adapted to 64 random anatomies")
    fig.tight_layout(); fig.savefig(OUT / "speaker-check.png", dpi=150)


if __name__ == "__main__":
    main()
