"""Steady vowels over F0: how the voice changes with F0 alone (hypothesis b).

    ./run.sh sweep.py [variant ...]
"""
import sys
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import diag
import variants

F0 = [165, 185, 205, 220, 235, 255, 280, 310]
VOWELS = ["a", "i", "o"]


def sweep(name, f0s=F0, vowels=VOWELS):
    v = dict(variants.VARIANTS[name])
    v["name"] = "sweep-" + name
    speaker = v.get("speaker", diag.SPEAKER)
    jobs = {}
    for vw in vowels:
        for f in f0s:
            g = diag.steady(vw, f, v, speaker)
            if v.get("edit"):
                v["edit"](g, [("", 0, .15), (vw, .15, 1.05), ("", 1.05, 1.2)])
            jobs[(vw, f)] = g
    with ThreadPoolExecutor(8) as ex:
        fut = {k: ex.submit(diag.probe, g, g.with_suffix(".f32"), speaker, v.get("static", ())) for k, g in jobs.items()}
        res = {k: diag.measure(f.result(), .45, .85) for k, f in fut.items()}
    return res


def table(name, res, vowels=VOWELS, f0s=F0):
    print(f"\n== {name}: mean over {', '.join(vowels)}")
    keys = ["f0_err", "h1h2", "cq", "drop", "level", "ac", "dc", "strain", "pressure"]
    print("F0   " + "".join(f"{k:>9}" for k in keys))
    for f in f0s:
        print(f"{f:<5}" + "".join(f"{np.mean([res[(v, f)][k] for v in vowels]):9.3f}" for k in keys))


if __name__ == "__main__":
    for n in sys.argv[1:] or ["base"]:
        table(n, sweep(n))
