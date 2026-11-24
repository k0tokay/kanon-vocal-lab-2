"""The burst of /t/ (and, for reference, of d k): timing labels and the shape tt-alveolar-closure.

    t_scan.py <speaker> "key=value,..." ... [--rate 1.5]      ("=" for no change)

Keys: offset_tau, onset_tau, vot, lead (labels of t only, see accent.TIMING), dur; begin, end
(glottal gesture of t); ts3 (added to the shape, all contexts), front (0: teeth and lips as in the
speaker, 1: as in v1.1.0); gx, gchink (voiceless-plosive x and chink).
Synthesis only: short texts and the five sentences; the JVS medians (dB re the vowel) are cached.
Per vowel: burst 1-2, 2-4, 4-8, 1-8 kHz, VOT, release to segment end, closure; d and k for reference.
"""
import multiprocessing
import sys
import zlib

from compare import *
from build import ctune, edit_glottis
from voiced_scan import spans

TEXT = {"t1": "あた、また、かたな、わたし。", "t2": "あて、みて、てがみ。", "t3": "おと、こと、ととのう。", "t4": "いたい、うたう、ひとつ。",
        "d1": "あだ、まだ、から、でも、おど。", "k1": "あか、こけ、かき、くき。"}
LONG = dict(offset_tau="offset_tau_s", onset_tau="onset_tau_s", vot="vot_s", lead="lead_s", begin="glottis_begin_s", end="glottis_end_s")
KEYS = ["burst_1k", "burst_2k", "burst_4k", "burst_mid", "vot_ms", "cv_ms", "closure_ms", "closure_low", "voice_min"]


def shape(speaker, out, ts3, front):
    tr = ctune.vm.Tract(Path(speaker))
    old = ctune.vm.Tract(ROOT / "speakers/fulkhisa-kanon/fulkhisa-kanon-v1-1-0.speaker")
    ix = lambda n: int(np.ravel(tr.index(n))[0])
    for c in "aiu":
        n = f"tt-alveolar-closure({c})"
        x, y = tr.shape(n).copy(), old.shape(n)
        for p in ("JA", "LD"):
            x[ix(p)] += front * (y[ix(p)] - x[ix(p)])
        x[ix("TS3")] += ts3
        tr.set_shape(n, x)
    tr.write_speaker(Path(out), Path(speaker))
    return str(out)


def job(a):
    speaker, spec, rate = a
    o = {k: float(v) for k, v in (kv.split("=") for kv in spec.split(","))} if spec != "=" else {}
    tag = f"{zlib.crc32((speaker + spec + str(rate)).encode())}"
    if "ts3" in o or "front" in o:
        speaker = shape(speaker, OUT / f"scan/ts-{tag}.speaker", o.pop("ts3", 0), o.pop("front", 0))
    g = {n: o.pop(k) for k, n in (("gx", "x_bottom"), ("gchink", "chink")) if k in o}
    if g:
        speaker = str(edit_glottis(speaker, "voiceless-plosive", g, OUT / f"scan/tsg-{tag}.speaker"))
    if "dur" in o:
        accent.BASE["t"] = o.pop("dur")
    accent.TIMING["t"] = {**accent.TIMING.get("t", {}), **{LONG[k]: v for k, v in o.items()}}
    tok = []
    for u, text in {**TEXT, **SENTENCES}.items():
        stem = OUT / f"scan/ts-{tag}-{u}"
        r = accent.render(text, stem, speaker=Path(speaker), rate=rate)
        sr, x = wavfile.read(stem.with_suffix(".wav"))
        tok += [(k[1], v) for k, v in measure_one((level(to16(x / 32768.0, sr)), spans(r))).items()]
    return spec, tok


def row(tok, ps):
    t = [v for k, v in tok if k in ps]
    md = lambda k: np.median([x[k] for x in t if k in x]) if any(k in x for x in t) else np.nan
    return " ".join(f"{md(k):4.0f}" for k in KEYS)


if __name__ == "__main__":
    args = sys.argv[1:]
    rate = float(args.pop(args.index("--rate") + 1)) if "--rate" in args else 1.0
    args = [q for q in args if q != "--rate"]
    spk, *specs = args
    J = [(k[1], v) for d in pickle.load(open(OUT / "jvs-measures.pkl", "rb")).values() for k, v in d.items()]
    with multiprocessing.Pool(8, maxtasksperchild=1) as ex:
        res = ex.map(job, [(str(Path(spk).resolve()), s, rate) for s in specs], chunksize=1)
    print(f"{'':38s}" + " ".join(k.replace("burst_", "b").replace("_ms", "")[:4].rjust(4) for k in KEYS))
    for s, tok in [("JVS", J)] + res:
        for ps in (["ta"], ["te"], ["to"], ["da", "de", "do"], ["ka", "ko", "ke"]):
            print(f"{s if ps == ['ta'] else '':30s}{'/'.join(ps)[:6]:8s}{row(tok, ps)}")
