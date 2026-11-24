"""Swap WORLD components between a JVS recording (R) and v1.1.0 with the same timing (V).

log SP(t, f) = E(t) + S(f) + D(t, f):
  E  frame power (loudness contour); it is restored after S or D is swapped
  S  mean of the power-normalised log spectrum over the active frames (long-term tone)
  D  the rest (movement of the spectral shape)
F0 and AP keep the voiced/unvoiced decision of the base signal.
Writes out/swap/<spk>-<utt>-<base>-<component>.wav and out/swap/index.json.
"""
import json
import sys

from scipy.io import wavfile

from common import *
from copysynth import read_wav

OUT = HERE / "out/swap"
COMP = ["F0", "AP", "S", "E", "D"]


def warp_to(Pv, Pr):
    """V's parameters on R's frames: constant lag first, then DTW."""
    ev, er = (np.maximum(logmel(P["sp"]).mean(1), -110) for P in (Pv, Pr))
    n = max(len(ev), len(er))
    c = np.correlate(np.pad(er - er.mean(), (0, n - len(er))), np.pad(ev - ev.mean(), (0, n - len(ev))), "full")
    lag = np.arange(-n + 1, n); ok = np.abs(lag) < 60
    lag = int(lag[ok][np.argmax(c[ok])])               # R frame = V frame + lag
    N = len(er)
    base = np.clip(np.arange(N) - lag, 0, len(ev) - 1)
    A = {k: Pv[k][base] for k in ("f0", "sp")}
    path, score = dtw(feats(Pr), feats(A), band=.04)
    pos = np.clip(path - lag, 0, len(ev) - 1)
    i0 = np.floor(pos).astype(int); i1 = np.minimum(i0 + 1, len(ev) - 1); w = (pos - i0)[:, None]
    lsp = np.log(np.maximum(Pv["sp"], Pv["sp"].max() * 1e-9))
    f = voiced_interp(Pv["f0"])
    near = np.rint(pos).astype(int)
    return dict(f0=np.where(Pv["f0"][near] > 0, np.exp(np.log(f[i0]) * (1 - w[:, 0]) + np.log(f[i1]) * w[:, 0]), 0),
                sp=np.exp(lsp[i0] * (1 - w) + lsp[i1] * w), ap=Pv["ap"][near]), lag, score


def split(P, active):
    L = 10 * np.log10(np.maximum(P["sp"], P["sp"].max() * 1e-9))
    E = 10 * np.log10((10 ** (L / 10)).sum(1))
    S = (L - E[:, None])[active].mean(0)
    return S, E, L - E[:, None] - S


def build(base, other, comps, act):
    Sb, Eb, Db = split(base, act); So, Eo, Do = split(other, act)
    Eo = Eo - Eo[act].mean() + Eb[act].mean()
    L = (So if "S" in comps else Sb) + (Do if "D" in comps else Db)
    # Whatever the shape became, the frame power follows the chosen loudness contour.
    L += ((Eo if "E" in comps else Eb) - 10 * np.log10((10 ** (L / 10)).sum(1)))[:, None]
    v = base["f0"] > 0
    f0 = np.where(v, voiced_interp(other["f0"]) if "F0" in comps else voiced_interp(base["f0"]), 0)
    both = v & (other["f0"] > 0)
    ap = np.where(both[:, None], other["ap"], base["ap"]) if "AP" in comps else base["ap"].copy()
    return dict(f0=f0.astype(np.float64), sp=10 ** (L / 10), ap=ap.astype(np.float64))


def save(x, name):
    x = level(x) * 1.6
    peak = np.abs(x).max()
    wavfile.write(OUT / f"{name}.wav", RS, (x * min(1, .98 / peak) * 32767).astype(np.int16))


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True); info = {}
    for spk in sys.argv[1:]:
        for u, real in load_jvs(spk, SENTENCES).items():
            v = read_wav(HERE / f"out/audio/{spk}/{u}.wav")
            R, Pv = analyse(real), analyse(v)
            V, lag, score = warp_to(Pv, R)
            e = [logmel(P["sp"]).mean(1) for P in (R, V)]
            act = np.all([q > np.quantile(q, .95) - 35 for q in e], 0)
            tag = f"{spk}-{u}"
            save(real, f"{tag}-R-original"); save(v, f"{tag}-V-original")
            for b, (x, y) in {"R": (R, V), "V": (V, R)}.items():
                save(synth(x), f"{tag}-{b}-none")
                for c in COMP:
                    save(synth(build(x, y, {c}, act)), f"{tag}-{b}-{c}")
            # Cumulative: V with everything from R except the long-term tone.
            save(synth(build(V, R, {"F0", "AP", "E"}, act)), f"{tag}-V-F0+AP+E")
            save(synth(build(V, R, {"F0", "AP", "E", "D"}, act)), f"{tag}-V-F0+AP+E+D")
            vv = [(P["f0"] > 0) & act for P in (R, V)]
            info[tag] = dict(lag_ms=lag * HOP_MS, dtw=float(score), voicing_agree=float((vv[0] == vv[1])[act].mean()),
                             f0_rmse_cent=float(np.sqrt(np.median((1200 * np.log2(R["f0"][vv[0] & vv[1]] / V["f0"][vv[0] & vv[1]])) ** 2))))
            print(tag, info[tag], flush=True)
    (OUT / "index.json").write_text(json.dumps(info, indent=1))
