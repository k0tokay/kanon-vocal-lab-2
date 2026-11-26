"""Markdown table of the variants for the README (from build/diag/*/rows.json and the consonant checks).

    ./run.sh table.py variant ...
"""
import json, sys
from pathlib import Path
import numpy as np
import diag

CONS = Path(__file__).resolve().parent / "results/consonants"     # from compare.py / compare_edit.py, moved here


def early_drop(v, rows, group="after_voiceless"):
    logs = {k: diag.load(diag.OUT / v / f"{k}.f32") for k in diag.SENTENCES}
    d = []
    for r in rows:
        if not diag.GROUPS[group](r["prev"]):
            continue
        t0, t1 = r["t0"], r["t1"]
        m = diag.measure(logs[r["key"]], t0 + .05 * (t1 - t0), t0 + .5 * (t1 - t0))
        w = .45 * (t1 - t0) / 2
        q = diag.measure(diag.load(diag.OUT / v / f"steady-{r['vowel']}-{r['f0r']:.0f}.f32"), .6 - w, .6 + w)
        d.append(m["drop"] - q["drop"])
    return np.mean(d)


def consonants(v):
    label = "v141" if v == "base" else v
    p = CONS / f"compare-{label}.json"
    if not p.exists():
        return np.nan
    d = json.loads(p.read_text())
    return np.mean([abs(x["z"]) for c in d.values() for x in c.values()])


def main(names):
    print("| 版 | F0 誤差 (半音) | ΔH1−H2 (dB) | ΔCQ | Δ落ち (dB) | Δ漏れ (cm³/s) | 無声の後 Δ落ち 中 / 前半 (dB) | 有声子音の後 TA / IA | レベルの F0 依存 (dB/半音) | 子音 |z| |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for v in names:
        rows = json.loads((diag.OUT / v / "rows.json").read_text())
        S, Q = (lambda k: np.array([r["sent"][k] for r in rows])), (lambda k: np.array([r["steady"][k] for r in rows]))
        st = 12 * np.log2(S("f0_target") / 220)
        uv = [r for r in rows if diag.GROUPS["after_voiceless"](r["prev"])]
        vc = [r for r in rows if diag.GROUPS["after_voiced_consonant"](r["prev"])]
        print(f"| {v} | {np.nanmean(abs(S('f0_err'))):.2f} | {np.mean(abs(S('h1h2') - Q('h1h2'))):.2f} | {np.mean(abs(S('cq') - Q('cq'))):.3f} | "
              f"{np.mean(abs(S('drop') - Q('drop'))):.2f} | {np.mean(S('dc') - Q('dc')):+.2f} | "
              f"{np.mean([r['sent']['drop'] - r['steady']['drop'] for r in uv]):+.1f} / {early_drop(v, rows):+.1f} | "
              f"{np.mean([r['sent']['ta'] for r in vc]):.2f} / {np.mean([r['sent']['ia'] for r in vc]):.2f} | "
              f"{np.polyfit(st, S('level'), 1)[0]:+.2f} | {consonants(v):.2f} |")


if __name__ == "__main__":
    main(sys.argv[1:])
