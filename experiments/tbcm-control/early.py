"""Sentence vowels against steady vowels in the first half of the vowel (right after the consonant).

    ./run.sh early.py variant ...    (uses the logs of diag.py)
"""
import json, sys
import numpy as np
import diag


def main(names):
    print(f"{'variant':22}{'group':>24}{'n':>4}{'dH1H2':>8}{'dCQ':>8}{'dDrop':>8}{'dLeak':>8}{'TA':>7}{'IA':>7}")
    for v in names:
        rows = json.loads((diag.OUT / v / "rows.json").read_text())
        logs = {k: diag.load(diag.OUT / v / f"{k}.f32") for k in diag.SENTENCES}
        acc = {}
        for r in rows:
            g = next(g for g, sel in diag.GROUPS.items() if sel(r["prev"]))
            t0, t1 = r["t0"], r["t1"]
            m = diag.measure(logs[r["key"]], t0 + .05 * (t1 - t0), t0 + .5 * (t1 - t0))
            w = .45 * (t1 - t0) / 2
            q = diag.measure(diag.load(diag.OUT / v / f"steady-{r['vowel']}-{r['f0r']:.0f}.f32"), .6 - w, .6 + w)
            acc.setdefault(g, []).append([m["h1h2"] - q["h1h2"], m["cq"] - q["cq"], m["drop"] - q["drop"], m["dc"] - q["dc"], m["ta"], m["ia"]])
        for g, a in acc.items():
            a = np.array(a)
            print(f"{v:22}{g:>24}{len(a):4d}" + "".join(f"{x:8.2f}" for x in a[:, :4].mean(0)) + "".join(f"{x:7.3f}" for x in a[:, 4:].mean(0)))


if __name__ == "__main__":
    main(sys.argv[1:])
