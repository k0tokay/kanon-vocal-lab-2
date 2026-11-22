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

ROOT = Path(__file__).resolve().parents[2]
SPEAKER = ROOT / "speakers/fulkhisa-kanon/fulkhisa-kanon-v0-8-vtl24.speaker"
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
        if n["chain_flag"] != 1 or not phrases:
            phrases.append([0, 0])
        moras, acc = phrases[-1]
        if acc == 0 and n["acc"] != 0:
            phrases[-1][1] = moras + n["acc"]
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
BASE = {"p": .055, "b": .045, "t": .055, "d": .045, "k": .06, "g": .045,
        "s": .085, "z": .06, "S": .09, "C": .08, "h": .065, "f": .07, "v": .05,
        "ts": .08, "tS": .085, "dZ": .065, "m": .05, "n": .045, "N": .05,
        "4": .022, "j": .035, "u": .04}
FRICATIVE = {"s", "S", "C", "h", "f", "ts", "tS"}


@dataclass
class Segment:
    name: str
    duration: float
    t0: float = 0.0
    f0: list = field(default_factory=lambda: [0.0, 0.0, 0.0])


def moraic_nasal(next_onset):
    if next_onset in ("p", "b", "m", "py", "by", "my"):
        return "m"
    if next_onset in ("t", "d", "n", "ts", "ch", "j", "s", "z", "r", "ny"):
        return "n"
    return "N"


def to_segments(units, mora=0.135, rate=1.0):
    """Mora-timed durations; devoiced vowels fold into a voiceless onset.

    Returns the segment list and, per unit, its (start, end) time.
    """
    mora /= rate
    segments, owned = [], []          # owned[i] = segments belonging to units[i]
    for i, u in enumerate(units):
        if isinstance(u, Pause):
            seg = [Segment("", (0.12 if u.kind == "sil" else 0.22) / rate)]
        else:
            nxt = units[i + 1] if i + 1 < len(units) else None
            final = nxt is None or isinstance(nxt, Pause)
            stretch = 1.35 if final else 1.0
            if u.vowel == "cl":
                seg = [Segment("cl", mora * .85)]
            elif u.vowel == "N":
                seg = [Segment(moraic_nasal(nxt.consonant if isinstance(nxt, Mora) else ""), mora * stretch)]
            else:
                seg = [Segment(s, BASE[s] / rate) for s in ONSET.get(u.consonant, [])]
                vowel_time = max(.04 / rate, mora * stretch - sum(s.duration for s in seg))
                if u.vowel.isupper():
                    # Devoiced vowel: lengthen a voiceless fricative/affricate
                    # onset, otherwise breathe it out as /h/.
                    if seg and seg[-1].name in FRICATIVE:
                        seg[-1].duration += .7 * vowel_time
                    else:
                        seg.append(Segment("h", .6 * vowel_time))
                else:
                    seg.append(Segment(u.vowel, vowel_time))
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
        lines.append(f"name = {s.name}; duration_s = {s.duration:.6f}; "
                     f"f0_20%_Hz = {f[0]:.2f}; f0_50%_Hz = {f[1]:.2f}; f0_80%_Hz = {f[2]:.2f};")
    path.write_text("\n".join(lines) + "\n")


_lib = None


def synthesize(seg, wav):
    global _lib
    if _lib is None:
        _lib = ct.CDLL(str(LIB))
        assert _lib.vtlInitialize(bytes(SPEAKER)) == 0
    ges = seg.with_suffix(".ges")
    assert _lib.vtlSegmentSequenceToGesturalScore(bytes(seg), bytes(ges)) == 0
    count = ct.c_int()
    assert _lib.vtlGesturalScoreToAudio(bytes(ges), b"", b"", None, ct.byref(count), 0, 0) == 0
    buf = (ct.c_double * count.value)()
    assert _lib.vtlGesturalScoreToAudio(bytes(ges), b"", b"", buf, ct.byref(count), 0, 0) == 0
    audio = np.frombuffer(buf, dtype=np.float64)
    audio = audio / max(1e-9, np.abs(audio).max()) * .8
    write(wav, 44100, (audio * 32767).astype(np.int16))
    return audio


def render(text, out_stem, params=Fujisaki(), accent=True, rate=1.0):
    units = parse(text)
    segments, spans = to_segments(units, rate=rate)
    phrases, accents = commands(units, spans, params)
    if not accent:
        accents = []
    for s in segments:
        s.f0 = list(f0_curve(np.array([s.t0 + r * s.duration for r in (.2, .5, .8)]),
                             phrases, accents, params))
    out_stem.parent.mkdir(parents=True, exist_ok=True)
    seg = out_stem.with_suffix(".seg")
    write_seg(segments, seg)
    synthesize(seg, out_stem.with_suffix(".wav"))
    t = np.arange(0, segments[-1].t0 + segments[-1].duration, .005)
    return dict(text=text, units=units, segments=segments, phrases=phrases,
                accents=accents, t=t, f0=f0_curve(t, phrases, accents, params))
