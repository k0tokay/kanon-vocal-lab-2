"""Listening page v1.3.0 -> v1.3.1, with v1.1.4 for reference (synthesis only).

    listen131.py      -> results/listen131.html

v1.3.0 is rendered with the rules before the consonant work (compare.old_rules: no timing labels).
"""
from compare import *
from build131 import V114, V130, V131
from listen import clip, load
from listen112 import MORE
from listen112 import WORDS as VOICED
from listen_t import CSS

WORDS = {k: t for k, (t, _) in VOICED.items()} | {
    "さ行": "さき。すな。あせ。そら。", "しゃ行": "しま。あした。しゃしん。", "ち・つ": "まち。つき。いちつ。ちち。", "は行": "はは。ふね。ひと。ほん。",
    "た行": "あた。また。かたな。わたし。たたく。", "て・と": "あて。みて。てがみ。おと。こと。ととのう。", "か行": "かき。こけ。くき。あか。"}
SETS = {k: (k, t, 1.0) for k, t in WORDS.items()} | {
    f"{u}-{round(100 * r)}": (f"{r:g} 倍速" if r != 1 else "ふつうの速さ", t, r) for r in (1.0, 1.5) for u, t in (SENTENCES | MORE).items()}
COLS = [("v131", "v1.3.1（今回）", V131), ("v114", "v1.1.4（2025 声門）", V114), ("v130old", "v1.3.0（前の規則）", V130)]

if __name__ == "__main__":
    for c, _, spk in COLS:
        if c == "v130old":
            old_rules()
        for n, (_, t, r) in SETS.items():
            accent.render(t, OUT / f"listen/{c}x/{n}", speaker=spk, rate=r)
    order = [COLS[2], COLS[0], COLS[1]]
    rows = ""
    for n, (h, t, r) in SETS.items():
        cells = ""
        for c, _, _ in order:
            sr, x = load(OUT / f"listen/{c}x/{n}.wav")
            cells += f"<td>{clip([x], sr)}</td>"
        rows += f"<tr><th>{h}<small>{t}</small></th>{cells}</tr>"
    html = f"""<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>嘉音 v1.3.1</title><style>{CSS}</style></head><body><h1>嘉音 v1.3.0 → v1.3.1</h1>
<p>すべて合成です．音量はそろえてあります．v1.3.1 は，v1.3.0 の声門（TBCM）に v1.1.4 の声道と子音の規則を入れたものです．TBCM の声門の形は変えていません．v1.1.4 は声門が違う（Geometric 2025）ので，子音だけを聞き比べてください．</p>
<div class="w"><table><thead><tr><th></th>{"".join(f"<th>{l}</th>" for _, l, _ in order)}</tr></thead><tbody>{rows}</tbody></table></div></body></html>"""
    (HERE / "results/listen131.html").write_text(html)
    print(len(html) // 1024, "KB", html.count("<audio"), "clips")
