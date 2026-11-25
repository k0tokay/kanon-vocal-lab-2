"""Japanese text -> VTL segment sequence with Tokyo-dialect pitch accent.

Accent phrases and nucleus positions come from OpenJTalk full-context labels
(pyopenjtalk). F0 is a Fujisaki command-response contour, durations are
mora-timed rules, so no recorded speaker's prosody enters the output.
"""
import ctypes as ct
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pyopenjtalk
from scipy.io.wavfile import write

from gestures import Score

ROOT = Path(__file__).resolve().parents[2]
SPEAKER = Path(os.environ.get("VTL_SPEAKER", ROOT / "speakers/fulkhisa-kanon/fulkhisa-kanon-v0-8-vtl24.speaker"))
LIB = Path(os.environ.get("VTL_LIB", ROOT / "build-mac/gui/libVocalTractLabApi.dylib"))


# ---------------------------------------------------------------- labels -> moras

@dataclass
class Mora:
    consonant: str          # OpenJTalk phoneme, "" if none
    vowel: str              # a i u e o, A I U E O (devoiced), N, cl
    accent_type: int        # F:f2, 0 = heiban
    position: int           # 1-based mora position in the accent phrase
    phrase_len: int
    phrase_id: int
    breath_id: int


@dataclass
class Pause:
    kind: str               # "sil" or "pau"


def parse(text):
    """Group OpenJTalk phonemes into moras carrying accent-phrase info."""
    units, consonant = [], ""
    phrase_id, breath_id, last_key = -1, 0, None
    for label in pyopenjtalk.extract_fullcontext(text):
        phone = re.search(r"-(.+?)\+", label).group(1)
        if phone in ("sil", "pau"):
            units.append(Pause(phone))
            if phone == "pau":
                breath_id += 1
            continue
        a = re.search(r"/A:([\d\-]+)\+(\d+)\+(\d+)/", label)
        f = re.search(r"/F:(\d+)_(\d+)#", label)
        position, phrase_len, accent_type = int(a.group(2)), int(f.group(1)), int(f.group(2))
        # A new accent phrase starts when the forward position restarts at 1.
        key = (breath_id, position)
        if position == 1 and last_key != key:
            phrase_id += 1
        last_key = key
        if phone in "aiueoAIUEO" or phone in ("N", "cl"):
            units.append(Mora(consonant, phone, accent_type, position,
                              phrase_len, phrase_id, breath_id))
            consonant = ""
        else:
            consonant = phone
    fix_heiban(text, units)
    return units


def njd_phrases(text):
    """(moras, accent type) per accent phrase from NJD, where 0 = heiban."""
    phrases = []
    for n in pyopenjtalk.run_frontend(text):
        if n["pos"] == "記号" or n["mora_size"] == 0:
            continue
        # The first word of a phrase carries the accent of the whole phrase; the other
        # words keep values of their own (a particle's made heiban phrases odaka).
        if n["chain_flag"] != 1 or not phrases:
            phrases.append([0, n["acc"]])
        phrases[-1][0] += n["mora_size"]
    return phrases


def fix_heiban(text, units):
    """Full-context labels write heiban as type = mora count, like odaka.

    Restore type 0 from NJD when its phrase list lines up with the labels.
    """
    moras = [u for u in units if isinstance(u, Mora)]
    ids = sorted({u.phrase_id for u in moras})
    njd = njd_phrases(text)
    lengths = [moras[[u.phrase_id for u in moras].index(i)].phrase_len for i in ids]
    if [m for m, _ in njd] != lengths:
        return False
    for i, (_, acc) in zip(ids, njd):
        if acc == 0:
            for u in moras:
                if u.phrase_id == i:
                    u.accent_type = 0
    return True


# ---------------------------------------------------------------- moras -> segments

# Consonant onsets as VTL SAMPA sequences. Palatalised onsets get a short glide.
ONSET = {
    "k": ["k"], "g": ["g"], "s": ["s"], "z": ["z"], "t": ["t"], "d": ["d"],
    "n": ["n"], "h": ["h"], "b": ["b"], "p": ["p"], "m": ["m"], "r": ["4"],
    "y": ["j"], "w": ["u"], "f": ["f"], "v": ["v"],
    "ts": ["ts"], "ch": ["tS"], "j": ["dZ"], "sh": ["S"], "hy": ["C"],
    "ky": ["k", "j"], "gy": ["g", "j"], "ny": ["n", "j"], "my": ["m", "j"],
    "ry": ["4", "j"], "by": ["b", "j"], "py": ["p", "j"], "dy": ["d", "j"],
    "ty": ["t", "j"],
}
# Japanese-specific symbols, supported natively by this VTL build:
# alveolo-palatal s\ z\ ts\ dz\ and the unrounded vowel M.
# w: VTL has no /w/; a short M left the lips open (0.44 cm^2) and F2 flat,
# a 50 ms rounded u narrows the lips to 0.15 cm^2 and starts F2 ~300 Hz
# lower (experiments/consonant-tuning).
JA_ONSET = {"sh": ["s\\"], "ch": ["ts\\"], "j": ["dz\\"], "w": ["u"]}
# Onsets that get a short palatal glide before /i/ when palatal_i=True.
PALATALIZE = {"k", "g", "n", "m", "b", "p", "r"}
# Durations follow the consonants of 51 JVS women at the same mora length (median
# 140 ms; experiments/consonant-articulation). VTL places closures exactly (segment
# minus VOT), so a short segment is a short closure and a weak burst.
BASE = {"p": .075, "b": .065, "t": .07, "d": .055, "k": .08, "g": .065,
        "s": .10, "z": .095, "S": .115, "C": .105, "h": .075, "f": .085, "v": .06,
        "ts": .115, "tS": .115, "dZ": .095, "m": .065, "n": .06, "N": .06,
        "4": .035, "j": .075, "u": .065, "M": .05,
        "s\\": .115, "z\\": .105, "ts\\": .115, "dz\\": .105}
GLIDE = .04             # /j/ after another consonant (kya, ...)
VELIC = 2.0             # VTL's velic openings (m N .3, n .2 cm2) give Kanon too weak a murmur at 1-3 kHz
# Segments that get the Japanese timing of GesturalScore.cpp (label "timing = ja").
JA_TIMING = {"p", "t", "k", "b", "d", "g", "s", "z", "s\\", "z\\", "C", "f", "ts", "ts\\", "dz\\", "4",
             "m", "n", "N"}
# Single numbers of it: the tap only has to come within .13 cm2 for 14 ms (no full closure),
# approaches slowly and leaves fast.
# /t/: the glottis closes earlier than for /k/ (aspiration 10 dB too strong otherwise).
TIMING = {"t": {"glottis_end_s": -.055},
          "4": {"contact_s": .014, "contact_cm2": .13, "onset_tau_s": .010, "offset_tau_s": .006}}
FRICATIVE = {"s", "S", "C", "h", "f", "ts", "tS", "s\\", "ts\\"}


@dataclass
class Segment:
    name: str
    duration: float
    t0: float = 0.0
    f0: list = field(default_factory=lambda: [0.0, 0.0, 0.0])
    tag: str = ""           # Japanese-specific edit applied to the score


def moraic_nasal(next_onset):
    if next_onset in ("p", "b", "m", "py", "by", "my"):
        return "m"
    if next_onset in ("t", "d", "n", "ts", "ch", "j", "s", "z", "r", "ny"):
        return "n"
    return "N"


def onset(consonant, vowel, japanese, palatal_i=False, after_vowel=False):
    """VTL segments for a mora onset, tagged for later score edits."""
    if not consonant:
        return []
    if japanese and consonant == "j" and after_vowel:
        names = ["z\\"]                     # aji = [aʑi], no closure between vowels
    elif japanese and consonant == "h" and vowel in "iI":
        names = ["C"]                       # hi = [çi]
    elif japanese and consonant in JA_ONSET:
        names = JA_ONSET[consonant]
    else:
        names = ONSET.get(consonant, [])
    if japanese and palatal_i and consonant in PALATALIZE and vowel in "iI":
        names = names + ["j"]               # ki = [kʲi]
    tag = "phi" if japanese and consonant == "f" else ""
    return [Segment(n, BASE.get(n, .04) if n != "j" or len(names) == 1 else GLIDE,
                    tag=tag if k == 0 else "") for k, n in enumerate(names)]


def vowel_symbol(v, japanese):
    return "M" if japanese and v == "u" else v


def to_segments(units, mora=0.135, rate=1.0, japanese=True, palatal_i=False,
                devoice="keep"):
    """Mora-timed durations.

    Devoiced vowels: with devoice="keep" (and japanese=True) the vowel is
    kept, shortened, and later made voiceless in the score; with "drop" it
    is removed and folded into a voiceless onset.
    palatal_i adds a short /j/ after k g n m b p r before /i/.

    Returns the segment list and, per unit, its (start, end) time.
    """
    mora /= rate
    segments, owned = [], []          # owned[i] = segments belonging to units[i]
    for i, u in enumerate(units):
        if isinstance(u, Pause):
            # VTL lengthens a first pause below 100 ms, which would shift everything after it.
            seg = [Segment("", max(.1, 0.12 / rate) if u.kind == "sil" else 0.22 / rate)]
        else:
            nxt = units[i + 1] if i + 1 < len(units) else None
            final = nxt is None or isinstance(nxt, Pause)
            stretch = 1.35 if final else 1.0
            if u.vowel == "cl":
                seg = [Segment("cl", mora * .85)]
            elif u.vowel == "N":
                seg = [Segment(moraic_nasal(nxt.consonant if isinstance(nxt, Mora) else ""), mora * stretch)]
            else:
                prev = units[i - 1] if i else None
                seg = onset(u.consonant, u.vowel, japanese, palatal_i,
                            after_vowel=isinstance(prev, Mora) and prev.vowel in "aiueo")
                for s in seg:
                    s.duration /= rate
                vowel_time = max(.04 / rate, mora * stretch - sum(s.duration for s in seg))
                if u.vowel.isupper() and japanese and devoice == "keep":
                    seg.append(Segment(vowel_symbol(u.vowel.lower(), japanese), .75 * vowel_time,
                                       tag="devoiced"))
                    for s in seg[:-1]:
                        s.tag = s.tag or "devoiced-onset"
                elif u.vowel.isupper():
                    # Devoiced vowel: lengthen a voiceless fricative/affricate
                    # onset, otherwise breathe it out as /h/.
                    if seg and seg[-1].name in FRICATIVE:
                        seg[-1].duration += .7 * vowel_time
                    else:
                        seg.append(Segment("h", .6 * vowel_time))
                else:
                    seg.append(Segment(vowel_symbol(u.vowel, japanese), vowel_time))
        segments += seg
        owned.append(seg)
    # Geminate closure becomes extra duration of the following consonant;
    # before a pause it is silence.
    for i, s in enumerate(segments):
        if s.name == "cl":
            if i + 1 < len(segments) and segments[i + 1].name:
                s.name = "_gem"
            else:
                s.name = ""
    t = 0.0
    for s in segments:
        s.t0, t = t, t + s.duration
    spans = [(seg[0].t0, seg[-1].t0 + seg[-1].duration) for seg in owned]
    out, pending = [], None
    for s in segments:
        if s.name == "_gem":
            pending = s
            continue
        if pending is not None:
            s.t0, s.duration, pending = pending.t0, pending.duration + s.duration, None
        out.append(s)
    return out, spans


# ---------------------------------------------------------------- Fujisaki F0

@dataclass
class Fujisaki:
    fb: float = 170.0       # base frequency (Hz)
    ap_first: float = .32   # phrase command at utterance start
    ap_next: float = .22    # phrase command after each pause
    aa: float = .30         # accent command amplitude
    alpha: float = 3.0
    beta: float = 20.0
    gamma: float = .9
    lead: float = .05       # commands lead the segments they govern


def commands(units, spans, p):
    phrases, accents = [], []
    by_phrase = {}
    for u, span in zip(units, spans):
        if isinstance(u, Mora):
            by_phrase.setdefault(u.phrase_id, []).append((u, span))
    seen_breath = set()
    for pid in sorted(by_phrase):
        moras = by_phrase[pid]
        u0 = moras[0][0]
        start, end = moras[0][1][0], moras[-1][1][1]
        if u0.breath_id not in seen_breath:
            seen_breath.add(u0.breath_id)
            phrases.append((start - .2, p.ap_first if not phrases else p.ap_next))
        typ = u0.accent_type
        # Tokyo accent: rise after the first mora unless the nucleus is on it.
        on = moras[0][1][0] if typ == 1 or len(moras) == 1 else moras[1][1][0]
        off = end if typ == 0 else moras[min(typ, len(moras)) - 1][1][1]
        amp = p.aa * (0.8 if typ == 0 else 1.0)
        if off > on:
            accents.append((on - p.lead, off - p.lead, amp))
    return phrases, accents


def f0_curve(t, phrases, accents, p):
    log = np.full_like(t, np.log(p.fb))
    for t0, ap in phrases:
        x = np.clip(t - t0, 0, None)
        log += ap * p.alpha**2 * x * np.exp(-p.alpha * x)
    ga = lambda x: np.minimum(1 - (1 + p.beta * x) * np.exp(-p.beta * x), p.gamma) * (x > 0)
    for t1, t2, aa in accents:
        log += aa * (ga(t - t1) - ga(t - t2))
    return np.exp(log)


# ---------------------------------------------------------------- output

def write_seg(segments, path):
    lines = []
    for s in segments:
        f = s.f0 if s.name else [0, 0, 0]
        ja = " timing = ja;" if s.name in JA_TIMING else ""
        ja += "".join(f" {k} = {v:.4f};" for k, v in TIMING.get(s.name, {}).items())
        lines.append(f"name = {s.name}; duration_s = {s.duration:.6f}; "
                     f"f0_20%_Hz = {f[0]:.2f}; f0_50%_Hz = {f[1]:.2f}; f0_80%_Hz = {f[2]:.2f};{ja}")
    path.write_text("\n".join(lines) + "\n")


def patch_score(ges, segments):
    """Japanese edits that the seg format cannot express.

    - devoiced vowels keep their tract shape but get an open glottis,
      together with their voiceless onset
    - fu: bilabial instead of labiodental fricative
    - nasals: wider velic opening (VELIC)

    [ɯ] (M) and the alveolo-palatals (s\\ z\\ ts\\ dz\\) are handled by
    VTL itself and need no edit here.
    """
    score = Score(ges)
    for i, s in enumerate(segments):
        t1 = s.t0 + s.duration
        if s.tag == "devoiced":
            start = s.t0
            k = i - 1
            while k >= 0 and segments[k].tag == "devoiced-onset":
                start = segments[k].t0
                k -= 1
            score["glottal-shape-gestures"].paint(start, t1, "voiceless-fricative")
        elif s.tag == "phi":
            for g in score["lip-gestures"].items:       # any overlap: in fast speech the gesture lies before the segment
                if g[0] < t1 and g[1] > s.t0 - .06:
                    g[2]["value"] = g[2]["value"].replace("ll-dental-fricative", "ll-labial-fricative")
    for g in score["velic-gestures"].items:
        if any(s.name in ("m", "n", "N") and min(g[1], s.t0 + s.duration) - max(g[0], s.t0) > .005 for s in segments):
            g[2]["value"] = f"{float(g[2]['value']) * VELIC:.6f}"       # not the open velum of the pauses
    score.save()


_lib = None


def use_speaker(speaker):
    """Load the API once and (re)initialise it when the speaker changes."""
    global _lib
    if _lib is None:
        _lib = ct.CDLL(str(LIB))
        _lib.speaker = None
    if _lib.speaker != Path(speaker):
        if _lib.speaker is not None:
            _lib.vtlClose()
        assert _lib.vtlInitialize(bytes(Path(speaker))) == 0
        constants = [ct.c_int() for _ in range(4)]
        assert _lib.vtlGetConstants(*map(ct.byref, constants)) == 0
        _lib.rate = constants[0].value      # 48 kHz for VTL 2.4
        _lib.tube_sections = constants[1].value
        _lib.speaker = Path(speaker)
    return _lib


def synthesize(seg, wav, segments=None, speaker=SPEAKER):
    use_speaker(speaker)
    ges = seg.with_suffix(".ges")
    assert _lib.vtlSegmentSequenceToGesturalScore(bytes(seg), bytes(ges)) == 0
    if segments is not None:
        patch_score(ges, segments)
    count = ct.c_int()
    assert _lib.vtlGesturalScoreToAudio(bytes(ges), b"", b"", None, ct.byref(count), 0, 0) == 0
    buf = (ct.c_double * count.value)()
    assert _lib.vtlGesturalScoreToAudio(bytes(ges), b"", b"", buf, ct.byref(count), 0, 0) == 0
    audio = np.frombuffer(buf, dtype=np.float64)
    audio = audio / max(1e-9, np.abs(audio).max()) * .8
    write(wav, _lib.rate, (audio * 32767).astype(np.int16))
    return audio


def render(text, out_stem, params=Fujisaki(), accent=True, rate=1.0,
           japanese=True, palatal_i=False, devoice="keep", speaker=SPEAKER, f0_model="auto", f0_mean=218.0):
    """f0_model: "auto" uses the learned F0 when its model file is available and params is untouched,
    else the Fujisaki rules; None always uses the rules; or a model loaded with accent_f0.load."""
    units = parse(text)
    segments, spans = to_segments(units, rate=rate, japanese=japanese,
                                  palatal_i=palatal_i, devoice=devoice)
    phrases, accents = commands(units, spans, params)
    if not accent:
        accents = []
    for s in segments:
        s.f0 = list(f0_curve(np.array([s.t0 + r * s.duration for r in (.2, .5, .8)]),
                             phrases, accents, params))
    learned = None
    if f0_model == "auto":
        import accent_f0
        f0_model = accent_f0.default() if accent and params == Fujisaki() else None
    if f0_model is not None and accent:
        import accent_f0
        learned = accent_f0.apply(f0_model, units, spans, segments, f0_mean)
    out_stem.parent.mkdir(parents=True, exist_ok=True)
    seg = out_stem.with_suffix(".seg")
    write_seg(segments, seg)
    synthesize(seg, out_stem.with_suffix(".wav"), segments if japanese else None, speaker)
    t = np.arange(0, segments[-1].t0 + segments[-1].duration, .005)
    return dict(text=text, units=units, segments=segments, spans=spans, phrases=phrases,
                accents=accents, t=t, f0=learned(t) if learned else f0_curve(t, phrases, accents, params))
