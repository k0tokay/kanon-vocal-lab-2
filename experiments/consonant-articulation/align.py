"""Forced alignment of JVS sentences with monophone HMMs trained on those sentences only.

Start from a DTW between the rule synthesis (boundaries known) and each recording, both
without pauses; then Viterbi training. Left-to-right, 3 states per phone (1 for pauses),
diagonal Gaussians on speaker-normalised MFCCs, hop 2.5 ms. Silent stretches found from the
energy are forced into pause states, which may be skipped after every vowel and N, and no
other frame may use them (a flat start without this put the pauses into the consonants).
Boundaries are a starting point only:
measure.py looks for closures and releases acoustically around them.
"""
import pickle
import sys
from pathlib import Path

import numpy as np
from scipy.fft import dct

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "world-decomposition"))
from common import *          # noqa: E402,F403
import accent                 # noqa: E402
from concurrent.futures import ProcessPoolExecutor  # noqa: E402
from scipy.io import wavfile  # noqa: E402

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
H = 40                        # 2.5 ms at 16 kHz
WIN, NFFT = 256, 512          # 16 ms


def mfcc(x):
    x = np.append(x[0], x[1:] - .95 * x[:-1])
    n = (len(x) - WIN) // H
    f = np.stack([x[i * H:i * H + WIN] for i in range(n)]) * np.hanning(WIN)
    p = np.abs(np.fft.rfft(f, NFFT)) ** 2
    fr = np.arange(NFFT // 2 + 1) * RS / NFFT
    mel = lambda f: 2595 * np.log10(1 + f / 700)
    c = 700 * (10 ** (np.linspace(mel(80), mel(7800), 28) / 2595) - 1)
    m = np.array([np.clip(np.minimum((fr - c[i]) / (c[i + 1] - c[i]), (c[i + 2] - fr) / (c[i + 2] - c[i + 1])), 0, None)
                  for i in range(26)])
    L = np.log(p @ m.T + 1e-8)
    C = dct(L, norm="ortho", axis=1)[:, :13]
    d = np.zeros_like(C)
    d[4:-4] = (C[8:] - C[:-8]) / 2
    return np.hstack([C, d])


def phones(text):
    """[(phone, optional, rule duration s)]."""
    out = [("sil", False, .1)]
    for u in accent.parse(text):
        if isinstance(u, accent.Pause):
            if u.kind == "pau" and out[-1][0] == "sil":
                out[-1] = ("sil", True, .05)
            continue
        if u.consonant:
            out.append((u.consonant, False, .06))
        out.append((u.vowel, False, .09 if u.vowel == "cl" else .075))
        if u.vowel != "cl":
            out.append(("sil", True, .004))
    out[-1] = ("sil", False, .1)
    return out


def nstates(p):
    return 1 if p in ("sil", "cl") else 3


def chain(ph):
    """State names, phone index per state, and whether the state belongs to a skippable pause."""
    S, P, O = [], [], []
    for k, (p, opt, _) in enumerate(ph):
        for j in range(nstates(p)):
            S.append(f"{p}{j}"); P.append(k); O.append(opt)
    return S, np.array(P), np.array(O)


def loglik(F, S, model):
    L = {}
    for s in set(S):
        mu, var, w = model[s]
        l = -.5 * (((F[:, None] - mu[None]) ** 2 / var[None]).sum(2) + np.log(var).sum(1)[None]) + np.log(w)[None]
        L[s] = np.logaddexp.reduce(l, axis=1)
    return np.stack([L[s] for s in S], 1)


def viterbi(LL, O):
    T, N = LL.shape
    D = np.full(N, -np.inf); D[0] = LL[0, 0]
    B = np.zeros((T, N), np.int16)
    skip = np.zeros(N, bool); skip[2:] = O[1:-1]
    for t in range(1, T):
        c = np.full((3, N), -np.inf)
        c[0], c[1, 1:] = D, D[:-1]
        c[2, 2:] = np.where(skip[2:], D[:-2], -np.inf)
        k = np.argmax(c, 0)
        B[t] = k
        D = c[k, np.arange(N)] + LL[t]
    n, path = N - 1, np.zeros(T, int)
    for t in range(T - 1, -1, -1):
        path[t] = n
        n -= B[t, n]
    return path


def fit_gmm(X, k, floor):
    mu, var, w = X.mean(0)[None], np.maximum(X.var(0), floor)[None], np.ones(1)
    while len(mu) < k and len(X) > 400 * len(mu):
        mu = np.vstack([mu - .2 * np.sqrt(var), mu + .2 * np.sqrt(var)]); var = np.vstack([var, var]); w = np.r_[w, w] / 2
        for _ in range(6):
            l = -.5 * (((X[:, None] - mu[None]) ** 2 / var[None]).sum(2) + np.log(var).sum(1)[None]) + np.log(w)[None]
            r = np.exp(l - np.logaddexp.reduce(l, axis=1, keepdims=True))
            n = r.sum(0) + 1e-6
            mu = (r.T @ X) / n[:, None]
            var = np.maximum((r.T @ X ** 2) / n[:, None] - mu ** 2, floor)
            w = n / n.sum()
    return mu, var, w


def women():
    out = []
    for k in range(100):
        d = np.load(JVS / f"spk{k:03d}.npz")
        if str(d["gender"]) == "F":
            out.append(str(d["name"]))
    return out


def norm(Fs):
    A = np.vstack(Fs)
    speech = A[:, 0] > np.quantile(A[:, 0], .95) - 8
    return A[speech].mean(0), A[speech].std(0)


def pauses(x):
    """Mask on the MFCC grid: silent for at least 100 ms (first/last 30 ms left free)."""
    n = (len(x) - WIN) // H
    e = np.array([np.mean(x[i * H:i * H + WIN] ** 2) for i in range(n)])
    e = 10 * np.log10(np.convolve(e, np.ones(5) / 5, "same") + 1e-12)
    low = e < 20 * np.log10(RMS) - 34
    m = np.zeros(n, bool)
    for a, b in np.flatnonzero(np.diff(np.r_[0, low.astype(int), 0])).reshape(-1, 2):
        edge = a == 0 or b == n
        if edge or b - a >= 48:
            m[a if a == 0 else a + 6:b if b == n else b - (12 if a else 4)] = True
    return m


def rule_sentences():
    """Pause-free rule synthesis and its phone boundaries, per sentence."""
    out = {}
    for u, text in SENTENCES.items():
        units = [q for q in accent.parse(text) if not (isinstance(q, accent.Pause) and q.kind == "pau")]
        segs, sp = accent.to_segments(units)
        ph, com = accent.commands(units, sp, accent.Fujisaki())
        for s in segs:
            s.f0 = list(accent.f0_curve(np.array([s.t0 + r * s.duration for r in (.2, .5, .8)]), ph, com, accent.Fujisaki()))
        seg = OUT / f"tmp/{u}.seg"; seg.parent.mkdir(parents=True, exist_ok=True)
        accent.write_seg(segs, seg)
        accent.synthesize(seg, seg.with_suffix(".wav"), segs)
        rate, x = wavfile.read(seg.with_suffix(".wav"))
        b = []
        for q, (s, e) in zip(units, sp):
            if isinstance(q, accent.Pause):
                continue
            own = [g for g in segs if s - 1e-6 <= g.t0 < e - 1e-6]
            if q.consonant:
                k = next((g for g in own if g.name in "aiueoM" and g is own[-1]), own[-1])
                b.append((q.consonant, s, k.t0)); b.append((q.vowel, k.t0, e))
            else:
                b.append((q.vowel, s, e))
        out[u] = (level(to16(x / 32768.0, rate)), b, segs[0].duration, segs[-1].t0)
    return out


def init(job):
    x, (v, b, t0, t1) = job
    m = pauses(x)
    P, V = analyse(x), analyse(v)
    k = np.arange(len(P["f0"])) * HOP_MS / 1000
    sp = ~np.interp(k, np.arange(len(m)) * H / RS + WIN / 2 / RS, m.astype(float)).astype(bool)
    idx = np.flatnonzero(sp)
    hop = HOP_MS / 1000
    A = feats({q: V[q][int(t0 / hop):int(t1 / hop)] for q in ("f0", "sp")})
    B = feats({q: P[q][idx] for q in ("f0", "sp")})
    path, _ = dtw(A, B, band=.2)
    at = lambda t: idx[int(np.clip(np.interp((t - t0) / hop, np.arange(len(path)), path), 0, len(idx) - 1))] * hop
    return [(p, at(s), at(e)) for p, s, e in b], m


def load():
    R = rule_sentences()
    data, jobs = [], []
    for n in women():
        xs = load_jvs(n, list(SENTENCES))
        Fs = {u: mfcc(x) for u, x in xs.items()}
        mu, sd = norm(list(Fs.values()))
        for u, x in xs.items():
            data.append((n, u, (Fs[u] - mu) / sd)); jobs.append((x, R[u]))
    with ProcessPoolExecutor(8) as ex:
        res = list(ex.map(init, jobs, chunksize=4))
    return data, [r[0] for r in res], [r[1] for r in res]


def start(ph, S, P0, b, T, m):
    """State path from the DTW boundaries."""
    path = np.zeros(T, int); k = 0
    order = [q for q in range(len(ph)) if ph[q][0] != "sil"]
    assert len(order) == len(b), (len(order), len(b))
    last = 0
    for q, (p, s, e) in zip(order, b):
        assert ph[q][0] == p
        st = np.flatnonzero(P0 == q)
        i, j = int((s - WIN / 2 / RS) * RS / H), int((e - WIN / 2 / RS) * RS / H)
        i = max(i, 0)
        g = np.linspace(i, max(j, i + len(st)), len(st) + 1).astype(int)
        for w, c in enumerate(st):
            path[g[w]:g[w + 1]] = c
            last = max(last, g[w + 1])
    path[last:] = len(S) - 1
    path[m] = -1
    return path


def train(data, inits, masks, rounds=14):
    PH = {u: phones(t) for u, t in SENTENCES.items()}
    CH = {u: chain(p) for u, p in PH.items()}
    paths = [start(PH[u], *CH[u][:2], b, len(F), m) for (n, u, F), b, m in zip(data, inits, masks)]
    allx = np.vstack([F for _, _, F in data[:40]]); floor = .02 * allx.var(0)
    for it in range(rounds):
        bins = {}
        for (n, u, F), p, m in zip(data, paths, masks):
            S = np.where(p < 0, "sil0", np.array(CH[u][0], dtype=object)[p])
            for s in set(S):
                if s != "sil0":
                    bins.setdefault(s, []).append(F[(S == s) & ~m])
            bins.setdefault("sil0", []).append(F[m])
        model = {s: fit_gmm(np.vstack(x), 1 if it < 5 else 3, floor) for s, x in bins.items() if sum(map(len, x)) > 5}
        for s in {q for c in CH.values() for q in c[0]}:
            model.setdefault(s, (allx.mean(0)[None], allx.var(0)[None], np.ones(1)))
        tot = 0
        for k, (n, u, F) in enumerate(data):
            S, P, O = CH[u]
            LL = loglik(F, S, model)
            sil = np.array([s == "sil0" for s in S])
            LL[np.ix_(masks[k], ~sil)] = -1e4
            LL[np.ix_(~masks[k], sil)] -= 6.0
            paths[k] = viterbi(LL, O)
            tot += LL[np.arange(len(F)), paths[k]].sum()
        print(it, round(tot / sum(len(F) for _, _, F in data), 3), flush=True)
    return model, PH, CH, paths


def spans(ph, P, path):
    """[(phone, start s, end s)] of the phones that were visited."""
    out, k, c = [], P[path], WIN / 2 / RS
    for q in range(len(ph)):
        i = np.flatnonzero(k == q)
        if len(i):
            out.append((ph[q][0], i[0] * H / RS + c, (i[-1] + 1) * H / RS + c))
    return out


if __name__ == "__main__":
    data, inits, masks = load()
    print(len(data), "utterances")
    model, PH, CH, paths = train(data, inits, masks)
    res = {(n, u): spans(PH[u], CH[u][1], p) for (n, u, _), p in zip(data, paths)}
    OUT.mkdir(exist_ok=True)
    pickle.dump(dict(align=res, model=model), open(OUT / "align.pkl", "wb"))
