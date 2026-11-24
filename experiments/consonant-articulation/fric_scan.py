"""Scan of the voiced fricatives: is there noise, is the voice weak enough, is the vowel onset clean?

    fric_scan.py <speaker> <z|j> "key=value,..." ...      (keys as in voiced_scan.py)

Median over the tokens of TEXT, next to the JVS women (the same phone in the five sentences):
    n_hi    highest 5-7.8 kHz level (course.py, dB re the full level of the vowel) from -80 to 0 ms
    n_ms    how long it stays within 6 dB of that
    v_lo    lowest 80-500 Hz level, v_mid lowest 0.5-1 kHz level
    ratio   n_hi - level of 80-1000 Hz at the same time
    hnr     at +10, +20, +30 ms; tilt at +10 (voicing.py)
    cog     centre of gravity of the fricative (measure.py), v_hi = 2-4 kHz level at the noise peak
"""
import multiprocessing
import sys
import zlib

from voiced_scan import *
import course


def stats(c, v):
    B = course.CB
    t = course.T
    hi = 10 * np.log10((10 ** (c[6:8] / 10)).sum(0))
    w = np.flatnonzero((t >= -80) & (t <= 0))
    k = w[int(hi[w].argmax())]
    lo = 10 * np.log10((10 ** (c[:2] / 10)).sum(0))
    q = np.flatnonzero((t >= -90) & (t <= 5))
    at = lambda m, ms: v[m][int(np.flatnonzero(voicing.T == ms)[0])]
    return dict(n_hi=hi[k], n_ms=5. * (hi[q] > hi[k] - 6).sum(), v_lo=c[0][w].min(), v_mid=c[1][w].min(), ratio=hi[k] - lo[k],
                n_24=10 * np.log10((10 ** (c[3:5] / 10)).sum(0))[k], hnr10=at("hnr", 10), hnr20=at("hnr", 20), hnr30=at("hnr", 30), tilt10=at("tilt", 10))


def jobf(a):
    speaker, ph, spec, rate = a
    o = dict(kv.split("=") for kv in spec.split(",")) if spec != "=" else {}
    o = {k: float(v) for k, v in o.items()}
    tag = f"{ph}-{zlib.crc32(spec.encode())}-{round(100 * rate)}"
    shape = {k: o.pop(n) for n, k in (("xb", "x_bottom"), ("xt", "x_top"), ("chink", "chink"), ("amp", "rel_amp")) if n in o}
    if shape:
        speaker = edit_glottis(speaker, SHAPE[ph], shape, OUT / f"scan/fs-{tag}.speaker")
    for s in SEG[ph]:
        if "dur" in o:
            accent.BASE[s] = o["dur"]
        if o:
            accent.TIMING[s] = {**accent.TIMING.get(s, {}), **{(k if k.endswith("_cm2") else k + "_s"): v for k, v in o.items() if k != "dur"}}
    out = []
    for j, t in enumerate(TEXT[ph]):
        stem = OUT / f"scan/fs-{tag}-{j}"
        r = accent.render(t, stem, speaker=Path(speaker), rate=rate)
        sr, x = wavfile.read(stem.with_suffix(".wav"))
        q = (level(to16(x / 32768.0, sr)), spans(r))
        C, V, K = course.courses(q), voicing.tracks(q), measure_one(q)
        out += [stats(C[t][1], V[t]) | dict(cog=K[t].get("fric_cog", np.nan)) for t in C if t in V and t[1][:-1] in PHONES[ph]]
    return spec, rate, {k: np.nanmedian([x[k] for x in out]) for k in out[0]}


if __name__ == "__main__":
    a = sys.argv[1:]
    rate = 1.0
    if "--rate" in a:
        i = a.index("--rate"); rate = float(a[i + 1]); del a[i:i + 2]
    spk, ph, *specs = a
    spk = str(Path(spk).resolve())
    vj, cj, mj = pickle.load(open(OUT / "voicing-jvs.pkl", "rb")), course.jvs_courses(), jvs()
    J = [stats(o[1], vj[n][t]) | dict(cog=mj[n][t].get("fric_cog", np.nan)) for n, d in cj.items() for t, o in d.items()
         if t[1][:-1] in PHONES[ph] and t in vj[n] and t in mj[n]]
    ks = list(J[0])
    print(" ".join(f"{k:>6s}" for k in ks))
    print(" ".join(f"{np.nanmedian([x[k] for x in J]):6.0f}" for k in ks), f"  JVS n={len(J)}")
    for p in (25, 75):
        print(" ".join(f"{np.nanpercentile([x[k] for x in J], p):6.0f}" for k in ks), f"  p{p}")
    with multiprocessing.Pool(8, maxtasksperchild=1) as ex:
        for s, r, o in ex.imap(jobf, [(spk, ph, s, rate) for s in specs], chunksize=1):
            print(" ".join(f"{o[k]:6.0f}" for k in ks), "  " + s)
