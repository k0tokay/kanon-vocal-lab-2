"""Tune the consonant shapes of a VTL speaker and check them by ear and by measurement.

VTL 2.4 stores each consonant as three shapes, `<name>(a)`, `<name>(i)` and
`<name>(u)`. At synthesis time GesturalScore::getContextDependentConsonant
interpolates them by the position of the current vowel in the a-i-u triangle
(tongue and lips separately), and the consonant then takes over every tract
parameter downstream of its place (tongue body < tongue tip < lips). There is
no per-parameter dominance in 2.4: the shape *is* the target.

This module
  * loads a speaker (vtlmap.Tract) and applies edits to consonant shapes,
  * writes the edited speaker to a new file (the input is never touched),
  * renders /a/ + CV frames through the VTL API with the Japanese mapping of
    experiments/japanese-accent (M, s\\, ts\\, C, bilabial fu, taps),
  * measures closure, burst, frication and the F2 transition from the audio,
    and the static constriction of each shape from the tract geometry.

Edits are strings `shape:PARAM op value`, op in = += -= *=; `(*)` in the
shape name stands for all three vowel contexts, e.g.
    "tb-velar-closure(*):TBX+=0.2"   "tt-alveolar-fricative(i):TTY=-0.4"
"""
from __future__ import annotations

import ctypes
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from scipy.io.wavfile import read


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "vtlmap"))
sys.path.insert(0, str(HERE.parent / "japanese-accent"))
import vtlmap as vm  # noqa: E402

try:                                  # accent.py imports pyopenjtalk for text input,
    import pyopenjtalk  # noqa: F401  # which CV frames do not need.
except ImportError:
    import types
    sys.modules["pyopenjtalk"] = types.ModuleType("pyopenjtalk")
import accent  # noqa: E402

ROOT = vm.ROOT
SPEAKER = ROOT / "speakers/fulkhisa-kanon/fulkhisa-kanon-v0-8-vtl24.speaker"
CONTEXTS = ("a", "i", "u")

# Which consonant shape(s) each Japanese onset uses (for `show` and reports).
ONSET_SHAPES = {
    "k": ["tb-velar-closure"], "g": ["tb-velar-closure"],
    "s": ["tt-alveolar-fricative"], "z": ["tt-alveolar-fricative"],
    "sh": ["tt-alveolopalatal-fricative"], "j": ["tt-alveolar-closure", "tt-alveolopalatal-fricative"],
    "t": ["tt-alveolar-closure"], "d": ["tt-alveolar-closure"],
    "ts": ["tt-alveolar-closure", "tt-alveolar-fricative"],
    "ch": ["tt-alveolar-closure", "tt-alveolopalatal-fricative"],
    "n": ["tt-alveolar-closure"], "h": [], "hy": ["tb-palatal-fricative"],
    "f": ["ll-labial-fricative"], "m": ["ll-labial-closure"], "p": ["ll-labial-closure"],
    "b": ["ll-labial-closure"], "y": ["tb-palatal-fricative"], "r": ["tt-tap-*"], "w": [],
}

DEFAULT_SYLLABLES = ("ka ki ku ke ko ga sa shi su se so sha shu za ji ta chi tsu te to da "
                     "na ni nu ne no ha hi fu he ho ma mi mu pa ba ya yu yo ra ri ru re ro wa").split()


# ---------------------------------------------------------------- syllables

def split_syllable(syl: str) -> tuple[str, str]:
    """Romaji CV -> (OpenJTalk consonant, vowel)."""
    v = syl[-1]
    c = syl[:-1]
    special = {"shi": "sh", "chi": "ch", "tsu": "ts", "fu": "f", "ji": "j", "hi": "h"}
    if syl in special:
        c = special[syl]
    if c in ("sy",):
        c = "sh"
    if v not in "aiueo":
        raise ValueError(f"not a CV syllable: {syl}")
    return c, v


@dataclass
class Frame:
    syllable: str
    consonant: str
    vowel: str
    segments: list
    onset: tuple = (0.0, 0.0)     # seg-file time span of the consonant
    nucleus: tuple = (0.0, 0.0)   # and of the vowel
    carrier: tuple = (0.0, 0.0)   # preceding /a/
    track: np.ndarray | None = None  # tract parameters every TRACK_STEP s


def frame(syl: str, f0=220.0, vowel_s=0.24, carrier_s=0.2, onset_map=None) -> Frame:
    """Segments of '(pause) a CV (pause)' with the Japanese mapping of
    experiments/japanese-accent; onset_map overrides it per consonant,
    e.g. {"w": ["w"]} or {"w": ["M:0.06"]} (VTL symbol[:duration s])."""
    c, v = split_syllable(syl)
    S = accent.Segment
    if onset_map and c in onset_map:
        onset = []
        for item in onset_map[c]:
            name, _, dur = item.partition(":")
            onset.append(S(name, float(dur) if dur else accent.BASE.get(name, .04)))
    else:
        onset = accent.onset(c, v, japanese=True)
    vowel = S(accent.vowel_symbol(v, True), vowel_s)
    segs = [S("", 0.12), S("a", carrier_s)] + onset + [vowel, S("", 0.15)]
    t = 0.0
    for s in segs:
        s.t0, t = t, t + s.duration
        s.f0 = [f0, f0, f0] if s.name else [0, 0, 0]
    # gentle declination over the voiced part
    for s in segs[1:-1]:
        s.f0 = [f0 * (1 - 0.06 * (s.t0 + r * s.duration) / t) for r in (.2, .5, .8)]
    on0 = onset[0].t0 if onset else vowel.t0
    return Frame(syl, c, v, segs, (on0, vowel.t0), (vowel.t0, vowel.t0 + vowel.duration),
                 (segs[1].t0, segs[1].t0 + segs[1].duration))


NOISE_SCALING = True   # VTL noise-source constants scaled to the speaker's size
NOISE_EXPONENTS = (1.0, 2.0, -1.0)   # of the size for lengths, areas, cutoff frequencies
GLOTTAL_NOISE = (1.0, 1000.0)   # gain factor, cutoff Hz of the aspiration source
APERIODICITY = (0.0, 0.0)   # jitter %, shimmer % per glottal cycle
LUNG_PRESSURE = None   # dPa; replaces VTL's fixed 8000 dPa lung-pressure gestures


def _set_lung_pressure(ges: Path, dpa: float):
    t = ges.read_text()
    i = t.index('type="lung-pressure-gestures"')
    j = t.index("</gesture_sequence>", i)
    seq = re.sub(r'value="8000\.0+"', f'value="{dpa:.6f}"', t[i:j])
    ges.write_text(t[:i] + seq + t[j:])


def render(speaker, syllables, out_dir: Path, **kw):
    """WAV per syllable plus all.wav (the set joined) in out_dir; each frame also
    gets its tract-parameter trajectory (Frame.track). Returns the frames."""
    out_dir.mkdir(parents=True, exist_ok=True)
    frames = []
    for syl in syllables:
        fr = frame(syl, **kw)
        seg = out_dir / f"{syl}.seg"
        accent.write_seg(fr.segments, seg)
        lib = accent.use_speaker(speaker)
        if hasattr(lib, "vtlScaleNoiseToAnatomy"):
            lib.vtlScaleNoiseToAnatomy(int(NOISE_SCALING))
            lib.vtlSetNoiseScalingExponents.argtypes = [ctypes.c_double] * 3
            lib.vtlSetNoiseScalingExponents(*NOISE_EXPONENTS)
        if hasattr(lib, "vtlSetGlottalNoise"):
            lib.vtlSetGlottalNoise.argtypes = [ctypes.c_double] * 2
            lib.vtlSetGlottalNoise(*GLOTTAL_NOISE)
        if hasattr(lib, "vtlSetGlottalAperiodicity"):
            lib.vtlSetGlottalAperiodicity.argtypes = [ctypes.c_double] * 2
            lib.vtlSetGlottalAperiodicity(*APERIODICITY)
        patch = accent.patch_score
        if LUNG_PRESSURE is not None:
            def patch(ges, segments, _orig=accent.patch_score):
                if segments is not None:
                    _orig(ges, segments)
                _set_lung_pressure(Path(ges), LUNG_PRESSURE)
        saved, accent.patch_score = accent.patch_score, patch
        try:
            accent.synthesize(seg, out_dir / f"{syl}.wav", fr.segments, speaker)
        finally:
            accent.patch_score = saved
        fr.track = tract_sequence(speaker, seg.with_suffix(".ges"))
        seg.unlink()
        seg.with_suffix(".ges").unlink()
        frames.append(fr)
    join(out_dir, syllables)
    return frames


TRACK_STEP = 0.0025
_ctrack = None


def tract_sequence(speaker, ges, step=TRACK_STEP) -> np.ndarray:
    """Tract parameters of a gestural score every `step` s (ctrack.so)."""
    global _ctrack
    import ctypes as C
    if _ctrack is None:
        lib = ROOT / "build-mac/ctrack.so"
        if not lib.exists():
            raise FileNotFoundError(f"{lib} is missing; see the build line in ctrack.cpp")
        _ctrack = C.CDLL(str(lib))
        _ctrack.ct_tract_sequence.argtypes = [C.c_char_p, C.c_char_p, C.c_double,
                                              np.ctypeslib.ndpointer(np.float64), C.c_int]
    n_max = 4000
    out = np.zeros((n_max, len(vm.param_names())))
    n = _ctrack.ct_tract_sequence(str(speaker).encode(), str(ges).encode(), step, out, n_max)
    if n < 0:
        raise RuntimeError(f"could not load {ges} with {speaker}")
    return out[:n]


_tracts: dict = {}


def tract(speaker) -> vm.Tract:
    """Cached vtlmap.Tract per speaker file (handles are never freed)."""
    key = str(Path(speaker).resolve())
    if key not in _tracts:
        _tracts[key] = vm.Tract(speaker)
    return _tracts[key]


CLOSED = 1e-3       # cm^2: oral area at or below this counts as a closure


def articulation(speaker, fr: Frame, t0, t1):
    """Oral minimum area, its position, and F1-F3 (VTL transfer-function peaks,
    velum closed) for track frames in [t0, t1)."""
    tr = tract(speaker)
    rows = []
    for k in range(int(t0 / TRACK_STEP), min(len(fr.track), int(t1 / TRACK_STEP))):
        x = fr.track[k]
        c = oral_constriction(tr, x)
        f = tr.peaks(x, 3, exponent=11)[0] if c["area"] > CLOSED else np.zeros(3)
        rows.append((k * TRACK_STEP, c["area"], c["pos"], *f))
    return np.array(rows)


def join(out_dir: Path, syllables, gap=0.15):
    from scipy.io.wavfile import write
    parts = []
    for syl in syllables:
        sr, x = read(out_dir / f"{syl}.wav")
        parts += [x, np.zeros(int(gap * sr), x.dtype)]
    write(out_dir / "all.wav", sr, np.concatenate(parts))


# ---------------------------------------------------------------- speaker edits

EDIT = re.compile(r"^\s*([^:]+):\s*([A-Z0-9]+)\s*(\+=|-=|\*=|=)\s*(-?[\d.eE+-]+)\s*$")


def expand(tract: vm.Tract, shape: str) -> list[str]:
    if "(*)" in shape:
        return [shape.replace("(*)", f"({c})") for c in CONTEXTS]
    if shape.endswith("-*"):                      # tt-tap-* -> every tap shape
        return [s for s in tract.shape_names() if s.startswith(shape[:-1])]
    return [shape]


def apply_edits(tract: vm.Tract, edits, clip=True) -> list[dict]:
    """Apply edit strings in order; returns what changed (old -> new)."""
    lo, hi, _ = tract.bounds()
    log = []
    for e in edits:
        m = EDIT.match(e)
        if not m:
            raise ValueError(f"bad edit {e!r}; expected shape:PARAM op value")
        shape, p, op, val = m.group(1).strip(), m.group(2), m.group(3), float(m.group(4))
        j = tract.names.index(p)
        for s in expand(tract, shape):
            x = tract.shape(s)
            old = x[j]
            new = {"=": val, "+=": old + val, "-=": old - val, "*=": old * val}[op]
            if clip:
                new = float(np.clip(new, lo[j], hi[j]))
            x[j] = new
            tract.set_shape(s, x)
            log.append(dict(shape=s, param=p, old=round(float(old), 4), new=round(float(new), 4)))
    return log


def load_edits(path: Path | None) -> list[str]:
    if path is None:
        return []
    data = json.loads(Path(path).read_text())
    return data["edits"] if isinstance(data, dict) else list(data)


def make_speaker(edits, out_path: Path, base=SPEAKER) -> tuple[Path, list[dict]]:
    """Copy of `base` with the edits applied, written to out_path (never to base)."""
    out_path = Path(out_path)
    if out_path.resolve() == Path(base).resolve():
        raise ValueError("refusing to overwrite the base speaker")
    tract = vm.Tract(base)
    log = apply_edits(tract, edits)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tract.write_speaker(out_path, base)
    return out_path, log


# ---------------------------------------------------------------- static geometry

def oral_constriction(tract: vm.Tract, x, start_cm=3.0) -> dict:
    """Narrowest tube section beyond `start_cm` from the glottis (skips the larynx,
    which is the global minimum of open shapes)."""
    pos, area = tract.area_function(x, 64)
    keep = pos > start_cm
    k = np.argmin(area[keep])
    return dict(area=float(area[keep][k]), pos=float(pos[keep][k]), length=float(pos[-1]))


def describe(tract: vm.Tract, name: str) -> list[dict]:
    rows = []
    if name in tract.shape_names() or "(" in name or name.endswith("-*"):
        names = expand(tract, name)
    else:
        names = expand(tract, name + "(*)")
    for s in names:
        x = tract.shape(s)
        c = oral_constriction(tract, x)
        rows.append(dict(shape=s, oral_area_cm2=round(c["area"], 3), oral_pos_cm=round(c["pos"], 2),
                         tract_cm=round(c["length"], 2),
                         params={n: round(float(v), 3) for n, v in zip(tract.names, x)}))
    return rows


# ---------------------------------------------------------------- acoustics

HOP = 0.002


def frames_db(x, sr, lo, hi, win=0.008):
    """Band energy (dB) on a 2 ms grid with `win` Hann windows."""
    n, h = int(win * sr), int(HOP * sr)
    nfft = 1 << int(np.ceil(np.log2(n)))
    f = np.fft.rfftfreq(nfft, 1 / sr)
    band = (f >= lo) & (f < hi)
    w = np.hanning(n)
    idx = np.arange(0, len(x) - n, h)
    spec = np.abs(np.fft.rfft(np.stack([x[i:i + n] * w for i in idx]), nfft)) ** 2
    return idx / sr + win / 2, 10 * np.log10(spec[:, band].sum(1) + 1e-20)


def spectrum(x, sr, nfft=8192):
    spec = np.abs(np.fft.rfft(x * np.hanning(len(x)), nfft)) ** 2
    return np.fft.rfftfreq(nfft, 1 / sr), spec


def cog_peak(x, sr, lo=1000, hi=12000):
    f, s = spectrum(x, sr)
    b = (f > lo) & (f < hi)
    cog = float((f[b] * s[b]).sum() / s[b].sum())
    sm = np.convolve(s, np.ones(25) / 25, "same")
    return cog, float(f[b][np.argmax(sm[b])])


def band_levels(x, sr, edges=(500, 2000, 4000, 8000, 12000)):
    f, s = spectrum(x, sr)
    tot = s.sum() + 1e-30
    return {f"{a // 1000 if a >= 1000 else a / 1000:g}-{b // 1000}k": round(float(10 * np.log10(s[(f >= a) & (f < b)].sum() / tot + 1e-12)), 1)
            for a, b in zip(edges[:-1], edges[1:])}



CONTINUANT = {"s", "z", "sh", "j", "ts", "ch", "h", "hy", "f"}


def measure(wav: Path, fr: Frame, speaker) -> dict:
    """Checks for one '(pause) a CV' frame. Articulatory columns come from the
    tract trajectory (exact), acoustic ones from the WAV.

    articulation (window: consonant onset - 30 ms .. vowel onset + 40 ms)
      min_area_cm2, min_pos_cm  narrowest oral section and where it is
      closed_ms                 time with the oral tract closed (<= CLOSED)
      narrow_ms                 time with oral area < 0.25 cm^2 (constriction held)
      f2_release_hz             F2 5 ms after the release (stops) or at the
                                narrowest frame (continuants; that is, the locus side)
      f2_vowel_hz               F2 at the vowel midpoint
    acoustics (levels re the vowel midpoint)
      closure_ms                silence: 0.5-12 kHz > 35 dB below the vowel
      burst_db, burst_cog_hz    first 8 ms after the acoustic closure
      release_peak              peak |x| in -2..+10 ms around the release / vowel peak
      vot_ms                    release to the return of 70-500 Hz energy (within 12 dB)
      noise_db                  peak 2-12 kHz level in the consonant window
      fric_cog_hz, fric_peak_hz, fric_bands, voice_db
                                middle 60% of the span where 2-12 kHz is within 6 dB
                                of its peak (fricatives/affricates/h); voice_db is the
                                70-500 Hz level there (voicing leaking through)
      murmur_db                 nasal murmur level (m, n)
    """
    sr, x = read(wav)
    x = x.astype(float) / 32767
    out = dict(syllable=fr.syllable)
    v0, v1 = fr.nucleus
    vmid = 0.5 * (v0 + v1)
    w0, w1 = fr.onset[0] - 0.03, v0 + 0.04

    # articulation
    A = articulation(speaker, fr, w0, vmid + 0.003)
    t, area, pos, f2 = A[:, 0], A[:, 1], A[:, 2], A[:, 4]
    inside = t < w1
    k = np.argmin(np.where(inside, area, np.inf))
    out["min_area_cm2"] = round(float(area[k]), 3)
    out["min_pos_cm"] = round(float(pos[k]), 2)
    closed = inside & (area <= CLOSED)
    out["closed_ms"] = round(float(closed.sum() * TRACK_STEP * 1000), 1)
    out["narrow_ms"] = round(float((inside & (area < 0.25)).sum() * TRACK_STEP * 1000), 1)
    if closed.any():
        rel_art = t[np.flatnonzero(closed)[-1]] + TRACK_STEP
        j = np.searchsorted(t, rel_art + 0.005)
    else:
        j = k
    if j < len(f2) and f2[j] > 0:
        out["f2_release_hz"] = round(float(f2[j]))
    out["f2_vowel_hz"] = round(float(f2[-1]))

    # acoustics
    t_hi, hi_db = frames_db(x, sr, 500, 12000)
    t_lo, lo_db = frames_db(x, sr, 70, 500, win=0.02)
    t_n, n_db = frames_db(x, sr, 2000, 12000, win=0.01)
    mid = lambda tt: (tt > vmid - .04) & (tt < vmid + .04)
    ref_hi, ref_lo, ref_n = (np.median(hi_db[mid(t_hi)]), np.median(lo_db[mid(t_lo)]), np.median(n_db[mid(t_n)]))
    vseg = x[int((vmid - .03) * sr):int((vmid + .03) * sr)]
    vrms = np.sqrt(np.mean(vseg ** 2))
    c_mid = 0.5 * sum(fr.carrier)
    quiet = (t_hi > c_mid) & (t_hi < w1) & (hi_db < ref_hi - 35)
    rel = None
    if quiet.any():
        q = np.flatnonzero(quiet)
        run = max(np.split(q, np.flatnonzero(np.diff(q) > 1) + 1), key=len)
        if len(run) * HOP >= 0.01:
            out["closure_ms"] = round(len(run) * HOP * 1000, 1)
            rel = t_hi[run[-1]] + HOP
            b = x[int(rel * sr):int((rel + .008) * sr)]
            out["burst_db"] = round(20 * np.log10(np.sqrt(np.mean(b ** 2)) / vrms + 1e-12), 1)
            # click check: release peak against the vowel's peak (JD2: 0.6-0.75)
            r = x[int((rel - .002) * sr):int((rel + .01) * sr)]
            out["release_peak"] = round(float(np.abs(r).max() / np.abs(vseg).max()), 2)
            out["burst_cog_hz"] = round(cog_peak(b, sr)[0])
            voiced = (t_lo > rel) & (lo_db > ref_lo - 12)
            if voiced.any():
                out["vot_ms"] = round((t_lo[np.flatnonzero(voiced)[0]] - rel) * 1000, 1)
    win = (t_n > w0) & (t_n < w1)
    out["noise_db"] = round(float(n_db[win].max() - ref_n), 1)
    if fr.consonant in CONTINUANT:
        ks = np.flatnonzero(win & (n_db > n_db[win].max() - 6))
        a, b = t_n[ks[0]], t_n[ks[-1]]
        if rel is not None:
            a = max(a, rel)
        if b - a > 0.012:
            pad = 0.2 * (b - a)
            seg = x[int((a + pad) * sr):int((b - pad) * sr)]
            cog, peak = cog_peak(seg, sr)
            lo_in = lo_db[(t_lo > a + pad) & (t_lo < b - pad)]
            out.update(fric_ms=round((b - a) * 1000, 1), fric_cog_hz=round(cog), fric_peak_hz=round(peak),
                       fric_db=round(20 * np.log10(np.std(seg) / vrms), 1),
                       voice_db=round(float(np.median(lo_in) - ref_lo), 1) if len(lo_in) else None,
                       fric_bands=band_levels(seg, sr))
    if fr.consonant in ("m", "n"):
        nseg = x[int((fr.onset[0] + .01) * sr):int((fr.onset[1] - .005) * sr)]
        if len(nseg) > 100:
            out["murmur_db"] = round(20 * np.log10(np.std(nseg) / vrms), 1)
    return out


def locus(rows: list[dict]) -> dict:
    """Locus equation per consonant over its vowels: F2release = k F2vowel + c;
    locus = c / (1 - k), where the line meets F2release = F2vowel."""
    by = {}
    for r in rows:
        if "f2_release_hz" in r:
            c, _ = split_syllable(r["syllable"])
            by.setdefault(c, []).append((r["f2_vowel_hz"], r["f2_release_hz"]))
    out = {}
    for c, pts in by.items():
        if len(pts) >= 3:
            v, o = np.array(pts, float).T
            k, b = np.polyfit(v, o, 1)
            out[c] = dict(slope=round(float(k), 2), intercept_hz=round(float(b)),
                          locus_hz=round(float(b / (1 - k))) if abs(1 - k) > .05 else None, n=len(pts))
    return out


# ---------------------------------------------------------------- one-call workflow

def run(edits, syllables, out_dir: Path, base=SPEAKER, label=None, onset_map=None) -> dict:
    """Write out_dir/kanon.speaker with the edits, render the syllables,
    measure them, write out_dir/summary.json. Returns the summary."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    spk, log = make_speaker(edits, out_dir / "kanon.speaker", base)
    frames = render(spk, syllables, out_dir, onset_map=onset_map)
    rows = [measure(out_dir / f"{fr.syllable}.wav", fr, spk) for fr in frames]
    try:
        base_name = str(Path(base).resolve().relative_to(ROOT))
    except ValueError:
        base_name = str(base)
    summary = dict(label=label or out_dir.name, base=base_name, edits=list(edits), onset_map=onset_map or {},
                   noise_scaling=NOISE_SCALING, noise_exponents=list(NOISE_EXPONENTS),
                   changes=log,
                   syllables=rows, locus=locus(rows))
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1))
    return summary


COLUMNS = [("min_area_cm2", "minA"), ("min_pos_cm", "pos"), ("closed_ms", "shut"), ("narrow_ms", "narw"),
           ("closure_ms", "sil"), ("burst_db", "brst"), ("release_peak", "rpk"), ("vot_ms", "VOT"), ("noise_db", "noise"),
           ("fric_cog_hz", "fCoG"), ("fric_db", "fdB"), ("voice_db", "voic"), ("murmur_db", "nas"),
           ("f2_release_hz", "F2rel"), ("f2_vowel_hz", "F2v")]


def table(summary: dict, other: dict | None = None) -> str:
    """Text table; with `other` (an earlier summary), changed cells show old>new."""
    prev = {r["syllable"]: r for r in other["syllables"]} if other else {}
    width = 12 if other else 6
    lines = ["syl  " + "".join(f"{h:>{width}s}" for _, h in COLUMNS)]
    for r in summary["syllables"]:
        cells = []
        for key, _ in COLUMNS:
            v = r.get(key, "")
            v = "" if v is None else v
            p = prev.get(r["syllable"], {}).get(key, "")
            p = "" if p is None else p
            cells.append(f"{f'{p}>{v}' if other and p != v else v!s:>{width}}")
        lines.append(f"{r['syllable']:4s} " + "".join(cells))
    return "\n".join(lines)


# ---------------------------------------------------------------- fitting a static shape

TONGUE = ("TCX", "TCY", "TTX", "TTY", "TBX", "TBY")
AREA_SCALE, POS_SCALE = 0.02, 0.2        # residual units: 0.02 cm^2, 0.2 cm


def area_at(tract: vm.Tract, x, pos: float) -> float:
    """Tube area (cm^2) at `pos` cm from the glottis, linearly interpolated."""
    p, a = tract.area_function(x, 64)
    return float(np.interp(pos, p, a))


def open_up(tract: vm.Tract, shape: str, x0, idx, area: float):
    """A closed shape has zero area derivatives. Blend its `idx` parameters
    toward its context vowel (the letter in parentheses, else the neutral
    shape) and bisect for the least blend whose oral area reaches `area`."""
    m = re.search(r"\((\w)\)$", shape)
    try:
        ref = tract.shape(m.group(1)) if m else None
    except KeyError:
        ref = None
    if ref is None:
        ref = tract.bounds()[2]
    blend = lambda t: np.where(np.isin(np.arange(len(x0)), idx), (1 - t) * x0 + t * ref, x0)
    a, b = 0.0, 1.0
    if oral_constriction(tract, blend(b))["area"] < area:
        return blend(b)
    for _ in range(20):
        t = 0.5 * (a + b)
        a, b = (t, b) if oral_constriction(tract, blend(t))["area"] < area else (a, t)
    return blend(b)


def fit(tract: vm.Tract, shape: str, area: float, pos: float | None = None, free=TONGUE,
        tol=0.25, h=0.01, iterations=30, margin=0.02, limits=None) -> tuple[np.ndarray, dict]:
    """Move the `free` parameters of one shape (least change, in units of each
    parameter's range) so that its oral constriction has `area` cm^2.

    With `pos`, the residuals are (area at pos - area) and a one-sided penalty
    if any other oral section is narrower than area - margin; the argmin
    position itself jumps between sections and is useless for derivatives.
    Levenberg-Marquardt with vtlmap.jacobian (minmod, h = fraction of the
    range) and vtlmap.bounded_step. `limits` {param: (min, max)} narrows the
    box of free parameters. Returns the best (x, constriction)."""
    lo, hi, _ = tract.bounds()
    x0 = tract.shape(shape)
    idx = tract.index(*free)
    span = (hi - lo)[idx]
    if oral_constriction(tract, x0)["area"] <= CLOSED < area:
        x0 = open_up(tract, shape, x0, idx, max(0.25, 2 * area))

    def to_x(z):
        x = x0.copy()
        x[idx] = lo[idx] + z * span
        return x

    def f(z):
        x = to_x(z)
        c = oral_constriction(tract, x)
        if pos is None:
            return np.array([(c["area"] - area) / AREA_SCALE])
        return np.array([(area_at(tract, x, pos) - area) / AREA_SCALE,
                         5 * max(0.0, area - margin - c["area"]) / AREA_SCALE])

    z = (x0[idx] - lo[idx]) / span
    zero, one = np.zeros(len(z)), np.ones(len(z))
    for k, name in enumerate(free):
        a, b = (limits or {}).get(name, (None, None))
        if a is not None:
            zero[k] = max(0.0, (a - lo[idx][k]) / span[k])
        if b is not None:
            one[k] = min(1.0, (b - lo[idx][k]) / span[k])
    z = np.clip(z, zero, one)
    r = f(z)
    lam = 1e-2
    for _ in range(iterations):
        if np.max(np.abs(r)) < tol:
            break
        J = vm.jacobian(f, z, h, zero, one, y0=r, scheme="minmod")[0]
        if not np.any(J):
            J = vm.jacobian(f, z, h, zero, one, y0=r)[0]      # stuck on a flat side
        for _ in range(8):
            d = vm.bounded_step(J, -r, zero - z, one - z, lam)
            rt = f(z + d)
            shut = area > CLOSED and oral_constriction(tract, to_x(z + d))["area"] <= CLOSED
            if not shut and np.sum(rt ** 2) < np.sum(r ** 2):
                z, r, lam = z + d, rt, max(lam / 3, 1e-4)
                break
            lam *= 4
        else:
            break
    x = to_x(z)
    return x, oral_constriction(tract, x)


# ---------------------------------------------------------------- command line

def ab(before: Path, after: Path, syllables, out: Path, gap=0.35):
    """Listening set: <syl>-before.wav / <syl>-after.wav copies and ab.wav
    (before, after, before, after, ... with gaps)."""
    import shutil
    from scipy.io.wavfile import write
    out.mkdir(parents=True, exist_ok=True)
    parts = []
    for syl in syllables:
        for tag, d in (("before", before), ("after", after)):
            shutil.copy(Path(d) / f"{syl}.wav", out / f"{syl}-{tag}.wav")
            sr, x = read(Path(d) / f"{syl}.wav")
            parts += [x, np.zeros(int(gap * sr), x.dtype)]
    write(out / "ab.wav", sr, np.concatenate(parts))


def _summary(path):
    p = Path(path)
    return json.loads((p / "summary.json" if p.is_dir() else p).read_text())


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("show", help="static shapes: oral constriction and parameters")
    a.add_argument("names", nargs="+", help="consonant (tb-velar-closure), shape, or onset (k, sh, ...)")
    a.add_argument("--speaker", default=SPEAKER)
    a.add_argument("-e", "--edit", action="append", default=[])
    a.add_argument("--edits")
    a.add_argument("--params", action="store_true", help="print all parameters")

    a = sub.add_parser("run", help="edit, write the speaker, render and measure")
    a.add_argument("out", help="output folder (speaker, WAVs, summary.json)")
    a.add_argument("-e", "--edit", action="append", default=[], help="shape:PARAM op value")
    a.add_argument("--edits", help="JSON file with {\"edits\": [...]} applied first")
    a.add_argument("-s", "--syll", default=",".join(DEFAULT_SYLLABLES), help="comma-separated CV syllables")
    a.add_argument("--base", default=SPEAKER)
    a.add_argument("--map", action="append", default=[], help="onset override, e.g. w=w or w=M:0.06")
    a.add_argument("--compare", help="earlier output folder to diff against")
    a.add_argument("--no-noise-scaling", action="store_true",
                   help="VTL's original noise-source constants (JD2 sizes)")
    a.add_argument("--noise-exponents", default="1,2,-1",
                   help="exponents of the size scale for lengths, areas, cutoffs")
    a.add_argument("--glottal-noise", default="1,1000",
                   help="aspiration source gain factor and cutoff Hz (VTL: 1,1000)")
    a.add_argument("--aperiodicity", default="0,0",
                   help="glottal jitter and shimmer in percent per cycle (VTL: 0,0)")
    a.add_argument("--lung-pressure", type=float,
                   help="lung pressure in dPa instead of VTL's fixed 8000 (glottis clamps at 16000)")

    a = sub.add_parser("fit", help="fit one shape's constriction area/position; prints edits")
    a.add_argument("shape", help="shape name; (*) fits all three contexts")
    a.add_argument("--area", type=float, required=True)
    a.add_argument("--pos", type=float)
    a.add_argument("--free", default=",".join(TONGUE))
    a.add_argument("--speaker", default=SPEAKER)
    a.add_argument("--edits", help="edits applied before fitting")
    a.add_argument("--append", help="append the fitted edits to this JSON file")
    a.add_argument("--limit", action="append", default=[], help="bound a free parameter, e.g. TTY<=-0.7 or TTX>=2.8")

    a = sub.add_parser("ab", help="before/after listening set from two run folders")
    a.add_argument("before")
    a.add_argument("after")
    a.add_argument("out")
    a.add_argument("-s", "--syll", required=True)

    args = ap.parse_args(argv)
    if args.cmd == "show":
        tr = vm.Tract(args.speaker)
        apply_edits(tr, load_edits(args.edits) + args.edit)
        for n in args.names:
            for shape in ONSET_SHAPES.get(n, [n]):
                for r in describe(tr, shape):
                    print(f"{r['shape']:34s} oral min {r['oral_area_cm2']:.3f} cm2 at {r['oral_pos_cm']:5.2f} cm"
                          f" (tract {r['tract_cm']:.2f} cm)")
                    if args.params:
                        print("   ", " ".join(f"{k}={v}" for k, v in r["params"].items()))
    elif args.cmd == "run":
        omap = {}
        for m in args.map:
            k, _, v = m.partition("=")
            omap[k] = v.split("+")
        edits = load_edits(args.edits) + args.edit
        global NOISE_SCALING
        NOISE_SCALING = not args.no_noise_scaling
        global NOISE_EXPONENTS
        NOISE_EXPONENTS = tuple(float(v) for v in args.noise_exponents.split(","))
        global LUNG_PRESSURE
        LUNG_PRESSURE = args.lung_pressure
        global APERIODICITY
        APERIODICITY = tuple(float(v) for v in args.aperiodicity.split(","))
        global GLOTTAL_NOISE
        GLOTTAL_NOISE = tuple(float(v) for v in args.glottal_noise.split(","))
        s = run(edits, args.syll.split(","), Path(args.out), args.base, onset_map=omap or None)
        print(table(s, _summary(args.compare) if args.compare else None))
        print("locus:", json.dumps(s["locus"]))
        print(f"wrote {args.out}/kanon.speaker, {args.out}/all.wav, {args.out}/summary.json")
    elif args.cmd == "fit":
        tr = vm.Tract(args.speaker)
        apply_edits(tr, load_edits(args.edits))
        free = args.free.split(",")
        limits = {}
        for l in args.limit:
            m = re.match(r"([A-Z0-9]+)\s*(<=|>=)\s*(-?[\d.]+)$", l)
            if not m:
                raise SystemExit(f"bad --limit {l!r}")
            a, b = limits.get(m.group(1), (None, None))
            limits[m.group(1)] = (a, float(m.group(3))) if m.group(2) == "<=" else (float(m.group(3)), b)
        edits = []
        for shape in expand(tr, args.shape):
            before = oral_constriction(tr, tr.shape(shape))
            x, c = fit(tr, shape, args.area, args.pos, free, limits=limits)
            print(f"{shape}: {before['area']:.3f} cm2 @ {before['pos']:.2f} -> {c['area']:.3f} cm2 @ {c['pos']:.2f}")
            for j in tr.index(*free):
                old = tr.shape(shape)[j]
                if abs(x[j] - old) > 1e-4:
                    edits.append(f"{shape}:{tr.names[j]}={x[j]:.4f}")
                    print(f"   {tr.names[j]} {old:.3f} -> {x[j]:.3f}")
            tr.set_shape(shape, x)
        if args.append:
            p = Path(args.append)
            data = json.loads(p.read_text()) if p.exists() else {"edits": []}
            data["edits"] += edits
            p.write_text(json.dumps(data, indent=1) + "\n")
            print(f"appended {len(edits)} edits to {p}")
        else:
            print(json.dumps(edits, indent=1))
    elif args.cmd == "ab":
        ab(Path(args.before), Path(args.after), args.syll.split(","), Path(args.out))
        print(f"wrote {args.out}/ab.wav")


if __name__ == "__main__":
    main()
