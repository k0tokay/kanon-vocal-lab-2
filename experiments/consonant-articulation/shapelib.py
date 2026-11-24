"""Static measures of a consonant shape and the overshoot ("margin") construction.

VTL reaches a consonant target by a smooth approach, so a shape that only just makes its
constriction holds it for a moment, and releases at the slow start of the return movement.
The margin of a shape is the fraction of the way back to its context vowel that the whole
tract can move before the constriction opens. JD2's shapes have 0.2-0.5; see README.
"""
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "consonant-tuning"))
import ctune                                              # noqa: E402

TONGUE = ["TCX", "TCY", "TTX", "TTY", "TBX", "TBY"]
FRIC_OPEN, STOP_OPEN = .17, 1e-3       # cm^2: above this the constriction counts as opened


def profile(tr, x):
    p, a = tr.area_function(x, 64)
    return p / p[-1], a, p[-1]


def describe(tr, x):
    """Main oral constriction (relative position), and the narrowest place between it and the lips."""
    r, a, L = profile(tr, x)
    keep = np.flatnonzero(r > .45)
    k = keep[np.argmin(a[keep])]
    out = dict(area=float(a[k]), rel=float(r[k]), length=float(L))
    near = a <= a[k] + .02
    i = j = k
    while i > 0 and near[i - 1]:
        i -= 1
    while j < len(a) - 1 and near[j + 1]:
        j += 1
    out["span"] = (float(r[i]), float(r[j]))
    front = np.arange(len(a)) > j + 1
    out["front_min"] = float(a[front].min()) if front.any() else np.nan
    return out


def margin(tr, x, v, rel, threshold, width=.07, step=.01):
    for t in np.arange(0, 1.0001, step):
        r, a, _ = profile(tr, x + t * (v - x))
        if a[abs(r - rel) < width].min() > threshold:
            return float(t)
    return 1.0


def fit(tr, x, v, rel, area, m, free=TONGUE, lo_front=.3, channel=None, halfspan=(.06, .06), stop=False, iterations=70, weight=6.0, seeds=3, rmax=.94):
    """Least-change fit: after moving a fraction m back to the vowel v the section at rel*length
    has `area`, i.e. the constriction has margin m at the wanted place. At x itself nothing
    outside rel -/+ halfspan may be as narrow, and the part in front stays above lo_front
    (channel: lower bound right in front of a velar closure)."""
    lo, hi, _ = tr.bounds()
    idx = tr.index(*free)
    span = (hi - lo)[idx]
    z0 = np.clip((x[idx] - lo[idx]) / span, 0, 1)
    tol = .4 if stop else .15

    def full(z):
        y = x.copy(); y[idx] = lo[idx] + z * span
        return y

    def cost(z):
        y = full(z)
        r, a, _ = profile(tr, y + m * (v - y))
        near = np.abs(r - rel) < .025
        at = min(np.interp(rel, r, a), a[near].min() if near.any() else 9)
        c = (np.log(max(at, 2e-3) / area) / tol) ** 2
        oral = r > .45
        out = oral & (np.abs(r - rel) > .05) & (r < .94)
        c += 2 * (max(0, area * 1.3 - a[out].min()) / area) ** 2       # at the margin: narrowest at rel
        r, a, _ = profile(tr, y)
        bad = (r > .45) & (r < .94) & ((r < rel - halfspan[0]) | (r > rel + halfspan[1]))
        c += np.sum((np.maximum(0, (area if stop else .2) * 1.2 - a[bad]) / max(area, .05)) ** 2) * .5
        f = (r > rel + halfspan[1] + .02) & (r < rmax)
        if f.any() and lo_front:
            c += (max(0, lo_front - a[f].min()) / .1) ** 2
        if channel:
            c += np.sum((np.maximum(0, channel - a[f]) / .06) ** 2) * .3
        return c + weight * np.sum((z - z0) ** 2) / .02

    best_all, c_all = None, np.inf
    for s in range(seeds):
        rng = np.random.default_rng(s)
        best, cb, sig = z0.copy(), cost(z0), .08
        for it in range(iterations):
            cand = np.clip(best + sig * rng.standard_normal((16, len(idx))) * (rng.random((16, len(idx))) < .6), 0, 1)
            cs = [cost(c) for c in cand]
            k = int(np.argmin(cs))
            if cs[k] < cb:
                best, cb, sig = cand[k], cs[k], sig * 1.15
            else:
                sig *= .85
            if sig < .0015:
                break
        if cb < c_all:
            best_all, c_all = best, cb
    return full(best_all), float(c_all)


CONSONANTS = {"tt-alveolar-fricative": FRIC_OPEN, "tt-postalveolar-fricative": FRIC_OPEN,
              "tt-alveolopalatal-fricative": FRIC_OPEN, "tb-palatal-fricative": FRIC_OPEN,
              "ll-labial-fricative": FRIC_OPEN, "tt-alveolar-closure": STOP_OPEN,
              "tt-postalveolar-closure": STOP_OPEN, "tb-velar-closure": STOP_OPEN, "ll-labial-closure": STOP_OPEN}


def static_table(speaker):
    tr = ctune.tract(speaker)
    names, rows = tr.shape_names(), []
    j = tr.names.index("TS3"), tr.names.index("TS2")
    for c, thr in CONSONANTS.items():
        for ctx in "aiu":
            s = f"{c}({ctx})"
            if s not in names:
                continue
            x = tr.shape(s); d = describe(tr, x)
            rows.append(dict(shape=s, area=d["area"], rel=d["rel"], span=d["span"], front_min=d["front_min"],
                             TS2=float(x[j[1]]), TS3=float(x[j[0]]), margin=margin(tr, x, tr.shape(ctx), d["rel"], thr)))
    return rows


if __name__ == "__main__":
    for spk in sys.argv[1:]:
        print(spk)
        for r in static_table(spk):
            print(f"  {r['shape']:34s} A {r['area']:.3f} @ {r['rel']:.2f} ({r['span'][0]:.2f}-{r['span'][1]:.2f})"
                  f"  front min {r['front_min']:.2f}  TS2 {r['TS2']:.2f} TS3 {r['TS3']:.2f}  margin {r['margin']:.2f}")
