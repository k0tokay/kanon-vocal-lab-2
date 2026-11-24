"""Train the F0 model of japanese-accent/accent_f0.py on all 100 sentences, with varied commas.

    VA100=<dir> python prosody_train.py out/prosody-jvs.pkl texts.json out/f0-model.pkl
`gain` restores the range that averaging loses: SD of the JVS mean contour / SD of the 10-fold predictions.
"""
import pickle
import sys
from pathlib import Path

import numpy as np

from prosody_commas import ALL, R, U, fit, pred, score

cv = {}
for k in range(10):
    te = [u for i, u in enumerate(U) if i % 10 == k]; M = fit(ALL, [u for u in U if u not in te])
    cv.update({u: {c: pred(M, u, c) for c in ALL} for u in te})
for c in ALL:
    s = score(R, {u: cv[u][c] for u in U}, U); print(f"10-fold, {c:6s} commas: corr {s['corr']:.2f} RMSE {s['rmse']:.2f} SD {s['sd']:.2f}")
ref = np.concatenate([r["mean"][r["ok"]] for r in R.values()]).std()
gain = ref / np.mean([score(R, {u: cv[u][c] for u in U}, U)["sd"] for c in ALL])
Path(sys.argv[3]).write_bytes(pickle.dumps(dict(models=fit(ALL, U), gain=float(gain), source="mean F0 of 51 JVS women, voiceactress100 (research / non-commercial / personal use)")))
print("JVS SD", round(float(ref), 2), "gain", round(float(gain), 3))
