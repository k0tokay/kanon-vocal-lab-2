"""Sentences outside the corpus with the rule F0 and the learned F0 (same timing).   python prosody_free.py model.pkl outdir | page outdir"""
import json, sys                                     # noqa: E401
from pathlib import Path

S = [("hashi1", "箸がある。"), ("hashi2", "橋がある。"), ("hashi3", "端がある。"), ("amekasa", "雨が降っていますが、私は傘を持っていません。"), ("tenki", "今日はいい天気ですね。"),
     ("q", "明日、一緒に映画を見に行きませんか。"), ("koohii", "コーヒーを飲みながら、本を読むのが好きです。"), ("sumimasen", "すみません、この電車は新宿に止まりますか。"),
     ("nagai", "昨日の夜遅くまで友達と話していたので、今朝は起きるのがとてもつらかったです。"), ("novel", "少女は黙って窓の外を見ていた。遠くで、鐘が鳴っている。"), ("hai", "はい。"), ("kanon", "私の名前は嘉音です。よろしくお願いします。")]
NAME = {"rule": "いまの規則（藤崎モデル）", "learn": "学習したF0"}
if sys.argv[1] != "page":
    import contextlib, io                            # noqa: E401
    import numpy as np
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "japanese-accent"))
    import accent
    import accent_f0
    M, od = accent_f0.load(sys.argv[1]), Path(sys.argv[2])
    for n, t in S:
        for c in NAME:
            with contextlib.redirect_stdout(io.StringIO()):
                r = accent.render(t, od / f"{n}-{c}", f0_model=M if c == "learn" else None)
            a = [(m.consonant + m.vowel, s) for m, s in zip(r["units"], r["spans"]) if isinstance(m, accent.Mora)]
            f = np.interp([(s[0] + s[1]) / 2 for _, s in a], r["t"], r["f0"])
            print(n, c, " ".join(f"{k}{round(v)}" for (k, _), v in zip(a, f)), "| sd", round(float(np.std(12 * np.log2(f))), 2))
else:
    from blind_page import page, wav
    from common import LABEL
    od = Path(sys.argv[2])
    blocks = [dict(id=n, text=t, spk="", real=None, src={c: wav(od / f"{n}-{c}.wav") for c in NAME}) for n, t in S]
    page(od.parent / "prosody-free.html", "学習F0の自由文テスト", f"{LABEL}。コーパスにない話し言葉の文です。音の長さとポーズは同じ規則で、違うのはF0だけです（平均は同じではありません：規則はそのまま、学習は218 Hz）。自然さを5段階で付けてください。採点はこのブラウザにだけ残ります。", f"prosody-free-{LABEL}", blocks, NAME)
