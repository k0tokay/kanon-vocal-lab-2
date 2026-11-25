"""Render Kanon: rule prosody ("rule") and the timing + F0 of one JVS recording ("copy")."""
import contextlib
import io

import numpy as np
from scipy.io import wavfile
from scipy.signal import medfilt

from common import *
import accent


def read_wav(path):
    rate, x = wavfile.read(path)
    return level(to16(x / 32768.0, rate))


def rule(text, stem):
    stem.parent.mkdir(parents=True, exist_ok=True)
    r = accent.render(text, stem, f0_model=None)
    return read_wav(stem.with_suffix(".wav")), r


def find_pauses(x16, min_len=.15):
    """Silent stretches (frames of 5 ms), more than 35 dB below the active level."""
    h = int(RS * HOP_MS / 1000)
    n = len(x16) // h
    e = 10 * np.log10(np.convolve(np.mean(x16[:n * h].reshape(n, h) ** 2, 1), np.ones(5) / 5, "same") + 1e-12)
    low = e < 20 * np.log10(RMS) - 35
    edges = np.flatnonzero(np.diff(np.r_[0, low.astype(int), 0]))
    return [(a, b) for a, b in edges.reshape(-1, 2) if (b - a) * HOP_MS / 1000 >= min_len], n


def copy(text, stem, real16, P_real, rounds=3, cuts=None):
    """Time-align rule synthesis to the recording, then resynthesise with its timing and F0.

    cuts: segment index after which each recorded pause falls (otherwise the nearest vowel end
    of the DTW, which can be a mora or two off); the boundary is then pinned to the pause."""
    stem.parent.mkdir(parents=True, exist_ok=True)
    units = accent.parse(text)
    segs, _ = accent.to_segments([u for u in units if not (isinstance(u, accent.Pause) and u.kind == "pau")])
    segs = [s for s in segs]
    pauses, _ = find_pauses(real16)
    N = len(P_real["f0"])
    speech = np.ones(N, bool)
    inner = []
    for a, b in pauses:
        speech[a:b] = False
        if a > 5 and b < N - 25:
            inner.append((a, b))
    lo, hi = np.flatnonzero(speech)[[0, -1]]
    idx = np.flatnonzero(speech)                      # speech frames on the real timeline
    lf = np.log(clean_f0(P_real["f0"]))
    F_real = feats({k: P_real[k][idx] for k in ("f0", "sp")})
    durs = np.array([s.duration for s in segs])       # segs[0], segs[-1] are the outer pauses
    core = np.arange(1, len(segs) - 1)
    hop = HOP_MS / 1000
    scale = len(idx) * hop / durs[core].sum()
    bounds = np.r_[0, np.cumsum(durs[core] * scale)]  # on the pause-free real timeline
    score = None
    pins = {}
    if cuts is not None:
        assert len(cuts) == len(inner), (cuts, inner)
        pins = {k: np.searchsorted(idx, a) * hop for k, (a, b) in zip(cuts, inner)}
    for it in range(rounds):
        d = np.maximum(np.diff(bounds), .018)
        bounds = np.r_[0, np.cumsum(d)]
        bounds *= len(idx) * hop / bounds[-1]
        if pins:
            q = [0, *pins, len(core)]
            bounds = np.interp(bounds, bounds[q], [0, *pins.values(), bounds[-1]])
        path = stem.with_suffix(".seg")
        write(segs, core, bounds, inner, idx, lf, lo, N, path, it == rounds - 1, pins)
        if it == rounds - 1:
            break
        with contextlib.redirect_stdout(io.StringIO()):
            accent.synthesize(path, stem.with_suffix(".wav"), segs)
        v = read_wav(stem.with_suffix(".wav"))
        Pv = analyse(v)
        Fv = feats(Pv)
        a = int(round(segs[0].duration / hop)); m = len(idx)
        Fv = Fv[a:a + m]
        path_map, score = dtw(Fv, F_real, band=.25 if it == 0 else .1)
        bounds = np.interp(bounds / hop, np.arange(len(path_map)), path_map) * hop
        bounds[0], bounds[-1] = 0, m * hop
    with contextlib.redirect_stdout(io.StringIO()):
        accent.synthesize(stem.with_suffix(".seg"), stem.with_suffix(".wav"), final_segs(segs))
    return read_wav(stem.with_suffix(".wav")), final_segs(segs), score


def clean_f0(f0, shortest=6):
    """Voiced runs of at least 30 ms, median-filtered, interpolated across the rest."""
    e = np.flatnonzero(np.diff(np.r_[0, (f0 > 0).astype(int), 0])).reshape(-1, 2)
    g = np.zeros_like(f0)
    for a, b in e:
        if b - a >= shortest:
            g[a:b] = medfilt(np.pad(f0[a:b], 3, mode="edge"), 7)[3:-3]
    return voiced_interp(g)


_final = {}


def final_segs(segs):
    return _final.get(id(segs), segs)


def write(segs, core, bounds, inner, idx, lf, lo, N, path, with_pauses, pins=()):
    """Write the seg file; on the last round put the recorded pauses back in."""
    hop = HOP_MS / 1000
    if not with_pauses:
        t = segs[0].t0 = 0.0
        segs[0].duration = t = .12
        for k, i in enumerate(core):
            s = segs[i]; s.t0, s.duration = t, bounds[k + 1] - bounds[k]; t += s.duration
            s.f0 = [f0_at(bounds[k] + r * s.duration, idx, lf) for r in (.2, .5, .8)]
        segs[-1].t0, segs[-1].duration = t, .1
        accent.write_seg(segs, path)
        return
    # Boundary after which each recorded pause falls: nearest vowel end.
    real = lambda b: idx[min(int(round(b / hop)), len(idx) - 1)] * hop
    ends = [k for k in range(1, len(core)) if segs[core[k - 1]].name in list("aiueoMmnN")]
    cut = {}
    for a, b in inner:
        p = np.searchsorted(idx, a) * hop
        k = min(pins or ends, key=lambda q: abs(bounds[q] - p))
        cut[k] = (b - a) * hop, p
    for k, (_, p) in cut.items():
        bounds[k] = p
    bounds[:] = np.maximum.accumulate(bounds)
    out, t = [], lo * hop
    # VTL stretches a first pause below 100 ms but leaves the F0 gestures where they were.
    first = accent.Segment("", max(t, .12), 0.0); out.append(first); t = first.duration
    for k, i in enumerate(core):
        if k in cut:
            out.append(accent.Segment("", cut[k][0], t)); t += cut[k][0]
        s = segs[i]; d = max(bounds[k + 1] - bounds[k], .018)
        out.append(accent.Segment(s.name, d, t, [f0_at(bounds[k] + r * d, idx, lf) for r in (.2, .5, .8)], s.tag))
        t += d
    out.append(accent.Segment("", max(.05, N * hop - t), t))
    accent.write_seg(out, path)
    _final[id(segs)] = out


def f0_at(b, idx, lf):
    return float(np.exp(np.interp(b / (HOP_MS / 1000), np.arange(len(idx)), lf[idx])))
