"""Variants of the score or the speaker, switched one at a time against "base".

A variant may give
  speaker: another speaker file (made here from v1.4.1),
  static:  arguments sK=value of build/ges_probe (static parameters of the TBCM),
  edit:    a function (ges, segments) that rewrites the gestural score in place,
  accent:  False for the phrase component of the F0 only.
The same speaker, static parameters and edit are used for the steady vowels.
"""
import re
from pathlib import Path
import numpy as np
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BASE = ROOT / "speakers/fulkhisa-kanon/fulkhisa-kanon-v1-4-1.speaker"
SPK = HERE / "build/speakers"
IDX = dict(f0=0, pressure=1, lca=2, ia=3, pca=4, ct=5, ta=6, flutter=7)
CONSONANT_SHAPES = ("voiced-plosive", "voiced-fricative", "voiceless-plosive", "voiceless-fricative")


def tbcm_block(text):
    i = text.index('<glottis_model type="Triangular body-cover glottis"')
    j = text.index('</glottis_model>', i)
    return i, j


def shapes(path=BASE):
    t = Path(path).read_text()
    i, j = tbcm_block(t)
    out = {}
    for m in re.finditer(r'<shape name="([^"]+)">(.*?)</shape>', t[i:j], re.S):
        out[m.group(1)] = [float(v) for v in re.findall(r'value="([-\d.]+)"', m.group(2))]
    return out


def make_speaker(name, changes, static=None, src=BASE):
    """changes: {shape: {param: value}}; static: {abbr: value}."""
    t = Path(src).read_text()
    i, j = tbcm_block(t)
    b = t[i:j]
    for shape, ch in changes.items():
        m = re.search(r'(<shape name="%s">)(.*?)(</shape>)' % re.escape(shape), b, re.S)
        body = m.group(2)
        for p, v in ch.items():
            body = re.sub(r'(<control_param index="%d" value=")[-\d.]+(")' % IDX[p], r'\g<1>%.6f\g<2>' % v, body)
        b = b[:m.start(2)] + body + b[m.end(2):]
    for abbr, v in (static or {}).items():
        b = re.sub(r'(abbr="%s"[^>]*value=")[-\d.]+(")' % abbr, r'\g<1>%.6f\g<2>' % v, b)
    SPK.mkdir(parents=True, exist_ok=True)
    out = SPK / f"{name}.speaker"
    out.write_text(t[:i] + b + t[j:])
    return out


# ---------------------------------------------------------------- score edits

def tier(root, kind):
    return next(s for s in root.iter("gesture_sequence") if s.get("type") == kind)


def gestures(seq):
    t, out = 0.0, []
    for g in seq.findall("gesture"):
        d = float(g.get("duration_s"))
        out.append((t, t + d, g))
        t += d
    return out


def edit_xml(*fns):
    def edit(ges, segments):
        tree = ET.parse(ges)
        for fn in fns:
            fn(tree.getroot(), segments)
        tree.write(ges)
    return edit


def all_modal(root, segments):
    for _, _, g in gestures(tier(root, "glottal-shape-gestures")):
        if g.get("value") in CONSONANT_SHAPES:
            g.set("value", "modal")


def flat_f0(root, segments):
    seq = tier(root, "f0-gestures")
    gs = gestures(seq)
    st = sum((b - a) * float(g.get("value")) for a, b, g in gs) / gs[-1][1]
    for _, _, g in gs:
        g.set("value", "%.6f" % st)
        g.set("slope", "0.000000")


def glottal_tau(tau):
    def fn(root, segments):
        for _, _, g in gestures(tier(root, "glottal-shape-gestures")):
            g.set("time_constant_s", "%.6f" % tau)
    return fn


def fast_close(tau, delay=0.0):
    """The glottal gesture right after a voiceless one is approached with time constant tau,
    and begins delay seconds later (the voiceless gesture is that much longer)."""
    def fn(root, segments):
        gs = gestures(tier(root, "glottal-shape-gestures"))
        for (_, _, a), (_, _, g) in zip(gs, gs[1:]):
            if a.get("value").startswith("voiceless") and not g.get("value").startswith("voiceless"):
                g.set("time_constant_s", "%.6f" % tau)
                d = min(delay, .5 * float(g.get("duration_s")))
                a.set("duration_s", "%.6f" % (float(a.get("duration_s")) + d))
                g.set("duration_s", "%.6f" % (float(g.get("duration_s")) - d))
    return fn


def f0_at(root):
    """F0 target (Hz) of the score as a function of time (piecewise linear in st)."""
    gs = gestures(tier(root, "f0-gestures"))
    def f(t):
        for a, b, g in gs:
            if a <= t < b:
                st = float(g.get("value")) + float(g.get("slope")) * (t - a)
                return 2 ** (st / 12)        # VTL: reference 1 Hz
        return f(gs[-1][1] - 1e-6)
    return f


def pressure_follows_f0(k, ref=220.0, step=.02):
    """Lung pressure p = 8000 (F0/ref)^k while voiced; onset and release keep their ramps.
    The pressure gesture during the utterance is cut into steps of 20 ms."""
    def fn(root, segments):
        f = f0_at(root)
        seq = tier(root, "lung-pressure-gestures")
        gs = gestures(seq)
        new = []
        for a, b, g in gs:
            v = float(g.get("value"))
            if v <= 0 or b - a < 2 * step:
                new.append((b - a, g.attrib))
                continue
            n = int(round((b - a) / step))
            for i in range(n):
                t = a + (i + .5) * (b - a) / n
                at = dict(g.attrib)
                at["value"] = "%.6f" % (v * (f(t) / ref) ** k)
                at["time_constant_s"] = "0.020000"
                new.append(((b - a) / n, at))
        for g in list(seq):
            seq.remove(g)
        for d, at in new:
            at = dict(at)
            at["duration_s"] = "%.6f" % d
            ET.SubElement(seq, "gesture", at)
    return fn


# ---------------------------------------------------------------- variants

def _variants():
    sh = shapes()
    modal = sh["modal"]
    keep_register = {s: dict(ta=modal[IDX["ta"]], ct=modal[IDX["ct"]]) for s in CONSONANT_SHAPES}
    keep_all_but_abduction = {}
    for s in CONSONANT_SHAPES:
        keep_all_but_abduction[s] = dict(ta=modal[IDX["ta"]], ct=modal[IDX["ct"]], flutter=modal[IDX["flutter"]])
    reg_voiced = {s: dict(v) for s, v in keep_register.items()}
    reg_voiced["voiced-plosive"].update(lca=modal[IDX["lca"]], ia=modal[IDX["ia"]], pca=modal[IDX["pca"]])
    import json
    inv_path = HERE / "build/inverted.json"                            # invert.py
    if inv_path.exists():
        inv = json.loads(inv_path.read_text())
        matched = {s: {k: inv[s][k] for k in ("lca", "ia", "pca", "ct", "ta", "flutter")} for s in CONSONANT_SHAPES}
        spk_match = make_speaker("a_matched", matched)
    else:
        spk_match = None
    spk_reg = make_speaker("a_register", keep_register)
    spk_regv = make_speaker("a_reg_voiced", reg_voiced)
    return {
        "base": {},
        # (a) the consonant shapes keep the register (TA, CT) of modal
        "a_register": dict(speaker=spk_reg),
        # (a) and the voiced plosives with the adduction of modal: only the tract differs from the vowel
        "a_reg_voiced": dict(speaker=spk_regv),
        # (a) upper bound: no glottal gestures of consonants at all (everything voiced)
        "a_allmodal": dict(edit=edit_xml(all_modal)),
        # (b) the F0 does not move in the sentence (one value per sentence)
        "b_flatf0": dict(edit=edit_xml(flat_f0)),
        # (a) register of modal, LCA/IA/PCA solved for the old glottal opening (invert.py)
        "a_matched": dict(speaker=spk_match),
        "ac_matched_press1": dict(speaker=spk_match, edit=edit_xml(pressure_follows_f0(1.0))),
        # (c) the lung pressure follows the F0
        "c_press1": dict(edit=edit_xml(pressure_follows_f0(1.0))),
        "c_press2": dict(edit=edit_xml(pressure_follows_f0(2.0))),
        # (d) posture speed and the time constant of the glottal gestures
        "d_speed4": dict(static=["s11=4"]),
        "d_speed20": dict(static=["s11=20"]),
        "d_tau5": dict(edit=edit_xml(glottal_tau(.005))),
        "d_tau20": dict(edit=edit_xml(glottal_tau(.020))),
        # candidates: (a) and (c) together
        "ac_register_press1": dict(speaker=spk_reg, edit=edit_xml(pressure_follows_f0(1.0))),
        "ac_reg_voiced_press1": dict(speaker=spk_regv, edit=edit_xml(pressure_follows_f0(1.0))),
        # faster adduction after voiceless consonants
        "e_fastclose": dict(speaker=spk_match, edit=edit_xml(fast_close(.006))),
        "e_fastclose_late": dict(speaker=spk_match, edit=edit_xml(fast_close(.006, .008))),
        "e_fastclose_late15": dict(speaker=spk_match, edit=edit_xml(fast_close(.006, .015))),
        # all three: consonants at the modal register, faster adduction, pressure follows F0
        "ace_all": dict(speaker=spk_match, edit=edit_xml(fast_close(.006, .015), pressure_follows_f0(1.0))),
        # measurement check: no aspiration noise
        "n_quiet": dict(static=["s14=-60"]),
    }


VARIANTS = _variants()
