"""Formants (LPC, the same estimator for JVS and synthesis) around the taps, token by token.

    tap_formants.py <label>=<speaker> ...

Hz, median over the 51 women. The LPC is unreliable on the synthesis (high f0, weak F1): for
that, take the formants of the tract shapes instead.
"""
import sys

from scipy.signal import lfilter, resample_poly

import course
from voiced_scan import *

SH = [-50, -40, -30, -25, -20, -15, 15, 20, 25, 30, 40, 50]
FS = 11000


def lpc_formants(y, c):
    """F1..F3 of a 24 ms window at sample c."""
    w = int(.024 * FS)
    s = y[max(0, c - w // 2):c + w // 2]
    if len(s) < w - 2:
        return [np.nan] * 3
    s = lfilter([1, -.95], 1, s) * np.hamming(len(s))
    p = 12
    r = np.correlate(s, s, "full")[len(s) - 1:len(s) + p]
    r[0] *= 1 + 1e-6
    R = r[np.abs(np.arange(p)[:, None] - np.arange(p))]
    a = np.linalg.solve(R + 1e-12 * np.eye(p), r[1:])
    z = np.roots(np.r_[1, -a])
    z = z[z.imag > 0]
    f, bw = np.angle(z) * FS / 2 / np.pi, -np.log(np.abs(z)) * FS / np.pi
    f = np.sort(f[(f > 200) & (f < 4500) & (bw < 600)])
    return list(f[:3]) + [np.nan] * (3 - min(3, len(f)))


def fjob(job):
    x, spans = job
    sp = M.Spec(x)
    y = resample_poly(x, 11, 16)
    mid = sp.band(1000, 4000)
    out = {}
    for i, p, a, b, v1, q, n in tokens(spans):
        if p not in ("r", "ry") or q not in "aiueo":
            continue
        m = mid[int(1000 * a) - 10:int(1000 * b) + 20]
        if len(m) < 5:
            continue
        c = (int(1000 * a) - 10 + int(m.argmin())) / 1000
        out[(i, q + p + n)] = np.array([lpc_formants(y, int(FS * (c + t / 1000))) for t in SH])
    return out


if __name__ == "__main__":
    path = OUT / "tapf-jvs.pkl"
    if not path.exists():
        al = pickle.load(open(OUT / "align.pkl", "rb"))["align"]
        keys, jobs = [], []
        for n in women():
            for u, x in load_jvs(n, list(SENTENCES)).items():
                keys.append((n, u)); jobs.append((x, al[(n, u)]))
        with ProcessPoolExecutor(8) as ex:
            pickle.dump(dict(zip(keys, ex.map(fjob, jobs, chunksize=4))), open(path, "wb"))
    J = {}
    for (n, u), d in pickle.load(open(path, "rb")).items():
        for t, f in d.items():
            J.setdefault((u, t), []).append(f)
    J = {t: np.nanmedian(v, 0) for t, v in J.items() if len(v) > 20}
    S = {}
    for l in sys.argv[1:]:
        label, spk = l.split("=")
        S[label] = {(u, t): f for u, j in synth(spk, label).items() for t, f in fjob(j).items()}
    for t in J:
        print(t)
        for k in range(3):
            print(f"  F{k + 1} JVS  " + " ".join(f"{f[k]:5.0f}" for f in J[t]))
            for l in S:
                if t in S[l]:
                    print(f"     {l:5s}" + " ".join(f"{f[k]:5.0f}" for f in S[l][t]))
