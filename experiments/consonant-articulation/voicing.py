"""Time course of voicing and noise around the release of voiced (and voiceless) obstruents.

    voicing.py <label>=<speaker> ...      -> median tracks, JVS women against synthesis

Tracks aligned at the release (stops: end of the closure; others: end of the segment), dB re
the following vowel:
    low   80-500 Hz (20 ms window)    voice bar
    mid   1-7.8 kHz (6 ms)            closure depth, burst
    hnr   harmonics-to-noise ratio (dB), 25 ms, below 4 kHz: aspirated onsets are low
    tilt  80-500 Hz minus 2-4 kHz: breathy onsets are high
"""
import sys

from compare import *

SETS = {"b": ["b", "by"], "d": ["d"], "g": ["g", "gy"], "k t": ["k", "t", "ky"], "z": ["z"], "j": ["j"], "r": ["r", "ry"]}
T = np.arange(-120, 121, 5)


def hnr_track(x, win=400, hop=80, lo=50, hi=145):
    n = len(x) // hop
    pad = np.pad(x, (win // 2, win))
    f = np.fft.rfftfreq(1024, 1 / RS)
    w = np.hanning(win)
    out = np.full(n, np.nan)
    rw = np.fft.irfft(np.abs(np.fft.rfft(w, 1024)) ** 2)
    for i in range(n):
        s = pad[i * hop:i * hop + win] * w
        P = np.abs(np.fft.rfft(s, 1024)) ** 2
        P[f > 4000] = 0
        r = np.fft.irfft(P)
        r = r[:hi + 1] / (rw[:hi + 1] / rw[0] + 1e-9)
        q = np.clip(r[lo:hi].max() / (r[0] + 1e-15), 1e-3, .9999)
        out[i] = 10 * np.log10(q / (1 - q))
    return out


def tracks(job):
    x, spans = job
    sp = M.Spec(x)
    low, mid, h = sp.band(80, 500, "lo"), sp.band(1000, 7800), hnr_track(x)
    hi = sp.band(2000, 4000, "lo")
    ms = lambda t: int(np.clip(round(t * 1000), 0, sp.n - 1))
    out = {}
    for i, p, a, b, v1, q, n in tokens(spans):
        o = M.token(sp, a, b, v1, p)
        ve = min(v1, b + .14)
        sl = slice(ms(b + .35 * (ve - b)), ms(b + .8 * (ve - b)) + 3)
        if p in M.STOPS and "cv_ms" not in o or q not in "aiueoN":
            continue
        rel = ms(b) + (o["cv_ms"] if p in M.STOPS else 0)
        k = np.clip((rel + T).astype(int), 0, sp.n - 1)
        out[(i, p + n)] = dict(low=low[k] - np.median(low[sl]), mid=mid[k] - np.median(mid[sl]),
                               hnr=h[np.clip(k // 5, 0, len(h) - 1)], tilt=(low - hi)[k] - np.median((low - hi)[sl]))
    return out


def main(args):
    path = OUT / "voicing-jvs.pkl"
    if not path.exists():
        al = pickle.load(open(OUT / "align.pkl", "rb"))["align"]
        keys, jobs = [], []
        for n in women():
            for u, x in load_jvs(n, list(SENTENCES)).items():
                keys.append((n, u)); jobs.append((x, al[(n, u)]))
        with ProcessPoolExecutor(8) as ex:
            pickle.dump(dict(zip(keys, ex.map(tracks, jobs, chunksize=4))), open(path, "wb"))
    jv = pickle.load(open(path, "rb"))
    S = {l: {u: tracks(j) for u, j in synth(s, l).items()} for l, s in (a.split("=") for a in args)}
    show = list(range(-100, 101, 10))
    ix = [int(np.flatnonzero(T == t)[0]) for t in show]
    print("ms         " + " ".join(f"{t:5d}" for t in show))
    for name, phs in SETS.items():
        for m in ("low", "mid", "hnr", "tilt"):
            J = np.array([o[m] for d in jv.values() for t, o in d.items() if t[1][:-1] in phs])
            print(f"{name} {m}: JVS n={len(J)}")
            for tag, r in (("JVS med", np.median(J, 0)), ("JVS p25", np.percentile(J, 25, 0)), ("JVS p75", np.percentile(J, 75, 0))):
                print(f"  {tag:8s} " + " ".join(f"{r[k]:5.0f}" for k in ix))
            for l, d in S.items():
                q = [o[m] for u in d.values() for t, o in u.items() if t[1][:-1] in phs]
                r = np.median(q, 0)
                print(f"  {l:8s} " + " ".join(f"{r[k]:5.0f}" for k in ix) + f"  n={len(q)}")


if __name__ == "__main__":
    main(sys.argv[1:])
