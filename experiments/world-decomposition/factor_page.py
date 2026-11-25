"""Blind listening page for factor.py (local only). Scores stay in the browser; "copy" gives them as text."""
import sys

from blind_page import enc, page, wav
from common import LABEL, OUT, SENTENCES, load_jvs, RS

SPK = ["jvs064", "jvs053", "jvs015"]
UTT = sys.argv[1:] or ["013", "017"]
CONDS = ["rule", "none", "P", "T", "F", "R", "PT", "PF", "TF", "PTF"]
NAME = {"rule": "ルールそのまま（話速・声の高さもルール）", "none": "ルール（話速と声の高さだけ実声に合わせる）", "P": "＋ポーズ", "T": "＋分節の長さ",
        "F": "＋F0", "R": "＋F0の幅だけ", "PT": "＋ポーズ＋分節の長さ", "PF": "＋ポーズ＋F0", "TF": "＋分節の長さ＋F0", "PTF": "全部（写し）"}


blocks = []
for u in UTT:
    for s in SPK:
        src = {c: wav(OUT / (f"audio/vtl/{u}.wav" if c == "rule" else f"factor/{s}-{u}-{c}.wav")) for c in CONDS}
        blocks.append(dict(id=f"{s}-{u}", text=SENTENCES[u], spk=s, real=enc(load_jvs(s, [u])[u], RS), src=src))

page(OUT / "prosody.html", "韻律の組み替え試聴", f"""すべて{LABEL}のVTL音声です。変えてあるのは、ポーズ・分節の長さ・F0を、ルールから取るかJVSの録音から取るかだけです。ブロックごとに順番を混ぜてあります。自然さを5段階で付けてください（1 = 不自然、5 = 自然）。つけなくても構いません。採点はこのブラウザにだけ残ります。実声は参考で、声は違います。""",
     f"prosody-factor-{LABEL}-{'-'.join(UTT)}", blocks, NAME, effects=True)
