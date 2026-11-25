"""F0 and duration errors of text prosody predictors against the mean of the JVS women.

    python prosody_eval.py out/prosody-jvs.pkl pred-*.json ...
A predictor file: {utt: [[consonant, vowel, F0 in semitones or null, mora s, pause after s], ...]}.
Odd sentences fit the rule parameters, even ones are the test set (all predictors are scored on the even ones).
"""
import json
import pickle
import sys

import numpy as np

VOWEL = set("aiueoAIUEON") | {"cl"}


def moras_of(spans):
    """[(consonant, vowel, vowel start, vowel end, mora start, pause after)] of one aligned recording."""
    out, cons = [], ""
    start = None
    for n, a, b in spans:
        if n == "sil":
            if out: out[-1][5] = max(out[-1][5], b - a)
            continue
        if n in VOWEL:
            out.append([cons, n, a, b, start if cons else a, 0.0]); cons = ""
        else:
            cons, start = n, a
    return out


def reference(D):
    """Per sentence: mora list and arrays women x moras of F0 (st, centred), duration and pause."""
    R = {}
    for u in D["phones"]:
        rows = []
        for n, r in D["jvs"].items():
            if u not in r: continue
            M = moras_of(r[u]["spans"]); f, fc = r[u]["f0"], r[u]["f0c"]
            y, v, d, p = [], [], [], []
            for c, w, a, b, s, pa in M:
                i = min(int((a + b) / 2 * 200), len(f) - 1)
                y.append(12 * np.log2(fc[i] / 100)); lo, hi = int((a + .25 * (b - a)) * 200), int((b - .25 * (b - a)) * 200) + 1
                v.append((f[lo:hi] > 0).mean() if hi > lo else 0); d.append(b - s); p.append(pa)
            rows.append((y, v, d, p))
        k = [len(r[0]) for r in rows]
        assert len(set(k)) == 1, u
        Y, V, Du, Pa = (np.array([r[q] for r in rows]) for q in range(4))
        ok = (V > .5).mean(0) > .5
        ok &= np.array([w in "aiueo" or w == "N" for _, w, *_ in M])
        Y = Y - Y[:, ok].mean(1, keepdims=True)
        R[u] = dict(mora=[(c, w) for c, w, *_ in M], Y=Y, ok=ok, D=Du, P=Pa, mean=Y.mean(0))
    return R


def lev(a, b):
    n, m = len(a), len(b)
    D = np.zeros((n + 1, m + 1), int); D[:, 0] = range(n + 1); D[0] = range(m + 1)
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            D[i, j] = min(D[i - 1, j] + 1, D[i, j - 1] + 1, D[i - 1, j - 1] + (a[i - 1] != b[j - 1]))
    i, j, o = n, m, [None] * n
    while i and j:
        if D[i, j] == D[i - 1, j - 1] + (a[i - 1] != b[j - 1]):
            o[i - 1] = j - 1; i, j = i - 1, j - 1
        elif D[i, j] == D[i - 1, j] + 1: i -= 1
        else: j -= 1
    return o, D[n, m]


def score(R, pred, utts):
    """Pooled RMSE and correlation of F0, log-duration correlation, reading errors (mora)."""
    e, A, B, la, lb, sub, tot, per = [], [], [], [], [], 0, 0, []
    for u in utts:
        r = R[u]; P = pred[u]
        key = lambda c, v: (c, v.lower() if v != "cl" else v)
        o, d = lev([key(c, v) for c, v in r["mora"]], [key(q[0], q[1]) for q in P]); sub += d; tot += len(r["mora"])
        ix = [(i, j) for i, j in enumerate(o) if j is not None and r["ok"][i] and P[j][2] is not None]
        x = np.array([P[j][2] for _, j in ix]); y = r["mean"][[i for i, _ in ix]]
        x, y = x - x.mean(), y - y.mean()
        e.append((x - y) ** 2); per.append(np.sqrt(((x - y) ** 2).mean())); A.append(x); B.append(y)
        jd = [(i, j) for i, j in enumerate(o) if j is not None and P[j][3]]
        a = np.array([P[j][3] for _, j in jd]); b = r["D"][:, [i for i, _ in jd]].mean(0)
        la.append(np.log(a / a.mean())); lb.append(np.log(b / b.mean()))
    A, B = np.concatenate(A), np.concatenate(B); la, lb = np.concatenate(la), np.concatenate(lb)
    return dict(rmse=float(np.sqrt(np.concatenate(e).mean())), corr=float(np.corrcoef(A, B)[0, 1]), sd=float(A.std()),
                dur=float(np.corrcoef(la, lb)[0, 1]), mora_err=sub / tot, n=len(A), per=per)


if __name__ == "__main__":
    R = reference(pickle.load(open(sys.argv[1], "rb")))
    test = sorted(u for u in R if int(u) % 2 == 0)
    # one woman against the mean of the others, and a flat line
    loo = []
    for k in range(next(iter(R.values()))["Y"].shape[0]):
        loo.append([np.sqrt(np.mean((R[u]["Y"][k][R[u]["ok"]] - (R[u]["Y"].sum(0) - R[u]["Y"][k])[R[u]["ok"]] / (len(R[u]["Y"]) - 1)) ** 2)) for u in test if len(R[u]["Y"]) > k])
    flat = np.sqrt(np.mean(np.concatenate([(R[u]["mean"][R[u]["ok"]] - R[u]["mean"][R[u]["ok"]].mean()) ** 2 for u in test])))
    print(f"{'flat':28s} F0 RMSE {flat:.2f} st"); print(f"{'one woman vs the rest':28s} F0 RMSE {np.mean(np.concatenate(loo)):.2f} st (range over women {min(map(np.mean, loo)):.2f}-{max(map(np.mean, loo)):.2f})")
    out = {}
    for f in sys.argv[2:]:
        s = score(R, json.load(open(f)), test); out[f] = s
        print(f"{f.split('/')[-1][5:-5]:28s} F0 RMSE {s['rmse']:.2f} st  corr {s['corr']:.2f}  sd {s['sd']:.2f}  duration corr {s['dur']:.2f}  mora errors {100 * s['mora_err']:.1f} %  ({s['n']} moras)")
