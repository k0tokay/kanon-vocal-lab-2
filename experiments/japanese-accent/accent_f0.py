"""F0 learned from accent features (opt-in for accent.render, trained by world-decomposition/prosody_train.py).

The model file holds regressors fitted to the mean contour of the JVS women. JVS audio is for research,
non-commercial and personal use, so the file is kept out of git (as are all JVS derivatives).
Load only a model file you trained yourself: it is a pickle.
"""
import pickle

import numpy as np

from accent import Mora, Pause

VOICED = {"g", "z", "d", "b", "n", "m", "r", "y", "w", "j", "gy", "ny", "my", "ry", "by", "dy", "v", ""}


def features(units):
    """(moras, feature matrix) of the output of accent.parse."""
    ph, br, cur = [], [], None
    for m in units:
        if isinstance(m, Pause): continue
        if cur != (m.breath_id, m.phrase_id):
            ph.append([]); br.append(m.breath_id); cur = (m.breath_id, m.phrase_id)
        ph[-1].append(m)
    moras = [m for p in ph for m in p]; rows = []
    n, nb = len(moras), max(br) + 1 if br else 1
    hl = []
    for p in ph:
        t = p[0].accent_type; L = len(p)
        for k in range(1, L + 1):
            hl.append(int(k == 1 and (t == 1 or L == 1) or k > 1 and (t == 0 or k <= t)))
    i = 0
    for q, p in enumerate(ph):
        t, L = p[0].accent_type, len(p)
        same = [x for x in range(len(ph)) if br[x] == br[q]]
        for k, m in enumerate(p, 1):
            nuc = t if t else L + 1
            b0 = sum(len(ph[x]) for x in same if x < q); bn = sum(len(ph[x]) for x in same)
            pv, nx = (ph[q - 1] if q and br[q - 1] == br[q] else None), (ph[q + 1] if q + 1 < len(ph) and br[q + 1] == br[q] else None)
            acc = [x for x in same if x < q and ph[x][0].accent_type]
            v = "aiueoN".find(m.vowel.lower() if m.vowel != "N" else "N")
            rows.append([k, L - k, L, t, int(t == 0), k - nuc, int(k > nuc), int(k == nuc), hl[i], hl[i - 1] if i else 0, hl[i + 1] if i + 1 < n else 0,
                         min(k, 4), int(k == 1), int(k == 2), q, len(ph) - q, same.index(q), len(same), len(same) - same.index(q), br[q], nb, b0 + k, bn - b0 - k, bn, i / n,
                         len(acc), len(pv) if pv else 0, (pv[0].accent_type if pv else -1), int(pv is not None and pv[0].accent_type > 0), len(nx) if nx else 0, nx[0].accent_type if nx else -1,
                         int(m.consonant in VOICED), int(bool(m.consonant)), *(int(v == z) for z in range(6)), int(m.vowel.isupper())])
            i += 1
    return moras, np.array(rows, float)


def load(path):
    with open(path, "rb") as f:
        return pickle.load(f)


def predict(model, units):
    """Semitones per mora around the sentence mean, with the range lost to averaging restored (gain)."""
    _, f = features(units)
    return np.mean([m.predict(f) for m in model["models"]], 0) * model["gain"]


def apply(model, units, spans, segments, mean=218.0):
    """Write the learned F0 (Hz) into the segments; mean = geometric mean over the vowel centres."""
    from scipy.interpolate import PchipInterpolator
    moras = [(m, s) for m, s in zip(units, spans) if isinstance(m, Mora)]
    kx, ky = [], []
    for (m, (a, b)), y in zip(moras, predict(model, units)):
        if m.vowel not in "aiueoN": continue
        own = [s for s in segments if a - 1e-6 <= s.t0 < b - 1e-6]
        v0 = own[-1].t0 if m.consonant and len(own) > 1 else a
        kx.append((v0 + b) / 2); ky.append(float(y))
    ky = np.array(ky) - np.mean(ky)
    curve = PchipInterpolator(kx, ky) if len(kx) > 1 else lambda t: np.full(np.shape(t), ky[0])
    f0 = lambda t: mean * 2 ** (curve(np.clip(t, kx[0], kx[-1])) / 12)
    for s in segments:
        s.f0 = list(f0(np.array([s.t0 + r * s.duration for r in (.2, .5, .8)])))
    return f0
