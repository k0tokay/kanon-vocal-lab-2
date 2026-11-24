"""How much of the learned F0 depends on commas put where the JVS women pause?

    VA100=<dir> python prosody_commas.py out/prosody-jvs.pkl texts.json     (pyopenjtalk-plus env, scikit-learn)
Commas of the test sentences: as the JVS majority pauses (jvs), half of those dropped (half), none (none), one at
every break marked in the corpus reading (many), or at sentence-medial 'が、は、て…' style places a writer would
choose (writer: after a clause-final particle, at least 8 moras from the previous comma).
"""
import json
import pickle
import re
import sys

import numpy as np

from prosody_eval import lev, reference, score
from prosody_stat import KEY, accent, features
from prosody_text import PH, TX, with_commas
from sklearn.ensemble import ExtraTreesRegressor, GradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
import pyopenjtalk

R = reference(pickle.load(open(sys.argv[1], "rb"))); T = json.load(open(sys.argv[2])); U = sorted(R)
rng = np.random.default_rng(0)
LEAF = 12          # every training sentence appears with five comma placings
MK = [lambda: make_pipeline(StandardScaler(), Ridge(30.)), lambda: GradientBoostingRegressor(n_estimators=300, max_depth=4, learning_rate=.05, subsample=.7, min_samples_leaf=8 * LEAF // 3, random_state=0),
      lambda: ExtraTreesRegressor(150, min_samples_leaf=LEAF, max_features=.4, random_state=0, n_jobs=8)]


def writer(text):
    out, n = [], 0
    W = pyopenjtalk.run_frontend(text)
    for i, w in enumerate(W):
        out.append(w["string"]); n += w["mora_size"]
        last = i + 2 >= len(W)
        clause = w["pos"] == "助詞" and (w["pos_group1"] == "接続助詞" or w["pos_group1"] == "係助詞" or w["string"] in ("に", "で", "が") and w["pos_group1"] == "格助詞")
        if clause and not last and n >= 8 and W[i + 1]["pos"] not in ("助詞", "助動詞", "記号"): out.append("、"); n = 0
    return "".join(out) + "。"


def half(text):
    p = text.split("、"); return "".join(x + ("、" if i < len(p) - 1 and rng.random() < .5 else "") for i, x in enumerate(p))


V = {}
for u in U:
    t = TX[int(u) - 1]; V[u] = dict(jvs=T[u]["text"], half=half(T[u]["text"]), none=T[u]["text"].replace("、", ""), many=with_commas(t, PH[int(u) - 1]), writer=writer(t))
print({k: round(np.mean([V[u][k].count("、") for u in U]), 2) for k in V[U[0]]}, "commas per sentence")
X = {}
for u in U:
    for k, t in V[u].items():
        m, f = features(t); o, d = lev([KEY(*q) for q in R[u]["mora"]], [KEY(x.consonant, x.vowel) for x in m])
        ix = [(a, b) for a, b in enumerate(o) if b is not None and R[u]["ok"][a]]; y = R[u]["mean"][[a for a, _ in ix]]
        X[u, k] = (m, f, f[[b for _, b in ix]], y - y.mean())
odd, even = [u for u in U if int(u) % 2], [u for u in U if int(u) % 2 == 0]


def rule(u, k):
    un = accent.parse(V[u][k]); _, sp = accent.to_segments(un); p = accent.Fujisaki(); ph, ac = accent.commands(un, sp, p)
    return [[m.consonant, m.vowel, None if m.vowel in "AIUEO" or m.vowel == "cl" else float(12 * np.log2(accent.f0_curve(np.array([(a + b) / 2]), ph, ac, p)[0] / 100)), .1, 0.] for m, (a, b) in zip(un, sp) if isinstance(m, accent.Mora)]


def fit(train_k, utts=odd):
    S = [X[u, k] for u in utts for k in train_k]; return [m().fit(np.vstack([s[2] for s in S]), np.concatenate([s[3] for s in S])) for m in MK]


def pred(M, u, k):
    m, f = X[u, k][:2]; y = np.mean([q.predict(f) for q in M], 0)
    return [[x.consonant, x.vowel, None if x.vowel in "AIUEO" or x.vowel == "cl" else float(a), .1, 0.] for x, a in zip(m, y)]


ALL = ["jvs", "half", "none", "many", "writer"]
if __name__ == "__main__":
  for name, M in {"rule": None, "trained on jvs": fit(["jvs"]), "trained on jvs half none many writer": fit(ALL)}.items():
      r = {}
      for k in ALL:
          s = score(R, {u: rule(u, k) if M is None else pred(M, u, k) for u in even}, even); r[k] = f"{s['corr']:.2f}/{s['rmse']:.2f}"
      print(f"{name:38s}", r, flush=True)
