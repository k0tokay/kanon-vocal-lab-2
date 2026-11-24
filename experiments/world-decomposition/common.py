"""Shared pieces: JVS loading, WORLD analysis/synthesis, DTW and the Kanon version under test.

Everything is analysed at 24 kHz after a common 16 kHz band limit, because JVS is
stored at 16 kHz: at 16 kHz D4C returns a single aperiodicity band (3 kHz), at
24 kHz it returns 3, 6 and 9 kHz. The 9 kHz band is empty here and is not reported.
"""
import os
import sys
from pathlib import Path

import numpy as np
import pyworld as pw
from scipy.fft import dct
from scipy.signal import resample_poly

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
JVS = Path(os.environ.get("JVS_NPZ", ROOT.parent /
           "voice-articulation-parameter-estimation-89f316/experiments/anatomy-inversion/data/jvs-v1"))
VER = os.environ.get("KANON", "v1-1-3")          # speaker version; results and audio are kept per version
LABEL = VER.replace("-", ".")
OUT = HERE / "out" / VER
os.environ.setdefault("VTL_SPEAKER", str(ROOT / f"speakers/fulkhisa-kanon/fulkhisa-kanon-{VER}.speaker"))
sys.path.insert(0, str(ROOT / "experiments/japanese-accent"))

RS, FS, HOP_MS, FFT = 16000, 24000, 5.0, 2048
RMS = 0.05

# voiceactress100 (voice-statistics.github.io, CC-BY-SA 4.0); commas and one reading
# are ours, pauses in the recordings are found from the audio.
SENTENCES = {
    "001": "また、東寺のように、五大明王と呼ばれる、主要な明王の中央に配されることも多い。",
    "009": "また、禰寝氏は、中山王の治める琉球王国との交易にも参加した。",
    "012": "構造は、はがね製の単一アーチで、橋脚は石積みである。",
    "013": "そこへ、オーナーが、新しいシェフとして、腕利きのヒョヌクを招く。",
    "017": "ただし、ギャンブル依存症の入院治療をおこなっている病院は、わずかである。",
}


def active_rms(x):
    n = len(x) // 160
    e = np.mean(x[:n * 160].reshape(n, 160) ** 2, 1)
    return np.sqrt(e[e > e.max() * 1e-3].mean())


def level(x):
    return x * (RMS / active_rms(x))


def load_jvs(name, utterances):
    d = np.load(JVS / f"spk{int(name[3:]) - 1:03d}.npz")
    assert str(d["name"]) == name
    texts = [t.split("/")[-1] for t in d["text"]]
    offs = np.concatenate([[0], np.cumsum(d["audio_len"])])
    audio = d["audio"]
    out = {}
    for u in utterances:
        key = f"VOICEACTRESS100_{u}"
        if key in texts:
            k = texts.index(key)
            out[u] = level(audio[offs[k]:offs[k + 1]].astype(np.float64))
    return out


def to16(x, rate):
    g = np.gcd(rate, RS)
    return resample_poly(x, RS // g, rate // g)


def analyse(x16, floor=90.0, ceil=600.0):
    """F0 (Harvest + StoneMask), CheapTrick envelope and D4C aperiodicity."""
    x = np.ascontiguousarray(resample_poly(x16, 3, 2))
    f0, t = pw.harvest(x, FS, f0_floor=floor, f0_ceil=ceil, frame_period=HOP_MS)
    f0 = pw.stonemask(x, f0, t, FS)
    f0[(f0 < floor) | (f0 > ceil)] = 0
    sp = pw.cheaptrick(x, f0, t, FS, fft_size=FFT)
    ap = pw.d4c(x, f0, t, FS, fft_size=FFT)
    # Harvest rarely leaves a gap; D4C's own voicing test marks a frame by setting
    # its aperiodicity to 1 everywhere, so a frame is voiced only if both agree.
    f0 = np.where(ap[:, round(500 * FFT / FS)] > .99, 0.0, f0)
    return dict(f0=f0, sp=sp, ap=ap, t=t)


def synth(p):
    y = pw.synthesize(np.ascontiguousarray(p["f0"]), np.ascontiguousarray(p["sp"]),
                      np.ascontiguousarray(p["ap"]), FS, HOP_MS)
    return resample_poly(y, 2, 3)


# ------------------------------------------------------------------ features

def mel_matrix(n=40, lo=60.0, hi=7600.0):
    mel = lambda f: 2595 * np.log10(1 + f / 700)
    inv = lambda m: 700 * (10 ** (m / 2595) - 1)
    c = inv(np.linspace(mel(lo), mel(hi), n + 2))
    f = np.arange(FFT // 2 + 1) * FS / FFT
    m = np.array([np.clip(np.minimum((f - c[i]) / (c[i + 1] - c[i]), (c[i + 2] - f) / (c[i + 2] - c[i + 1])), 0, None)
                  for i in range(n)])
    return m / m.sum(1, keepdims=True), c[1:-1]


MEL, MEL_F = mel_matrix()


def logmel(sp, floor=1e-12):
    """dB re 1 in 40 mel bands, frames x bands."""
    return 10 * np.log10(sp @ MEL.T + floor)


def feats(p):
    m = logmel(p["sp"], 1e-9)
    m = np.maximum(m, m.max() - 70)
    c = dct(m, norm="ortho", axis=1)[:, :16]
    d = np.gradient(c, axis=0) * 3
    v = (p["f0"] > 0)[:, None] * 2.0
    z = lambda a: (a - a.mean(0)) / (a.std(0) + 1e-9)
    w = np.array([1.5] + [1.0] * 8 + [.6] * 7)
    return np.hstack([z(c) * w, .6 * z(d) * w, v])


def dtw(a, b, band=.18):
    """Monotone map: for every frame of a, the (fractional) frame of b."""
    n, m = len(a), len(b)
    cost = np.sqrt(np.maximum((a * a).sum(1)[:, None] + (b * b).sum(1)[None] - 2 * a @ b.T, 0))
    off = np.abs(np.arange(n)[:, None] / n - np.arange(m)[None] / m) > band
    cost = np.where(off, 1e6, cost)
    D = np.full((n + 1, m + 1), np.inf); D[0, 0] = 0
    back = np.zeros((n + 1, m + 1), np.int8)
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            o = (D[i - 1, j - 1] + cost[i - 1, j - 1], D[i - 1, j] + 1.15 * cost[i - 1, j - 1],
                 D[i, j - 1] + 1.15 * cost[i - 1, j - 1]) if cost[i - 1, j - 1] < 1e6 else (np.inf,) * 3
            k = int(np.argmin(o)); D[i, j] = o[k]; back[i, j] = k
    i, j, acc = n, m, [[] for _ in range(n)]
    while i > 0 and j > 0:
        acc[i - 1].append(j - 1)
        k = back[i, j]
        i, j = (i - 1, j - 1) if k == 0 else (i - 1, j) if k == 1 else (i, j - 1)
    path = np.array([np.mean(q) if q else np.nan for q in acc])
    ok = ~np.isnan(path)
    path = np.interp(np.arange(n), np.flatnonzero(ok), path[ok])
    path = np.convolve(np.pad(path, 3, mode="edge"), np.ones(7) / 7, "valid")
    return np.maximum.accumulate(path), D[n, m] / (n + m)


def voiced_interp(f0):
    v = f0 > 0
    return np.exp(np.interp(np.arange(len(f0)), np.flatnonzero(v), np.log(f0[v])))
