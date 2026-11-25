"""Per-mora F0 and durations of all JVS women on voiceactress100 (forced alignment).

Texts and readings (CC BY-SA 4.0) are read from VA100: balance_sentences.txt (voice-statistics)
and voiceactoress100_phoneme_openjtalk.txt (Hiroshiba/jvs_hiho). Monophone HMMs start from
consonant-articulation's align.pkl and are re-estimated on 12 speakers.
    VA100=<dir> ALIGN=<align.pkl> VTL_LIB=... python prosody_data.py      -> out/prosody-jvs.pkl
"""
import os
import pickle
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "consonant-articulation"))
import align as A
import common as C
from copysynth import clean_f0

VA = Path(os.environ["VA100"])
PH = {f"{i + 1:03d}": l.split() for i, l in enumerate((VA / "voiceactoress100_phoneme_openjtalk.txt").read_text().splitlines())}
OUT = C.HERE / "out"
VOWEL = set("aiueoAIUEON") | {"cl"}


def phones(u):
    out = []
    for p in PH[u]:
        if p in ("sil", "pau"):
            if not out or out[-1][0] != "sil":
                out.append(("sil", bool(out), 0))
            else:
                out[-1] = ("sil", True, 0)
            continue
        out.append((p, False, 0))
        if p in VOWEL and p != "cl":
            out.append(("sil", True, 0))
    out[-1] = ("sil", False, 0)
    return out


def speaker(a):
    """Align one speaker; optionally return the state-labelled features for training."""
    name, model, want = a
    xs = C.load_jvs(name, list(PH))
    Fs = {u: A.mfcc(x) for u, x in xs.items()}
    mu, sd = A.norm(list(Fs.values()))
    bins, rec = {}, {}
    for u, x in xs.items():
        F = (Fs[u] - mu) / sd; m = A.pauses(x); ph = phones(u)
        S, P, O = A.chain(ph)
        for s in set(S):
            model.setdefault(s, model["_any"])
        LL = A.loglik(F, S, model)
        sil = np.array([s == "sil0" for s in S])
        LL[np.ix_(m, ~sil)] = -1e4
        LL[np.ix_(~m, sil)] -= 6.0
        path = A.viterbi(LL, O)
        if want:
            lab = np.array(S, dtype=object)[path]
            for s in set(lab):
                bins.setdefault(s, []).append(F[lab == s])
        else:
            p = C.analyse(x)
            rec[u] = dict(spans=A.spans(ph, P, path), f0=p["f0"].astype(np.float32), f0c=clean_f0(p["f0"]).astype(np.float32))
    return name, {s: np.vstack(b) for s, b in bins.items()}, rec


if __name__ == "__main__":
    W = A.women()
    model = pickle.load(open(os.environ["ALIGN"], "rb"))["model"]
    anyv = np.vstack([g[0] for g in model.values()])
    model["_any"] = (np.zeros((1, anyv.shape[1])), np.ones((1, anyv.shape[1])), np.ones(1))
    with ProcessPoolExecutor(10) as ex:
        for it in range(5):
            bins = {}
            for _, b, _ in ex.map(speaker, [(n, dict(model), True) for n in W[::4][:12]]):
                for s, v in b.items():
                    bins.setdefault(s, []).append(v)
            allx = np.vstack([v[0][::20] for v in bins.values()]); floor = .02 * allx.var(0)
            for s, v in bins.items():
                x = np.vstack(v)
                model[s] = A.fit_gmm(x[np.random.default_rng(0).permutation(len(x))[:20000]], 1 if it < 2 else 3, floor)
            print("round", it, flush=True)
        res = {n: r for n, _, r in ex.map(speaker, [(n, dict(model), False) for n in W])}
    pickle.dump(dict(jvs=res, phones=PH), open(OUT / "prosody-jvs.pkl", "wb"))
    print(len(res), sum(map(len, res.values())))
