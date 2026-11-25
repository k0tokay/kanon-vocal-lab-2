"""Blind page for prosody_render.py."""
import json
import sys
from pathlib import Path

from blind_page import page, wav
from common import LABEL, OUT

OD = OUT / "prosody"
TEXT = json.load(open(sys.argv[1]))
NAME = {"rule": "いまのルール（pyopenjtalk、平板の不具合は修正済み）", "fit": "F0だけ：pyopenjtalk-plus ＋ JVSに合わせた規則の数値", "vvF": "F0だけ：VOICEVOX 四国めたん（plusのアクセント）",
        "vv": "F0・長さ・ポーズ：VOICEVOX 四国めたん（plusのアクセント）", "jvs": "F0・長さ・ポーズ：JVS女性51名の平均（目安の上限）"}
blocks = [dict(id=u, text=TEXT[u]["text"], spk="", real=None, src={c: wav(OD / f"{u}-{c}.wav") for c in NAME}) for u in json.load(open(OD / "utts.json"))]
page(OUT / "prosody-models.html", "韻律モデルの比較", f"すべて{LABEL}のVTL音声で、声の高さの平均（218 Hz）もそろえてあります。変えたのは韻律の出どころだけです。文ごとに順番を混ぜてあります。自然さを5段階で付けてください（1 = 不自然、5 = 自然）。採点はこのブラウザにだけ残ります。",
     f"prosody-models-{LABEL}", blocks, NAME)
