"""Loud vowels next to b d g: scan the glottal gesture and shape, with the closure voicing alongside.

    stop_scan.py <speaker> "key=value,..." ...       ("=" for no change)

Keys as in voiced_scan.py (begin, end, tau: the glottal gesture; xb, xt, chink, amp: the shape
voiced-plosive; vot, lead, velic_cm2, onset_tau, offset_tau), for b d g alike, or for one of them with
a prefix (g.end=.01). The five sentences and three full of b d g. Per line: the peaks after and before
b d g (dB re active rms, see onset_glottis.py), and from the five sentences only the closure low band,
VOT, burst 1-2, 2-4, 4-8 kHz, HNR 10/20/30 ms after the release and the low band around the release.
"""
import multiprocessing
import sys
import zlib

from onset_glottis import *
import voicing
from listen112 import MORE
from build import edit_glottis

LONG = dict(begin="glottis_begin_s", end="glottis_end_s", tau="glottis_tau_s", vot="vot_s", lead="lead_s",
            onset_tau="onset_tau_s", offset_tau="offset_tau_s", velic_cm2="velic_cm2")
SHAPE = dict(xb="x_bottom", xt="x_top", chink="chink", amp="rel_amp", lag="lag")


def job(a):
    speaker, spec, rate = a
    tag = f"{zlib.crc32((speaker + spec).encode())}-{rate}"
    timing, shape = {}, {}
    for kv in spec.split(",") if spec != "=" else []:
        k, v = kv.split("=")
        ph, k = k.split(".") if "." in k else ("bdg", k)
        if k in SHAPE:
            shape[SHAPE[k]] = float(v)
        else:
            for p in ph:
                timing.setdefault(p, {})[LONG[k]] = float(v)
    if shape:
        speaker = str(edit_glottis(speaker, "voiced-plosive", shape, OUT / f"scan/ss-{tag}.speaker"))
    for p, d in timing.items():
        accent.TIMING[p] = {**accent.TIMING.get(p, {}), **d}
    rows, ot, tr, tok = [], [], [], []
    for u, text in {**SENTENCES, **MORE}.items():
        stem = OUT / f"scan/ss-{tag}-{u}"
        r = accent.render(text, stem, speaker=Path(speaker), rate=rate)
        v, o = peaks(wav(stem.with_suffix(".wav")), seg_spans(r))
        rows += [q + (u,) for q in v]; ot += o
        sr, x = wavfile.read(stem.with_suffix(".wav"))
        q = (level(to16(x / 32768.0, sr)), spans_of(r))
        tr += [(k[1], d) for k, d in voicing.tracks(q).items() if k[1][0] in "bdg"]
        tok += [(k[1], d) for k, d in measure_one(q).items() if k[1][0] in "bdg"]
    return spec, rows, ot, tr, tok


def spans_of(r):
    from voiced_scan import spans
    return spans(r)


def report(res, per_phone=True):
    print(f"{'':44s} after med p95 max | before med p95 max | clo_low vot burst 1k 2k 4k | hnr 10 20 30 | low -20 -10 0 10 20 40 | tilt 10 20 40")
    jv, jm = pickle.load(open(OUT / "voicing-jvs.pkl", "rb")), jvs()
    for p in ("bdg", "b", "d", "g"):
        T = [o for d in jv.values() for t, o in d.items() if t[1][0] in p]
        t = [o for d in jm.values() for k, o in d.items() if k[1][0] in p]
        md = lambda k: np.median([d[k] for d in t if k in d])
        ix = lambda m, v: " ".join(f"{np.nanmedian([d[m][int(np.flatnonzero(voicing.T == q)[0])] for d in T]):4.0f}" for q in v)
        print(f"{'JVS ' + p:81s}| {md('closure_low'):5.1f} {md('vot_ms'):4.1f} {md('burst_1k'):5.1f} {md('burst_2k'):5.1f} {md('burst_4k'):5.1f} | {ix('hnr', (10, 20, 30))} | {ix('low', (-20, -10, 0, 10, 20, 40))} | {ix('tilt', (10, 20, 40))}")
    for spec, rows, ot, tr, tok in res:
        for p in ("bdg",) + (("b", "d", "g") if per_phone else ()):
            R = [r for r in rows if r[0] in p]
            A, B = np.array([r[4] for r in R]), np.array([r[6] for r in R])
            t = [d for k, d in tok if k[0] in p]; T = [d for k, d in tr if k[0] in p]
            md = lambda k: np.median([d[k] for d in t if k in d]) if any(k in d for d in t) else np.nan
            ix = lambda m, v: " ".join(f"{np.nanmedian([d[m][int(np.flatnonzero(voicing.T == q)[0])] for d in T]):4.0f}" for q in v)
            pc = lambda x, q: np.nanpercentile(x, q)
            print(f"{(spec if p == 'bdg' else '   ' + p):44s} {pc(A, 50):5.1f} {pc(A, 95):5.1f} {A.max():5.1f} | {pc(B, 50):5.1f} {pc(B, 95):5.1f} {np.nanmax(B):5.1f} | "
                  f"{md('closure_low'):5.1f} {md('vot_ms'):4.1f} {md('burst_1k'):5.1f} {md('burst_2k'):5.1f} {md('burst_4k'):5.1f} | {ix('hnr', (10, 20, 30))} | {ix('low', (-20, -10, 0, 10, 20, 40))} | {ix('tilt', (10, 20, 40))}")


if __name__ == "__main__":
    a = sys.argv[1:]
    per = "--all" not in a
    rate = float(a[a.index("--rate") + 1]) if "--rate" in a else 1.0
    if "--rate" in a:
        k = a.index("--rate"); a = a[:k] + a[k + 2:]
    a = [q for q in a if q != "--all"]
    spk = str(Path(a[0]).resolve())
    with multiprocessing.Pool(8, maxtasksperchild=1) as ex:
        res = ex.map(job, [(spk, s, rate) for s in a[1:]], chunksize=1)
    report(res, per)
