"""Is the noise and the missing spectral movement in the vowels themselves?

Central half of every vowel of at least 60 ms: JVS women (boundaries of
consonant-articulation/align.py) against Kanon (boundaries of the seg files).
    ALIGN=<consonant-articulation/out/align.pkl> python vowels.py v1-1-0 v1-1-3 ...
"""
import json
import pickle
import sys
from concurrent.futures import ProcessPoolExecutor

from common import *
from copysynth import read_wav
from stats import SPK

VOW = {"a": "a", "i": "i", "u": "u", "M": "u", "e": "e", "o": "o"}


def merged(spans):
    out = []
    for n, a, b in spans:
        n = VOW.get(n, "")
        if n and out and out[-1][0] == n and a - out[-1][2] < .012:
            out[-1][2] = b
        else:
            out.append([n, a, b])
    return [s for s in out if s[0] and s[2] - s[1] >= .06]


def seg_spans(path):
    t, out = 0., []
    for l in path.read_text().splitlines():
        d = dict(q.strip().split(" = ") for q in l.replace("name = ;", "name = _;").strip().rstrip(";").split(";"))
        out.append((d["name"], t, t + float(d["duration_s"]))); t += float(d["duration_s"])
    return out


def measure(items):
    """items: [(audio, spans)] of one voice."""
    nhr, frac, spec, sd, ons = {"3k": [], "6k": []}, [], {}, [], []
    for x, sp in items:
        p = analyse(x); m = logmel(p["sp"], 1e-14); v = p["f0"] > 0
        q = np.clip(p["ap"], 1e-4, .9999) ** 2
        r = {k: 10 * np.log10(q[:, i] / (1 - q[:, i])) for k, i in (("3k", round(3000 * FFT / FS)), ("6k", round(6000 * FFT / FS)))}
        for n, a, b in merged(sp):
            i, j = (int(round((a + f * (b - a)) * 200)) for f in (.25, .75))
            s = slice(i, min(j, len(v))); w = v[s]
            frac.append(w.mean())
            if w.mean() < .8:
                continue
            for k in r: nhr[k].append(np.median(r[k][s][w]))
            y = 10 ** (m[s][w] / 10); y = 10 * np.log10(y.mean(0)); spec.setdefault(n, []).append(y - y.mean())
    M = np.array([np.mean(spec[n], 0) if n in spec else np.full(40, np.nan) for n in "aiueo"])
    return dict(n=len(nhr["3k"]), voiced=float(np.mean(frac)), nhr3=float(np.mean(nhr["3k"])), nhr6=float(np.mean(nhr["6k"])),
                nhr3_sd=float(np.std(nhr["3k"])), vowel_sd=np.nanstd(M, 0).tolist())


def jvs(a):
    name, al = a
    return name, measure([(x, al[name, u]) for u, x in load_jvs(name, SENTENCES).items() if (name, u) in al])


if __name__ == "__main__":
    al = pickle.load(open(os.environ["ALIGN"], "rb"))["align"]
    names = sorted({n for n, _ in al})
    with ProcessPoolExecutor(8) as ex:
        pop = dict(ex.map(jvs, [(n, al) for n in names]))
    vo = {}
    for ver in sys.argv[1:]:
        A = HERE / "out" / ver / "audio"
        for tag, sub in [("rule", "vtl")] + [(f"copy-{s}", s) for s in SPK]:
            vo[f"{ver} {tag}"] = measure([(read_wav(A / f"{sub}/{u}.wav"), seg_spans(A / f"{sub}/{u}.seg")) for u in SENTENCES])
    for k in ("n", "voiced", "nhr3", "nhr6", "nhr3_sd"):
        x = np.array([p[k] for p in pop.values()])
        print(f"{k:8s} JVS {x.mean():7.2f} ± {x.std():5.2f} | " + " ".join(f"{v[k]:7.2f}" for v in vo.values()))
    print("pairs (same speaker) nhr3: " + " ".join(f"{k} {v['nhr3'] - pop[k.split('-')[-1]]['nhr3']:+.1f}" for k, v in vo.items() if "copy" in k))
    P = np.array([p["vowel_sd"] for p in pop.values()])
    print("\nSD between the five vowels' mean spectra (dB)\n     Hz   JVS   sd  " + "  ".join(vo))
    for b in range(40):
        print(f"{MEL_F[b]:7.0f} {P[:, b].mean():5.1f} {P[:, b].std():4.1f}  " + "  ".join(f"{v['vowel_sd'][b]:6.1f}" for v in vo.values()))
    (HERE / "results/vowels.json").write_text(json.dumps(dict(
        jvs={k: [round(float(f([p[k] for p in pop.values()])), 3) for f in (np.mean, np.std)] for k in ("voiced", "nhr3", "nhr6", "nhr3_sd")},
        jvs_vowel_sd=P.mean(0).round(2).tolist(), mel_hz=MEL_F.round(1).tolist(), kanon=vo), indent=1))
