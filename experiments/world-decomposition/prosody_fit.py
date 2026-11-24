"""Fit the Fujisaki parameters of accent.py to the JVS mean on odd sentences; write predictions for the test.

    python prosody_fit.py out/prosody-jvs.pkl texts.json pred-out.json     (run with either OpenJTalk)
"""
import json
import pickle
import sys
from pathlib import Path

import numpy as np

from prosody_eval import lev, reference
import prosody_pred

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "japanese-accent"))

if __name__ == "__main__":
    import accent
    from scipy.optimize import minimize
    R = reference(pickle.load(open(sys.argv[1], "rb"))); texts = json.load(open(sys.argv[2]))
    train = [u for u in sorted(R) if int(u) % 2]
    # parse once
    P = {u: accent.parse(texts[u]["text"]) for u in texts}
    S = {u: accent.to_segments(P[u])[1] for u in P}
    key = lambda c, v: (c, v.lower() if v != "cl" else v)
    J = {}
    for u in texts:
        m = [(x, s) for x, s in zip(P[u], S[u]) if isinstance(x, accent.Mora)]
        o, _ = lev([key(*q) for q in R[u]["mora"]], [key(x.consonant, x.vowel) for x, _ in m])
        J[u] = [(i, j) for i, j in enumerate(o) if j is not None and R[u]["ok"][i] and m[j][0].vowel in "aiueoN"], m

    def curve(u, q):
        p = accent.Fujisaki(**dict(zip(("ap_first", "ap_next", "aa", "alpha", "beta", "lead"), q)))
        ph, ac = accent.commands(P[u], S[u], p)
        return 12 * np.log2(accent.f0_curve(np.array([a + .65 * (b - a) for _, (a, b) in J[u][1]]), ph, ac, p) / 100)

    def loss(q, us):
        if min(q) < 0: return 99
        e = []
        for u in us:
            x = curve(u, q); ix = J[u][0]
            x = x[[j for _, j in ix]]; y = R[u]["mean"][[i for i, _ in ix]]
            e.append((x - x.mean() - y + y.mean()) ** 2)
        return np.sqrt(np.mean(np.concatenate(e)))
    q0 = np.array([.32, .22, .30, 3., 20., .05])
    best = min((minimize(loss, q0 * np.random.default_rng(k).uniform(.6, 1.6, 6), args=(train,), method="Nelder-Mead", options=dict(maxfev=900)) for k in range(4)), key=lambda r: r.fun)
    test = [u for u in sorted(R) if int(u) % 2 == 0]
    print("default train/test", round(loss(q0, train), 2), round(loss(q0, test), 2), "fitted", best.x.round(3), "train/test", round(best.fun, 2), round(loss(best.x, test), 2))
    json.dump(prosody_pred.rule(texts, list(best.x)), open(sys.argv[3], "w"), ensure_ascii=False)
