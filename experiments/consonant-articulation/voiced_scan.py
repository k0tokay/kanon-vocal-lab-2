"""Scan timing labels and glottal shapes of the voiced obstruents on short texts.

    voiced_scan.py <speaker> <b|d|g|z|j|r> "key=value,..." ...

Keys: the timing labels of accent.TIMING without "_s" (closure, vot, onset_tau, offset_tau,
glottis_begin, glottis_end, glottis_tau, velic_cm2); xb, xt, chink, amp: the glottal shape;
dur: the segment duration. Prints the voice band, the 1-8 kHz band, HNR and tilt around the
release (see voicing.py) next to the JVS medians of the same phone.
"""
import multiprocessing
import sys
import zlib

from compare import *
import voicing
from build import edit_glottis

TEXT = {"b": ["あばばば", "えべべ", "おぼぼ", "いびび"], "d": ["あだだだ", "えでで", "おどど"], "g": ["あががが", "ぐぎげご", "おごご"],
        "z": ["あざざ", "えぜぜ", "うずず", "おぞぞ"], "j": ["あじゃじゃ", "いじじ", "おじょじょ"], "r": ["あらら", "いりり", "うるる", "えれれ", "おろろ"]}
SHAPE = dict(b="voiced-plosive", d="voiced-plosive", g="voiced-plosive", z="voiced-fricative", j="voiced-fricative")
SEG = dict(b=["b"], d=["d"], g=["g"], z=["z"], j=["z\\", "dz\\"], r=["4"])
PHONES = dict(b=["b", "by"], d=["d"], g=["g", "gy"], z=["z"], j=["j"], r=["r", "ry"])
SHOW = list(range(-80, 61, 10))


def spans(r):
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
    speaker, ph, spec = a
    o = dict(kv.split("=") for kv in spec.split(",")) if spec != "=" else {}
    o = {k: float(v) for k, v in o.items()}
    tag = f"{ph}-{zlib.crc32(spec.encode())}"
    shape = {k: o.pop(n) for n, k in (("xb", "x_bottom"), ("xt", "x_top"), ("chink", "chink"), ("amp", "rel_amp")) if n in o}
    if shape:
        speaker = edit_glottis(speaker, SHAPE[ph], shape, OUT / f"scan/vs-{tag}.speaker")
    for s in SEG[ph]:
        if "dur" in o:
            accent.BASE[s] = o["dur"]
        if o:
            accent.TIMING[s] = {**accent.TIMING.get(s, {}), **{(k if k.endswith("_cm2") else k + "_s"): v for k, v in o.items() if k != "dur"}}
    rows, tok = [], []
    for j, t in enumerate(TEXT[ph]):
        stem = OUT / f"scan/{tag}-{j}"
        r = accent.render(t, stem, speaker=Path(speaker))
        sr, x = wavfile.read(stem.with_suffix(".wav"))
        q = (level(to16(x / 32768.0, sr)), spans(r))
        rows += list(voicing.tracks(q).values())
        tok += list(measure_one(q).values())
    return spec, {m: np.median([x[m] for x in rows], 0) for m in ("low", "mid", "hnr", "tilt")}, tok


if __name__ == "__main__":
    spk, ph, *specs = sys.argv[1:]
    spk = str(Path(spk).resolve())
    jv = pickle.load(open(OUT / "voicing-jvs.pkl", "rb"))
    ix = [int(np.flatnonzero(voicing.T == t)[0]) for t in SHOW]
    with multiprocessing.Pool(6, maxtasksperchild=1) as ex:
        res = ex.map(job, [(spk, ph, s) for s in specs], chunksize=1)
    print("ms        " + " ".join(f"{t:4d}" for t in SHOW))
    for m in ("low", "mid", "hnr", "tilt"):
        J = np.median([o[m] for d in jv.values() for t, o in d.items() if t[1][:-1] in PHONES[ph]], 0)
        print(f"{m:8s}  " + " ".join(f"{J[k]:4.0f}" for k in ix) + "   JVS")
        for s, r, _ in res:
            print(" " * 10 + " ".join(f"{r[m][k]:4.0f}" for k in ix) + "   " + s)
    for s, _, tok in res:
        md = lambda k: np.median([t[k] for t in tok if k in t]) if any(k in t for t in tok) else np.nan
        print(s, " ".join(f"{k} {md(k):.1f}" for k in ("closure_ms", "closure_low", "burst_mid", "burst_1k", "burst_2k", "burst_4k", "vot_ms", "cv_ms",
                                                      "fric_level", "fric_cog", "fb_6k", "fric_voice", "dip_mid", "nb_1k", "nb_2k") if md(k) == md(k)))
