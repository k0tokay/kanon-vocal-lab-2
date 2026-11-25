"""Predictions for prosody_eval.py: rules of accent.py (under either OpenJTalk build), or VOICEVOX.

    python prosody_pred.py rule   texts.json pred-x.json [ap_first,ap_next,aa,alpha,beta,lead]
    python prosody_pred.py kana   texts.json kana.json          (accent phrases of this OpenJTalk in VOICEVOX kana)
    python prosody_pred.py vv     texts.json pred-x.json <voicevox_core dir> <vvm> <style id> [kana.json]
Mora F0 of the rules is the value at 65 % of the mora (about the vowel centre); VOICEVOX pitch is log Hz per mora.
"""
import json
import math
import os
import sys
from pathlib import Path

import numpy as np


def rule(texts, par):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "japanese-accent"))
    os.environ.setdefault("VTL_SPEAKER", "x")
    import accent
    p = accent.Fujisaki(**dict(zip(("ap_first", "ap_next", "aa", "alpha", "beta", "lead"), par))) if par else accent.Fujisaki()
    out = {}
    for u, v in texts.items():
        units = accent.parse(v["text"]); segs, spans = accent.to_segments(units); ph, ac = accent.commands(units, spans, p)
        rows = []
        for m, (a, b) in zip(units, spans):
            if isinstance(m, accent.Pause):
                if rows: rows[-1][4] = b - a
                continue
            f = accent.f0_curve(np.array([a + .65 * (b - a)]), ph, ac, p)[0]
            rows.append([m.consonant, m.vowel, None if m.vowel in "AIUEO" or m.vowel == "cl" else 12 * math.log2(f / 100), b - a, 0.0])
        out[u] = rows
    return out


ROWS = {"": "アイウエオ", "k": "カキクケコ", "g": "ガギグゲゴ", "s": "サスィスセソ", "z": "ザズィズゼゾ", "t": "タティトゥテト", "d": "ダディドゥデド",
        "n": "ナニヌネノ", "h": "ハヒフヘホ", "b": "バビブベボ", "p": "パピプペポ", "m": "マミムメモ", "r": "ラリルレロ"}
FULL = {"sa": "サ", "si": "スィ", "su": "ス", "se": "セ", "so": "ソ", "za": "ザ", "zi": "ズィ", "zu": "ズ", "ze": "ゼ", "zo": "ゾ", "ta": "タ", "ti": "ティ",
        "tu": "トゥ", "te": "テ", "to": "ト", "da": "ダ", "di": "ディ", "du": "ドゥ", "de": "デ", "do": "ド", "ya": "ヤ", "yu": "ユ", "yo": "ヨ", "ye": "イェ",
        "wa": "ワ", "wi": "ウィ", "we": "ウェ", "wo": "ウォ", "fa": "ファ", "fi": "フィ", "fu": "フ", "fe": "フェ", "fo": "フォ", "tsa": "ツァ", "tsi": "ツィ", "tsu": "ツ",
        "tse": "ツェ", "tso": "ツォ", "va": "ヴァ", "vi": "ヴィ", "vu": "ヴ", "ve": "ヴェ", "vo": "ヴォ", "shi": "シ", "chi": "チ", "ji": "ジ"}
for c, row in ROWS.items():
    if c not in "szt d".split() and len(row) == 5:
        FULL.update({c + v: k for v, k in zip("aiueo", row)})
for c, k in {"kw": "ク", "gw": "グ"}.items():
    for v, y in zip("aieo", "ァィェォ"):
        FULL[c + v] = k + y
FULL["kwi"] = "キ"          # not in VOICEVOX's kana table; one mora kept
for c, k in {"ky": "キ", "gy": "ギ", "sh": "シ", "j": "ジ", "ch": "チ", "ny": "ニ", "hy": "ヒ", "by": "ビ", "py": "ピ", "my": "ミ", "ry": "リ", "dy": "デ", "ty": "テ"}.items():
    for v, y in zip("auoe", "ャュョェ"):
        FULL.setdefault(c + v, k + y)


def kana(texts):
    """AquesTalk-like notation: phrases by /, pauses by 、, ' after the nucleus (at the end for heiban)."""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "japanese-accent"))
    os.environ.setdefault("VTL_SPEAKER", "x")
    import accent
    out = {}
    for u, t in texts.items():
        s, cur, pid = "", [], None
        def close():
            nonlocal s, cur
            if not cur: return
            n = cur[0].accent_type or len(cur)
            for i, m in enumerate(cur, 1):
                k = {"cl": "ッ", "N": "ン"}.get(m.vowel) or FULL[m.consonant + m.vowel.lower()]
                s += ("_" if m.vowel in "IU" else "") + k + ("'" if i == min(n, len(cur)) else "")
            cur = []
        for m in accent.parse(t["text"]):
            if isinstance(m, accent.Pause):
                close(); s = s.rstrip("/") + ("、" if m.kind == "pau" else ""); pid = None; continue
            if pid is not None and m.phrase_id != pid:
                close(); s += "/"
            cur.append(m); pid = m.phrase_id
        close(); out[u] = s.rstrip("、/")
    return out


def voicevox(texts, root, vvm, style, kanas=None):
    from voicevox_core.blocking import Onnxruntime, OpenJtalk, Synthesizer, VoiceModelFile
    ort = Onnxruntime.load_once(filename=str(next(Path(root).rglob("libvoicevox_onnxruntime*.dylib"))))
    jt = OpenJtalk(str(next(Path(root).rglob("sys.dic")).parent))
    syn = Synthesizer(ort, jt, acceleration_mode="CPU")
    with VoiceModelFile.open(vvm) as m:
        syn.load_voice_model(m)
    out, info = {}, {}
    for u, v in texts.items():
        q = syn.create_audio_query_from_kana(kanas[u], style) if kanas else syn.create_audio_query(v["text"], style); rows = []
        for ap in q.accent_phrases:
            for m in ap.moras:
                d = (m.consonant_length or 0) + m.vowel_length
                rows.append([m.consonant or "", m.vowel, 12 * m.pitch / math.log(2) if m.pitch > 0 and m.vowel in "aiueoN" else None, d, 0.0])
                rows[-1] += [m.consonant_length or 0.0, m.vowel_length]
            if ap.pause_mora:
                p = ap.pause_mora
                rows[-1][4] = p["vowel_length"] if isinstance(p, dict) else p.vowel_length
        out[u] = rows
    return out


if __name__ == "__main__":
    texts = json.load(open(sys.argv[2]))
    if sys.argv[1] == "rule":
        r = rule(texts, [float(x) for x in sys.argv[4].split(",")] if len(sys.argv) > 4 else None)
    elif sys.argv[1] == "kana":
        r = kana(texts)
    else:
        r = voicevox(texts, *sys.argv[4:6], int(sys.argv[6]), json.load(open(sys.argv[7])) if len(sys.argv) > 7 else None)
    json.dump(r, open(sys.argv[3], "w"), ensure_ascii=False)
