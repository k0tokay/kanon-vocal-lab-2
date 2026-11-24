"""Rebuild Kanon's consonant shapes: v1.1.0 in, a new speaker file out (v1.1.0 is not touched).

For every consonant and context (a, i, u):
  1. open the lips and the jaw until nothing in front of the constriction is narrower than
     FRONT (the tongue does not move with the jaw in VTL, so this is free),
  2. move the tongue (least change) so that it just makes the constriction at the wanted place,
  3. move it on, away from the context vowel, until the margin equals JD2's,
  4. set the tongue-side parameters that give fricatives their area floor and noise source.

The taps only get step 1. Glottal shapes of the obstruents: GLOTTIS (modal is not touched).

    build.py [out.speaker] [--only s,sh,...]
"""
import json
import re
import sys

from shapelib import *

ROOT = HERE.parents[1]
BASE = ROOT / "speakers/fulkhisa-kanon/fulkhisa-kanon-v1-1-0.speaker"
NEW = ROOT / "speakers/fulkhisa-kanon/fulkhisa-kanon-v1-1-1.speaker"

# relative place, margin (both after JD2), TS2, TS3; TS3 = .893 is Kanon's maximum.
SPEC = {
    "tt-alveolar-fricative":       dict(kind="fric", rel=dict(a=.91, i=.89, u=.90), margin=.22, ts2=0.0, ts3=.893, halfspan=(.05, .05)),
    "tt-alveolopalatal-fricative": dict(kind="fric", rel=dict(a=.85, i=.86, u=.85), margin=.22, ts2=.5, ts3=.893, halfspan=(.06, .05)),
    "tb-palatal-fricative":        dict(kind="fric", rel=dict(a=.76, i=.78, u=.76), margin=.12, ts2=.5, ts3=.4, halfspan=(.08, .06), weight=3.0),
    "tt-alveolar-closure":         dict(kind="stop", margin=.30, halfspan=(.05, .06), rel=dict(a=.90, i=.87, u=.89),
                                         always="i", ifront=.4),
    "tt-postalveolar-closure":     dict(kind="stop", margin=.28, halfspan=(.06, .06)),
    "tb-velar-closure":            dict(kind="stop", margin=.43, halfspan=(.10, .11), lo_front=.15, front=.45,
                                         rel=dict(a=.57, i=.64, u=.58), weight=dict(i=1.0), channel=dict(i=.25), ts2=0.0, always="iu"),
    "ll-labial-closure":           dict(kind="stop", margin=.52),
    "ll-labial-fricative":         dict(kind="lip", area=.12),
}
FRONT = .60
# x_bottom, x_top (cm), chink area (cm2), relative amplitude; see glottis_scan.py. Voiced stops:
# adducted through the closure, so that the intraoral pressure rises slowly enough for voicing.
# Voiceless fricatives: v1.1.0 is hardly wider than its leaky modal shape (x_top .1432).
GLOTTIS = {"voiced-plosive": (.025, .055, .0015, 1.0), "voiceless-fricative": (.17, .17, .03, 0.0)}


def open_front(tr, x, front=FRONT, step=(.15, .05), kmax=8, behind=.945):
    """Lower the jaw and the lower lip in small steps until the teeth and lips are open
    (at most 1.2 deg and 0.4 cm: beyond that it is the tongue tip itself that is in the way)."""
    ja, ld = tr.index("JA", "LD")
    lo, hi, _ = tr.bounds()
    x = x.copy()
    for k in range(kmax):
        r, a, _ = profile(tr, x)
        if a[r > behind].min() >= front:
            break
        x[ja] = max(x[ja] - step[0], -4.0)
        x[ld] = min(x[ld] + step[1], hi[ld])
    return x


def fric(tr, name, ctx, s):
    x, v = tr.shape(f"{name}({ctx})"), tr.shape(ctx)
    t2, t3 = tr.index("TS2", "TS3")
    x = open_front(tr, x)
    # Fit without the area floor (it starts at 0.2), but with the tongue sides nearly up.
    x[t2], x[t3] = min(s["ts2"], .2), min(s["ts3"], .2)
    w = v.copy(); w[t2], w[t3] = x[t2], x[t3]
    y, c = fit(tr, x, w, s["rel"][ctx], .15, s["margin"], halfspan=s["halfspan"], weight=s.get("weight", 6.0))
    y[t2], y[t3] = s["ts2"], s["ts3"]
    return open_front(tr, y), dict(cost=c)


def stop(tr, name, ctx, s):
    x, v = tr.shape(f"{name}({ctx})").copy(), tr.shape(ctx)
    if "ts2" in s:              # tongue sides that rise on the way to /i/ would open the closure (area floor)
        x[tr.index("TS1", "TS2")] = s["ts2"]
    d = describe(tr, x)
    if name.startswith("ll"):
        idx = tr.index("LD")
        lo, hi, _ = tr.bounds()
        for k in range(60):
            if margin(tr, x, v, d["rel"], STOP_OPEN) >= s["margin"]:
                break
            x[idx] = max(x[idx] - .03, lo[idx])
        return x, dict(k=k)
    x = open_front(tr, x, s.get("front", FRONT))
    rel = s["rel"][ctx] if "rel" in s else (d["span"][0] + d["span"][1]) / 2
    if margin(tr, x, v, rel, STOP_OPEN) >= s["margin"] - .02 and ctx not in s.get("always", ""):
        return x, dict(cost=0.0)
    return fit(tr, x, v, rel, .03, s["margin"], free=s.get("free", TONGUE), stop=True, halfspan=s["halfspan"],
               weight=s.get("weight", {}).get(ctx, 6.0), channel=s.get("channel", {}).get(ctx), lo_front=s.get("lo_front", .3),
               rmax=.97 if ctx == "i" and "ifront" in s else .94)


def lip(tr, name, ctx, s):
    """Lip aperture (LD) such that the narrowest section is at the lips with the given area."""
    x = tr.shape(f"{name}({ctx})").copy()
    ld, ja = tr.index("LD", "JA")
    lo, hi, _ = tr.bounds()
    x[ja] = min(x[ja], -3.0)
    a, b = -.3, .6
    for _ in range(30):
        m = (a + b) / 2
        x[ld] = m
        r, ar, _ = profile(tr, x)
        a, b = (m, b) if ar[r > .93].min() < s["area"] else (a, m)
    return x, {}


INDEX = dict(x_bottom=2, x_top=3, chink=4, rel_amp=6)


def edit_glottis(speaker, shape, values, out):
    """Change control parameters of one shape of the Geometric glottis 2025 in a speaker file."""
    s = Path(speaker).read_text()
    k = s.index(f'<shape name="{shape}">', s.index('type="Geometric glottis 2025"'))
    e = s.index("</shape>", k)
    b = s[k:e]
    for n, v in values.items():
        b, c = re.subn(rf'(<control_param index="{INDEX[n]}"[^>]*value=")[-\d.]+', rf"\g<1>{v:.6f}", b)
        assert c == 1, (n, c)
    Path(out).write_text(s[:k] + b + s[e:])
    return out


def main(out=NEW, only=None):
    tr = ctune.vm.Tract(BASE)
    log = {}
    for name, s in SPEC.items():
        if only and name not in only:
            continue
        for ctx in "aiu":
            x0 = tr.shape(f"{name}({ctx})")
            q = dict(fric=fric, stop=stop, lip=lip)[s["kind"]](tr, name, ctx, s)
            x, info = q[0], q[1] if isinstance(q[1], dict) else dict(cost=q[1])
            lo, hi, _ = tr.bounds()
            x = np.clip(x, lo, hi)
            tr.set_shape(f"{name}({ctx})", x)
            d, d0 = describe(tr, x), describe(tr, x0)
            thr = STOP_OPEN if s["kind"] == "stop" else FRIC_OPEN
            v = tr.shape(ctx)
            row = dict(before=dict(area=d0["area"], rel=d0["rel"], front=d0["front_min"], margin=margin(tr, x0, v, d0["rel"], thr)),
                       after=dict(area=d["area"], rel=d["rel"], front=d["front_min"], margin=margin(tr, x, v, d["rel"], thr)),
                       changes={n: [round(float(p), 3), round(float(q), 3)] for n, p, q in zip(tr.names, x0, x) if abs(p - q) > 1e-3}, **info)
            log[f"{name}({ctx})"] = row
            f = lambda q: f"A {q['area']:.3f} @ {q['rel']:.2f} front {q['front']:.2f} margin {q['margin']:.2f}"
            print(f"{name}({ctx}): {f(row['before'])}  ->  {f(row['after'])}   {info}")
            print("      " + "  ".join(f"{n} {p:+.2f}>{q:+.2f}" for n, (p, q) in row["changes"].items()), flush=True)
    for n in tr.shape_names():
        if n.startswith("tt-tap-"):
            tr.set_shape(n, open_front(tr, tr.shape(n)))
    tr.write_speaker(out, BASE)
    for n, v in GLOTTIS.items():
        edit_glottis(out, n, dict(zip(INDEX, v)), out)
    (HERE / "results").mkdir(exist_ok=True)
    (HERE / "results/shapes.json").write_text(json.dumps(log, ensure_ascii=False, indent=1))
    return log


if __name__ == "__main__":
    a = sys.argv[1:]
    only = None
    if "--only" in a:
        only = a[a.index("--only") + 1].split(","); del a[a.index("--only"):a.index("--only") + 2]
    main(Path(a[0]) if a else NEW, only)
