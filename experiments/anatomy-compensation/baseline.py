"""Formants that the target anatomies give with their own vowels.

* W02 raw: W02.speaker's /a i u/ in its own (MRI) anatomy.
* W02 13-param: the same parameter values in the anatomy rebuilt from W02's
  13 anatomy parameters (what compensate.py moves towards).
* F15 VTL: VTL's template vowels (built-in reference) adapted to the 15-year
  female anatomy, as the GUI does.
* Kanon: Kanon's vowels, for comparison.

Run from the repository root: python3 experiments/anatomy-compensation/baseline.py
"""
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "vtlmap"))
import vtlmap as vm  # noqa: E402
from compensate import OUT, ROOT, SPEAKER, targets  # noqa: E402

VOWELS = ["a", "i", "u"]


def formants(tract, shapes):
    out = {}
    for v, x in shapes.items():
        f, _, area, n = tract.peaks(x, 3)
        out[v] = dict(F=np.round(f, 1).tolist(), min_area=round(area, 3), found=n)
    return out


def main():
    vm.set_reference(None)
    rows = {}
    kanon = vm.Tract(SPEAKER)
    rows["Kanon"] = formants(kanon, {v: kanon.shape(v) for v in VOWELS})
    w02 = vm.Tract(ROOT / "speakers/W02.speaker")
    shapes = {v: w02.shape(v) for v in VOWELS}
    rows["W02 raw"] = formants(w02, shapes)
    w13 = vm.Tract(ROOT / "speakers/W02.speaker")
    w13.set_anatomy(w02.anatomy())
    rows["W02 13-param"] = formants(w13, shapes)
    # VTL's template vowels: JD2 (≈ built-in reference) shapes adapted to F15.
    jd2 = vm.Tract(ROOT / "speakers/JD2.speaker")
    theta_ref = jd2.anatomy()
    f15 = vm.Tract(ROOT / "speakers/JD2.speaker")
    theta = vm.restrict_anatomy(targets()["F15"]["theta"])
    f15.set_anatomy(theta)
    rows["F15 VTL"] = formants(f15, {v: vm.adapt(theta, vm.unadapt(theta_ref, jd2.shape(v))) for v in VOWELS})
    rows["JD2 raw"] = formants(jd2, {v: jd2.shape(v) for v in VOWELS})
    (OUT / "baseline.json").write_text(json.dumps(rows, indent=1))
    print(f"{'':14s}" + "".join(f"{'/' + v + '/ F1-F3':>22s}" for v in VOWELS))
    for k, r in rows.items():
        print(f"{k:14s}" + "".join(f"{'%5.0f %5.0f %5.0f' % tuple(r[v]['F']):>22s}" for v in VOWELS))


if __name__ == "__main__":
    main()
