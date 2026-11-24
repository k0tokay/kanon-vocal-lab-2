"""Listening page for the rule of /t/ (v1.1.4): glottis_end_s -25 ms (before) -> -40 ms.

    listen_t.py <speaker>      -> results/listen114t.html     (synthesis only)
"""
import sys

from compare import *
from listen import clip, load

WORDS = {"た行": "あた。また。かたな。わたし。たたく。", "て・と": "あて。みて。てがみ。おと。こと。ととのう。", "清濁": "また、まだ。いと、いど。はて、はで。あた、あだ。",
         "t と k": "かた、たか。とき、こと。たこ、かど。", "促音": "まって。かった。おっと。ちょっと。", "ち・つ（変えていない）": "まち。つき。いちつ。ちち。"}
SETS = {k: (k, t, 1.0) for k, t in WORDS.items()} | {
    f"{u}-{round(100 * r)}": (f"{r:g} 倍速" if r != 1 else "ふつうの速さ", t, r) for r in (1.0, 1.5) for u, t in SENTENCES.items()}
NEW = dict(accent.TIMING["t"])
CSS = """:root{--bg:#fbfaf8;--fg:#24211e;--mut:#6d665f;--line:#ddd7cf}
@media (prefers-color-scheme:dark){:root{--bg:#1c1a18;--fg:#ece7e1;--mut:#a39a91;--line:#3b3733}}
body{background:var(--bg);color:var(--fg);font:15px/1.7 "Hiragino Sans",sans-serif;max-width:960px;margin:0 auto;padding:24px 16px}
h1{font-size:22px}.w{overflow-x:auto}table{border-collapse:collapse;width:100%}
th,td{border-top:1px solid var(--line);padding:8px;text-align:left;vertical-align:middle;font-weight:normal}
thead th{font-weight:600;border-top:0}small{display:block;color:var(--mut)}audio{width:230px;height:34px}"""

if __name__ == "__main__":
    rows = ""
    for n, (h, t, r) in SETS.items():
        cells = ""
        for tag, d in (("before", {}), ("after", NEW)):
            accent.TIMING["t"] = d
            stem = OUT / f"listen/t-{tag}/{n}"
            accent.render(t, stem, speaker=Path(sys.argv[1]), rate=r)
            sr, x = load(stem.with_suffix(".wav"))
            cells += f"<td>{clip([x], sr)}</td>"
        rows += f"<tr><th>{h}<small>{t}</small></th>{cells}</tr>"
    html = f"""<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>嘉音の t</title><style>{CSS}</style></head><body><h1>嘉音 v1.1.4 の t</h1>
<p>すべて合成です．音量はそろえてあります．話者は同じ v1.1.4 で，t の声門を閉じ始める時刻だけが違います（離しの 25 ms 前 → 40 ms 前）．</p>
<div class="w"><table><thead><tr><th></th><th>前</th><th>後</th></tr></thead><tbody>{rows}</tbody></table></div></body></html>"""
    (HERE / "results/listen114t.html").write_text(html)
    print(len(html) // 1024, "KB", html.count("<audio"), "clips")
