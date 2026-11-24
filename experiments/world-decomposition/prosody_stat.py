"""How far can F0 be predicted from accent features alone, learned from the mean contour of the JVS women?

    python prosody_stat.py out/prosody-jvs.pkl texts.json pred-out.json     (pyopenjtalk-plus env, scikit-learn)
Features: position and nucleus in the accent phrase, high/low pattern, place of the phrase and the breath
group in the sentence, neighbouring phrases, vowel and consonant class. No audio features.
"""
import json
import os
import pickle
import sys
from pathlib import Path

import numpy as np

os.environ.setdefault("VTL_SPEAKER", "x")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "japanese-accent"))
import accent                                        # noqa: E402
from prosody_eval import lev, reference, score        # noqa: E402

KEY = lambda c, v: (c, v.lower() if v != "cl" else v)
VOICED = {"g", "z", "d", "b", "n", "m", "r", "y", "w", "j", "gy", "ny", "my", "ry", "by", "dy", "v", ""}


def features(text):
    """(moras, feature matrix)."""
    units = accent.parse(text)
    ph, br, cur = [], [], None
    for m in units:
        if isinstance(m, accent.Pause): continue
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


if __name__ == "__main__":
    from sklearn.ensemble import ExtraTreesRegressor, GradientBoostingRegressor
    from sklearn.linear_model import Ridge
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    R = reference(pickle.load(open(sys.argv[1], "rb"))); T = json.load(open(sys.argv[2]))
    X, Y, K, F, W = {}, {}, {}, {}, {}
    for u in sorted(R):
        m, f = features(T[u]["text"]); F[u] = (m, f)
        o, _ = lev([KEY(*q) for q in R[u]["mora"]], [KEY(x.consonant, x.vowel) for x in m])
        ix = [(a, b) for a, b in enumerate(o) if b is not None and R[u]["ok"][a]]
        X[u], Y[u] = f[[b for _, b in ix]], R[u]["mean"][[a for a, _ in ix]]
        Y[u] = Y[u] - Y[u].mean()
    models = {"ridge": lambda: make_pipeline(StandardScaler(), Ridge(30.)),
              "gbm": lambda: GradientBoostingRegressor(n_estimators=300, max_depth=4, learning_rate=.05, subsample=.7, min_samples_leaf=8, random_state=0),
              "extratrees": lambda: ExtraTreesRegressor(500, min_samples_leaf=3, max_features=.4, random_state=0, n_jobs=8)}

    def fit_predict(mk, train, test):
        out = {}
        M = [(n, f().fit(np.vstack([X[u] for u in train]), np.concatenate([Y[u] for u in train]))) for n, f in mk]
        for u in test:
            m, f = F[u]; y = np.mean([q.predict(f) for _, q in M], 0)
            out[u] = [[x.consonant, x.vowel, None if x.vowel in "AIUEO" or x.vowel == "cl" else float(a), .1, 0.] for x, a in zip(m, y)]
        return out
    odd, even = [u for u in sorted(R) if int(u) % 2], [u for u in sorted(R) if int(u) % 2 == 0]
    for name, mk in {**{k: [(k, v)] for k, v in models.items()}, "average of three": list(models.items())}.items():
        s = score(R, fit_predict(mk, odd, even), even)
        folds = [[u for i, u in enumerate(sorted(R)) if i % 10 == k] for k in range(10)]
        cv = {}
        for te in folds: cv.update(fit_predict(mk, [u for u in sorted(R) if u not in te], te))
        c = score(R, cv, sorted(R))
        print(f"{name:18s} train 50 -> test 50: RMSE {s['rmse']:.2f} corr {s['corr']:.2f} sd {s['sd']:.2f} | 10-fold (90 -> 10): RMSE {c['rmse']:.2f} corr {c['corr']:.2f} sd {c['sd']:.2f}", flush=True)
        if name.startswith("average"): json.dump(fit_predict(mk, odd, sorted(R)), open(sys.argv[3], "w"), ensure_ascii=False)
