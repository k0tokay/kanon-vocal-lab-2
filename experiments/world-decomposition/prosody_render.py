"""Kanon speaking test sentences with the prosody of each predictor (run in the pyopenjtalk-plus env).

    KANON=v1-1-3 VTL_LIB=... python prosody_render.py texts.json out/prosody-jvs.pkl predictions-dir outdir
Conditions: rule (accent.py, see prosody_render_rule), fit (fitted rule F0), vvF (VOICEVOX F0 on the rule's
timing), vv (VOICEVOX F0, durations and pauses), jvs (mean F0, durations and pauses of 51 JVS women).
The mean log F0 over the moras is 218 Hz in every condition.
"""
import contextlib
import io
import json
import os
import pickle
import sys
from pathlib import Path

import numpy as np
from scipy.interpolate import PchipInterpolator

HERE = Path(__file__).resolve().parent
os.environ.setdefault("VTL_SPEAKER", str(HERE.parents[1] / f"speakers/fulkhisa-kanon/fulkhisa-kanon-{os.environ.get('KANON', 'v1-1-3')}.speaker"))
sys.path.insert(0, str(HERE.parent / "japanese-accent"))
import accent                                     # noqa: E402
from prosody_eval import lev, reference            # noqa: E402

MEAN = 218.0
KEY = lambda c, v: (c, v.lower() if v != "cl" else v)


def pick(R, preds, n=6):
    """The first even sentences of 18-38 moras that every front end reads as recorded."""
    out = []
    for u in sorted(R):
        a = [KEY(*q) for q in R[u]["mora"]]
        if int(u) % 2 == 0 and 18 <= len(a) <= 38 and all([KEY(q[0], q[1]) for q in p[u]] == a for p in preds):
            out.append(u)
    return out[:n]


def build(text, cond, pred, ref, q, u):
    """Segments with the requested F0 and timing; q = fitted Fujisaki parameters."""
    units = accent.parse(text); segs, spans = accent.to_segments(units)
    p = accent.Fujisaki(**q) if cond == "fit" else accent.Fujisaki()
    ph, ac = accent.commands(units, spans, p)
    moras = [(m, s) for m, s in zip(units, spans) if isinstance(m, accent.Mora)]
    # Vowel onset of every mora on the rule's timeline.
    vowel_on = []
    for m, (a, b) in moras:
        own = [s for s in segs if a - 1e-6 <= s.t0 < b - 1e-6]
        vowel_on.append(own[-1].t0 if m.consonant and len(own) > 1 else a)
    src = {"vvF": pred, "vv": pred, "jvs": ref}.get(cond)
    new = None
    if cond in ("vv", "jvs"):
        K = src["time"]; t = 0.0; old, nw = [0.0], [0.0]
        i = 0
        for un, (a, b) in zip(units, spans):
            if isinstance(un, accent.Pause):
                d = b - a
                if i and i < len(moras): d = K[i - 1][2]
                d = max(d, .1) if i == 0 else max(d, .03)
                t += d; old.append(b); nw.append(t); continue
            c, v, _ = K[i]
            if un.consonant and vowel_on[i] > a + 1e-6:
                old.append(vowel_on[i]); nw.append(t + c)
            t += c + v; old.append(b); nw.append(t); i += 1
        warp = lambda x: np.interp(x, old, nw)
        for s in segs:
            s.t0, e = float(warp(s.t0)), float(warp(s.t0 + s.duration)); s.duration = max(e - s.t0, .015)
        moras = [(m, (float(warp(a)), float(warp(b)))) for m, (a, b) in moras]; vowel_on = [float(warp(x)) for x in vowel_on]
    if cond in ("rule", "fit"):
        F = lambda tt: 12 * np.log2(accent.f0_curve(np.atleast_1d(tt), ph, ac, p) / 100)
    else:
        kx, ky = [], []
        for (m, (a, b)), v0, f in zip(moras, vowel_on, src["f0"]):
            if f is not None and m.vowel in "aiueoN":
                kx.append((v0 + b) / 2); ky.append(f)
        pc = PchipInterpolator(kx, ky)
        F = lambda tt: pc(np.clip(np.atleast_1d(tt), kx[0], kx[-1]))
    mid = np.array([float(F((v0 + s[1]) / 2)[0]) for (m, s), v0 in zip(moras, vowel_on) if m.vowel in "aiueoN"])
    shift = 12 * np.log2(MEAN / 100) - mid.mean()
    for s in segs:
        tt = np.array([s.t0 + r * s.duration for r in (.2, .5, .8)])
        s.f0 = [float(100 * 2 ** ((f + shift) / 12)) for f in F(tt)]
    # Contiguous times after the warp.
    t = 0.0
    for s in segs:
        s.t0 = t; t += s.duration
    return segs


if __name__ == "__main__":
    texts = json.load(open(sys.argv[1])); R = reference(pickle.load(open(sys.argv[2], "rb"))); pd = Path(sys.argv[3]); od = Path(sys.argv[4]); od.mkdir(parents=True, exist_ok=True)
    P = {n: json.load(open(pd / f"pred-{n}.json")) for n in ("vv-metan-plus", "vv-metan", "rule-venv", "rule-venv-plus")}
    q = json.load(open(pd / "fit.json")); utts = pick(R, P.values()); print(utts)
    al = pickle.load(open(sys.argv[2], "rb"))["jvs"]
    from prosody_eval import moras_of
    info = {}
    for u in utts:
        M = [moras_of(r[u]["spans"]) for r in al.values() if u in r]
        cons = np.mean([[m[2] - m[4] for m in x] for x in M], 0); vow = np.mean([[m[3] - m[2] for m in x] for x in M], 0); pa = np.median([[m[5] for m in x] for x in M], 0)
        ref = dict(f0=[float(y) if ok else None for y, ok in zip(R[u]["mean"], R[u]["ok"])], time=list(zip(cons, vow, np.maximum(pa, .03))))
        V = P["vv-metan-plus"][u]
        pred = dict(f0=[x[2] for x in V], time=[(x[5], x[6], x[4] or .03) for x in V])
        for c in ("fit", "vvF", "vv", "jvs"):
            segs = build(texts[u]["text"], c, pred, ref, q, u)
            seg = od / f"{u}-{c}.seg"; accent.write_seg(segs, seg)
            with contextlib.redirect_stdout(io.StringIO()):
                accent.synthesize(seg, seg.with_suffix(".wav"), segs)
            info[f"{u}-{c}"] = round(segs[-1].t0 + segs[-1].duration, 2)
    (od / "info.json").write_text(json.dumps(info)); (od / "utts.json").write_text(json.dumps(utts)); print(info)
