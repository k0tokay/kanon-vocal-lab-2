"""Same pitch range for every F0 predictor: only where the F0 goes differs (pyopenjtalk-plus env).

    KANON=v1-1-3 VTL_LIB=... python prosody_range.py render texts.json out/prosody-jvs.pkl predictions-dir
    KANON=v1-1-3 python prosody_range.py page texts.json
All conditions keep the rule timing and 218 Hz mean. Except `raw`, the vowel-centre F0 of each sentence is scaled
to the SD of the JVS mean contour of that sentence.
"""
import json
import os
import pickle
import sys
from pathlib import Path

NAME = {"raw": "いまの規則（振れ幅もそのまま）", "rule": "いまの規則", "fit": "規則の数値だけJVSに合わせたもの", "stat": "アクセントからの学習モデル（JVSの別の50文で学習）", "jvsF": "JVS女性51名の平均"}
OUT = Path(__file__).resolve().parent / "out" / os.environ.get("KANON", "v1-1-3")
if sys.argv[1] == "render":
    import contextlib, io                                      # noqa: E401
    import numpy as np
    from prosody_render import accent, build, reference
    OD = OUT / "prosody-range"; OD.mkdir(parents=True, exist_ok=True)
    T = json.load(open(sys.argv[2])); R = reference(pickle.load(open(sys.argv[3], "rb"))); pd = Path(sys.argv[4])
    S, q = json.load(open(pd / "pred-stat.json")), json.load(open(pd / "fit.json"))
    for u in json.load(open(OUT / "prosody" / "utts.json")):
        ref = dict(f0=[float(y) if ok else None for y, ok in zip(R[u]["mean"], R[u]["ok"])]); pred = dict(f0=[x[2] for x in S[u]])
        sd = float(np.std([y for y in ref["f0"] if y is not None]))
        for c in NAME:
            segs = build(T[u]["text"], "rule" if c == "raw" else c, pred, ref, q, u, None if c == "raw" else sd)
            seg = OD / f"{u}-{c}.seg"; accent.write_seg(segs, seg)
            with contextlib.redirect_stdout(io.StringIO()):
                accent.synthesize(seg, seg.with_suffix(".wav"), segs)
        print(u, round(sd, 2), flush=True)
else:
    from blind_page import page, wav
    from common import LABEL
    OD = OUT / "prosody-range"; T = json.load(open(sys.argv[2]))
    blocks = [dict(id=u, text=T[u]["text"], spk="", real=None, src={c: wav(OD / f"{u}-{c}.wav") for c in NAME}) for u in json.load(open(OUT / "prosody" / "utts.json"))]
    page(OUT / "prosody-range.html", "F0の振れ幅をそろえた比較", f"すべて{LABEL}のVTL音声で、音の長さとポーズは同じ規則です。声の高さの平均も218 Hzにそろえ、文ごとのF0の振れ幅（標準偏差）もJVS平均に合わせました（5つのうち1つだけは、いまの規則の振れ幅のままです）。違いはF0の動かし方だけです。順番は文ごとに混ぜてあります。自然さを5段階で付けてください（1 = 不自然、5 = 自然）。採点はこのブラウザにだけ残ります。",
         f"prosody-range-{LABEL}", blocks, NAME)
