"""Do the consonants and vowels reach their targets in fast speech?

    rate.py <label>=<speaker> [--rates 1,1.25,1.5,1.75,2] [--v111-rules]

The five sentences at several speech rates (1 = 135 ms per mora, 7.4 morae/s). For every token the
tract parameters of its articulator are compared with the same token at rate 0.5, where every
target is reached:
    attain  how far the movement from the vowel before (at 0.5: the vowel shape) to the consonant
            (at 0.5: the point of greatest constriction) gets, 1 = all the way
    Amin    smallest area near the constriction (cm2), and at rate 0.5
    VO      velic opening of the nasals relative to rate 0.5
    glottis how far x_bottom gets from modal to the glottal shape of the consonant
Vowels: median distance of F1/F2 from the vowel shape at the best instant (Bark), and the share (%)
of vowels that stay further away than 0.5 Bark.
Then the acoustic measures of measure.py per rate. Writes results/rate-<label>.json.
"""
import ctypes as C
import multiprocessing
import os
import sys

from compare import *

sys.path.insert(0, str(HERE.parent / "consonant-tuning"))
STEP = .0025
REF = .5
TIP, BODY, LIP = ["TTX", "TTY", "TBX", "TBY", "TS3"], ["TCX", "TCY", "TBX", "TBY"], ["LD", "LP", "JA"]
ART = {"k": BODY, "t": TIP, "g": BODY, "d": TIP, "p": LIP, "b": LIP, "s": TIP, "sh": TIP, "ch": TIP, "ts": TIP, "z": TIP, "j": TIP,
       "hy": BODY, "f": LIP, "m": LIP, "n": TIP, "r": TIP, "ky": BODY, "gy": BODY, "by": LIP, "my": LIP, "ny": TIP, "ry": TIP, "y": BODY, "w": LIP}
GROUP = {"k": "k t", "t": "k t", "ky": "k t", "b": "b d g", "d": "b d g", "g": "b d g", "by": "b d g", "gy": "b d g", "s": "s", "sh": "sh",
         "ch": "ch", "ts": "ts", "z": "z", "j": "j", "hy": "hy f", "f": "hy f", "m": "m n", "n": "m n", "my": "m n", "ny": "m n", "r": "r", "ry": "r",
         "y": "y w", "w": "y w"}
GLOTTIS = {"s": .17, "sh": .17, "ch": .17, "ts": .17, "hy": .17, "k": .153, "t": .153, "b": .025, "d": .025, "g": .025}   # x_bottom of the shapes
REL = {"LIP": (.94, 1.01), "TIP": (.80, .97), "BODY": (.45, .85)}
ACOUSTIC = {"無声破裂 k t": ["closure_ms", "burst_mid", "vot_ms"], "有声破裂 b d g": ["closure_ms", "closure_low", "burst_mid"], "s": ["fric_cog", "fb_6k", "fric_voice", "fric_level"],
            "ɕ (sh)": ["fric_cog", "fb_6k", "fric_voice", "fric_level"], "tɕ (ch)": ["closure_ms", "fric_cog", "fb_6k", "fric_voice"], "z": ["fric_cog", "fb_6k", "fric_voice"],
            "dʑ (j)": ["fric_cog", "fb_6k", "fric_voice"], "m n": ["nb_1k", "nb_2k", "voice_min"], "ɾ": ["dip_mid", "nb_1k"]}


def phone_spans(r):
    b = []
    for q, (s, e) in zip(r["units"], r["spans"]):
        if isinstance(q, accent.Pause):
            continue
        if q.consonant:
            k = [g for g in r["segments"] if s - 1e-6 <= g.t0 < e - 1e-6][-1]
            b += [(q.consonant, s, k.t0), (q.vowel, k.t0, e)]
        else:
            b.append((q.vowel, s, e))
    return b


def job(a):
    speaker, label, u, rate, old = a
    if old:
        v111_rules()
    stem = OUT / f"rate/{label}-{rate:g}/{u}"
    r = accent.render(SENTENCES[u], stem, speaker=Path(speaker), rate=rate)
    sr, x = wavfile.read(stem.with_suffix(".wav"))
    b = phone_spans(r)
    meas = measure_one((level(to16(x / 32768.0, sr)), b)) if rate != REF else {}
    lib = C.CDLL(str(HERE.parents[1] / "build-mac/ctrack.so"))
    lib.ct_tract_sequence.argtypes = [C.c_char_p, C.c_char_p, C.c_double, np.ctypeslib.ndpointer(np.float64), C.c_int]
    T = np.zeros((12000, lib.ct_num_params()))
    n = lib.ct_tract_sequence(str(speaker).encode(), str(stem.with_suffix(".ges")).encode(), STEP, T, 12000)
    assert n > 0
    glot = None
    if rate != REF:
        cd = C.CDLL(str(HERE.parents[1] / "build-mac/cdiag.so"))
        cd.cd_run.argtypes = [C.c_char_p, C.c_char_p, C.c_int, np.ctypeslib.ndpointer(np.float64), C.c_int]
        G = np.zeros((12000, 11))
        m = cd.cd_run(str(speaker).encode(), str(stem.with_suffix(".ges")).encode(), 120, G, 12000)
        glot = G[:m, [0, 2]]
    return (u, rate), dict(spans=b, track=T[:n], meas=meas, glot=glot)


def frames(t0, t1, n):
    return np.arange(max(0, int(t0 / STEP)), min(n, int(t1 / STEP) + 1))


def analyse(a):
    """Attainment of one sentence at one rate against the reference."""
    import ctune
    speaker, cur, ref = a
    tr = ctune.vm.Tract(Path(speaker))
    lo, hi, _ = tr.bounds()
    out, vow = [], []
    vo = tr.names.index("VO")
    for i, ((p, s0, s1), (q, r0, r1)) in enumerate(zip(cur["spans"], ref["spans"])):
        assert p == q
        if p in ART:
            art = ART[p]
            which = "LIP" if art is LIP else "BODY" if art is BODY else "TIP"
            idx = tr.index(*art)
            w = 1 / (hi - lo)[idx]
            rel = REL[which]

            def area(track, t0, t1):
                k = frames(t0 - .02, t1 + .01, len(track))
                A = []
                for j in k:
                    ar = tr.area_function(track[j], 64)
                    rr = ar[0] / ar[0][-1]
                    A.append(ar[1][(rr >= rel[0]) & (rr <= rel[1])].min())
                return k, np.array(A)
            kr, Ar = area(ref["track"], r0, r1)
            kc, Ac = area(cur["track"], s0, s1)
            m = np.flatnonzero(Ar <= Ar.min() + .01)
            c = ref["track"][kr[int(np.median(m))]][idx]
            # the following vowel's shape is the other end of the movement
            v = ref["track"][frames(r1, r1 + .1, len(ref["track"]))[-1]][idx]
            d = (c - v) * w
            X = (cur["track"][kc][:, idx] - v) * w
            o = dict(phone=p, attain=float((X @ d).max() / max(d @ d, 1e-9)) if d @ d > 1e-3 else None, Amin=float(Ac.min()), Aref=float(Ar.min()))
            if p in GLOTTIS:
                q = cur["glot"]
                x = q[(q[:, 0] > s0 - .03) & (q[:, 0] < s1 + .02), 1]
                m0 = np.median(cur["glot"][:, 1])
                a0 = (x.max() if GLOTTIS[p] > m0 else x.min())
                o["glottis"] = float((a0 - m0) / (GLOTTIS[p] - m0))
            if p[0] in "mn":
                o["VO"] = float(cur["track"][frames(s0 - .03, s1 + .03, len(cur["track"]))][:, vo].max() /
                                ref["track"][frames(r0 - .03, r1 + .03, len(ref["track"]))][:, vo].max())
            out.append(o)
        elif p in "aiueo":
            x = tr.shape({"u": "M"}.get(p, p)) if {"u": "M"}.get(p, p) in tr.shape_names() else tr.shape(p)
            ii = tr.index("TCX", "TCY", "TBX", "TBY", "TTX", "TTY", "JA", "LD", "LP")
            k = frames(s0, s1, len(cur["track"]))
            if not len(k):
                continue
            D = (((cur["track"][k][:, ii] - x[ii]) / (hi - lo)[ii]) ** 2).sum(1)
            f = tr.formants(cur["track"][k[int(np.argmin(D))]], 2)[0]
            vow.append((p, f.tolist(), tr.formants(x, 2)[0].tolist()))
    return out, vow


def bark(f):
    return 26.81 * f / (1960 + f) - .53


def main(args):
    old = "--v111-rules" in args
    rates = [float(x) for x in args[args.index("--rates") + 1].split(",")] if "--rates" in args else [1, 1.25, 1.5, 1.75, 2]
    label, spk = next(a for a in args if "=" in a).split("=")
    spk = str(Path(spk).resolve())
    with multiprocessing.Pool(8, maxtasksperchild=4) as pool:
        R = dict(pool.map(job, [(spk, label, u, r, old) for u in SENTENCES for r in [REF] + rates], chunksize=1))
        jobs = [(u, r) for u in SENTENCES for r in rates]
        A = dict(zip(jobs, pool.map(analyse, [(spk, R[j], R[(j[0], REF)]) for j in jobs], chunksize=1)))
    pop = collect_jvs()
    res = {}
    for r in rates:
        o = {"cons": {}, "acoustic": {}}
        toks = [t for u in SENTENCES for t in A[(u, r)][0]]
        for g in dict.fromkeys(GROUP.values()):
            q = [t for t in toks if GROUP[t["phone"]] == g]
            if q:
                att = [t["attain"] for t in q if t["attain"] is not None]
                o["cons"][g] = dict(n=len(q), attain=float(np.median(att)), attain10=float(np.percentile(att, 10)),
                                    Amin=float(np.median([t["Amin"] for t in q])), Aref=float(np.median([t["Aref"] for t in q])))
                if any("glottis" in t for t in q):
                    o["cons"][g]["glottis"] = float(np.median([t["glottis"] for t in q if "glottis" in t]))
                if "VO" in q[0]:
                    o["cons"][g]["VO"] = float(np.median([t["VO"] for t in q if "VO" in t]))
        V = [v for u in SENTENCES for v in A[(u, r)][1]]
        f, t = bark(np.array([v[1] for v in V])), bark(np.array([v[2] for v in V]))
        o["vowel"] = dict(bark=float(np.median(np.linalg.norm(f - t, axis=1))), far=float(100 * np.mean(np.linalg.norm(f - t, axis=1) > .5)))
        tab = table({u: R[(u, r)]["meas"] for u in SENTENCES}, pop)
        for c, ks in ACOUSTIC.items():
            o["acoustic"][c] = {k: tab[c][k]["syn"] for k in ks if k in tab[c]}
        res[f"{r:g}"] = o
    (HERE / f"results/rate-{label}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
    rs = list(res)
    print("rate                 " + " ".join(f"{r:>7s}" for r in rs))
    for g in res[rs[0]]["cons"]:
        for k in ("attain", "attain10", "Amin", "Aref", "VO", "glottis"):
            if k in res[rs[0]]["cons"][g]:
                print(f"{g:8s} {k:10s}  " + " ".join(f"{res[r]['cons'][g][k]:7.2f}" for r in rs))
    for k in ("bark", "far"):
        print(f"vowels   {k:10s}  " + " ".join(f"{res[r]['vowel'][k]:7.2f}" for r in rs))
    for c, ks in ACOUSTIC.items():
        for k in ks:
            print(f"{c:8s} {k:10s}  " + " ".join(f"{res[r]['acoustic'][c].get(k, np.nan):7.1f}" for r in rs))


if __name__ == "__main__":
    main(sys.argv[1:])
