"""A larger Kanon with the same articulation: scale.py, then what absolute areas disturb is put back.

    build.py <k> [out.speaker] [--no-polish] [--glottis=other.speaker]   (the glottis models of another speaker file)

A closure, a place of articulation and the opening of the jaw and lips survive the scaling by itself.
What does not is how long a constriction holds: areas grow by k^2, but a fricative channel is one below
the same 0.17 cm2 and the tongue-side floors (shapelib) stay. So
  * fricatives and stops whose margin (fraction of the way back to the vowel before the constriction
    opens) fell below the original's, capped at the value build.py of consonant-articulation asked for,
    are fitted again: least tongue movement, same place, same margin;
  * ll-labial-fricative: the lips go back to the original's 0.12 cm2;
  * the lateral gap of the taps grows with the rest of the mouth (area x k^2, through TS3).
Writes out/log-<k>.json.
"""
import json
import multiprocessing
import sys

import numpy as np

from scale import *

sys.path.insert(0, str(HERE.parent / "consonant-articulation"))
import shapelib as sl                          # noqa: E402
from build import SPEC  # noqa: E402  (consonant-articulation/build.py)

OUT = HERE / "out"
TOL = .03


def target(name, ctx, base):
    """What the original has: place and margin (capped at SPEC's)."""
    s, x = SPEC[name], base.shape(f"{name}({ctx})")
    d = sl.describe(base, x)
    thr = sl.STOP_OPEN if s["kind"] == "stop" else sl.FRIC_OPEN
    return d["rel"], min(sl.margin(base, x, base.shape(ctx), d["rel"], thr), s["margin"]), thr


def job(a):
    path, name, ctx = a
    s = SPEC[name]
    base, tr = sl.ctune.vm.Tract(BASE), sl.ctune.vm.Tract(path)
    shape = f"{name}({ctx})"
    x, v = tr.shape(shape).copy(), tr.shape(ctx)
    rel, m, thr = target(name, ctx, base)
    m0 = sl.margin(tr, x, v, sl.describe(tr, x)["rel"], thr)
    if name.startswith("ll") or m0 >= m - TOL:
        return shape, x, dict(margin=[m, m0, m0], moved={})
    t2, t3 = tr.index("TS2", "TS3")
    # fit toward a slightly larger margin: the fit holds an area (.15) below the threshold (.17)
    def fit(goal):
        y, w = x.copy(), v.copy()
        if s["kind"] == "fric":
            y[t2], y[t3] = min(x[t2], .2), min(x[t3], .2)
            w[t2], w[t3] = y[t2], y[t3]
            y, _ = sl.fit(tr, y, w, rel, .15, goal, halfspan=s["halfspan"], weight=s.get("weight", 6.0))
            y[t2], y[t3] = x[t2], x[t3]
        else:
            y, _ = sl.fit(tr, y, w, rel, .03, goal, stop=True, halfspan=s["halfspan"], weight=s.get("weight", {}).get(ctx, 6.0),
                          channel=s.get("channel", {}).get(ctx), lo_front=s.get("lo_front", .3), rmax=.94)
        return y
    best = None
    for goal in (m, m + .06, m + .12):
        y = fit(goal)
        d = sl.describe(tr, y)
        my = sl.margin(tr, y, v, d["rel"], thr)
        bad = max(0, m - TOL - my) / .05 + abs(d["rel"] - rel) / .03
        if best is None or bad < best[0]:
            best = bad, y, my
        if bad < .5 and my >= m - TOL:
            break
    _, y, my = best
    if my < m0 + TOL or abs(sl.describe(tr, y)["rel"] - rel) > .03:      # the place matters more than the margin
        return shape, x, dict(margin=[m, m0, m0], moved={}, failed=True)
    for t in np.arange(.1, 1, .1):             # only as far toward the fit as the margin needs
        q = x + t * (y - x)
        d = sl.describe(tr, q)
        if sl.margin(tr, q, v, d["rel"], thr) >= m and abs(d["rel"] - rel) <= .03:
            y, my = q, sl.margin(tr, q, v, d["rel"], thr)
            break
    return shape, y, dict(margin=[m, m0, my], moved={n: round(float(q - p), 3) for n, p, q in zip(tr.names, x, y) if abs(p - q) > 1e-3})


def lips(tr, ctx, area):
    x = tr.shape(f"ll-labial-fricative({ctx})").copy()
    ld = tr.index("LD")
    a, b = -.3, .8
    for _ in range(30):
        x[ld] = (a + b) / 2
        r, ar, _ = sl.profile(tr, x)
        a, b = (x[ld][0], b) if ar[r > .93].min() < area else (a, x[ld][0])
    return x


def build(k, out, polish=True, lip=True, tap=True):
    scaled(k, out)
    if not polish:
        return {}
    tr, base = sl.ctune.vm.Tract(out), sl.ctune.vm.Tract(BASE)
    jobs = [(out, n, c) for n, s in SPEC.items() for c in "aiu" if s["kind"] != "lip"]
    log = {}
    with multiprocessing.Pool(8) as pool:
        for shape, x, info in pool.imap(job, jobs):
            log[shape] = info
            tr.set_shape(shape, x)
    for c in "aiu" if lip else "":
        r, a, _ = sl.profile(base, base.shape(f"ll-labial-fricative({c})"))
        tr.set_shape(f"ll-labial-fricative({c})", lips(tr, c, a[r > .93].min()))
    if tap:
        t3 = tr.index("TS3")
        for n in tr.shape_names():
            if n.startswith("tt-tap-"):
                x = tr.shape(n).copy()
                x[t3] = -.2 + k * k * (x[t3] + .2)
                tr.set_shape(n, x)
    tr.write_speaker(out, out)
    return log


if __name__ == "__main__":
    a = [q for q in sys.argv[1:] if not q.startswith("--")]
    k = float(a[0])
    out = Path(a[1]) if len(a) > 1 else OUT / f"k{k:g}.speaker"
    log = build(k, out, "--no-polish" not in sys.argv)
    for q in sys.argv[1:]:
        if q.startswith("--glottis="):
            sl.ctune.vm.Tract(out).write_speaker(out, Path(q.split("=", 1)[1]))
    (OUT / f"log-{k:g}.json").write_text(json.dumps(log, indent=1))
    for s, i in log.items():
        if i["moved"] or i.get("failed"):
            print(f"{s:32s} margin {i['margin'][0]:.2f} scaled {i['margin'][1]:.2f} -> {i['margin'][2]:.2f}", i["moved"], "FAILED" if i.get("failed") else "", flush=True)
