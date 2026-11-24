"""Listening page v1.1.1 -> v1.1.2, v1.1.2 -> v1.1.3, v1.1.3 -> v1.1.4 (synthesis only).

    listen112.py render v111 ../../speakers/.../v1-1-1.speaker --v111-rules     (library of a86f77e)
    listen112.py render v112 ../../speakers/.../v1-1-2.speaker
    listen112.py page v111 v112      -> results/listen112.html
    listen112.py page v112 v113      -> results/listen113.html    (v112: rendered with the library and accent.py of ed0b60f)
    listen112.py page v113 v114      -> results/listen114.html
"""
import sys

from compare import *
from listen import clip, load

NOTE113 = {"ざ行": "声を弱め，雑音を強めた", "じゃ行": "同上", "ら行": "舌本体を前へ．離しを速く", "ら と だ": "区別がつくか",
           "ば行": "変えていない", "だ行": "変えていない", "が行": "変えていない"}
NOTE114 = dict.fromkeys(("ば行", "だ行", "が行"), "前後の母音の張りを弱めた") | dict.fromkeys(("ざ行", "じゃ行", "ら行"), "変えていない") | {"ら と だ": "区別がつくか", "清濁": "濁りが弱まっていないか"}
WORDS = {"ば行": ("かばん。そば。あぶら。えび。", "閉鎖中の声．閉鎖が長すぎた"), "だ行": ("あだな。まど。でで。からだ。", "同上"),
         "が行": ("かぎ。ごご。あがる。かげ。", "閉鎖しきらない [ɣ] 寄りにした"), "ざ行": ("かざり。みず。かぜ。なぞ。", "離しの後の気息をなくした"),
         "じゃ行": ("まじめ。じじつ。かじゅう。みじょう。", "同上"), "ら行": ("さらら。りりしい。るりいろ。それから。ろうろう。", "横に息を逃がし，閉じきらない"),
         "ら と だ": ("からだ。ただら。はらだ。どろ。れでろ。", "区別がつくか"), "清濁": ("かき、かぎ。また、まだ。あす、あず。しっぱ、しっば。", "区別がつくか")}
RATES = (1.5, 2.0)
MORE = {"x1": "だれかが、ごはんを食べながら、番組を見ていた。", "x2": "海辺で、美人の踊り子が、ぶどうを投げた。",
        "x3": "どこでも、げんきな子どもが、ぐるぐるとばいくで遊ぶ。"}


def render(label, speaker):
    for k, (t, _) in WORDS.items():
        accent.render(t, OUT / f"listen/{label}/{k}", speaker=Path(speaker))
    for u, t in MORE.items():
        accent.render(t, OUT / f"listen/{label}/{u}", speaker=Path(speaker))
    for u, t in SENTENCES.items():
        for r in (1.0,) + RATES:
            accent.render(t, OUT / f"listen/{label}/{u}-{round(r * 100)}", speaker=Path(speaker), rate=r)


def cell(label, name):
    sr, x = load(OUT / f"listen/{label}/{name}.wav")
    return f"<td>{clip([x], sr)}</td>"


def page(old, new):
    ver = lambda l: f"v1.1.{l[-1]}"
    rows = lambda items: "".join(f"<tr><th>{a}<small>{b}</small></th>{cell(old, n)}{cell(new, n)}</tr>" for n, a, b in items)
    head = f"<thead><tr><th></th><th>前（{ver(old)}）</th><th>後（{ver(new)}）</th></tr></thead>"
    tab = lambda items: f'<div class="w"><table>{head}<tbody>{rows(items)}</tbody></table></div>'
    words = tab([(k, k, f"{t}<br>{dict(v113=NOTE113, v114=NOTE114).get(new, {}).get(k, n)}") for k, (t, n) in WORDS.items()])
    sent = "".join(f"<h2>文：{'ふつうの速さ' if r == 1 else f'{r:g} 倍速'}</h2>" + tab([(f"{u}-{round(r * 100)}", t, "") for u, t in SENTENCES.items()]) for r in (1.0,) + RATES)
    more = "<h2>文：濁音の多いもの</h2>" + tab([(k, t, "") for k, t in MORE.items()]) if new == "v114" else ""
    css = """:root{--bg:#fbfaf8;--fg:#24211e;--mut:#6d665f;--line:#ddd7cf}
@media (prefers-color-scheme:dark){:root{--bg:#1c1a18;--fg:#ece7e1;--mut:#a39a91;--line:#3b3733}}
body{background:var(--bg);color:var(--fg);font:15px/1.7 "Hiragino Sans",sans-serif;max-width:960px;margin:0 auto;padding:24px 16px}
h1{font-size:22px}h2{font-size:17px;margin-top:36px}p{max-width:46em}.w{overflow-x:auto}table{border-collapse:collapse;width:100%}
th,td{border-top:1px solid var(--line);padding:8px;text-align:left;vertical-align:middle;font-weight:normal}
thead th{font-weight:600;border-top:0}small{display:block;color:var(--mut)}audio{width:230px;height:34px}"""
    html = f"""<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>嘉音の子音 {ver(old)} → {ver(new)}</title><style>{css}</style></head><body><h1>嘉音の子音 {ver(old)} → {ver(new)}</h1>
<p>すべて VocalTractLab の合成です．音量はそろえてあります．モーダルの声質と母音は変えていません．前は話者 {ver(old)} とその時の規則，後は話者 {ver(new)} と新しい規則です．</p>
<h2>語（有声の破裂・摩擦，ら行）</h2>{words}{more}{sent}</body></html>"""
    (HERE / f"results/listen1{new[2:]}.html").write_text(html)
    print(len(html) // 1024, "KB")


if __name__ == "__main__":
    a = sys.argv[1:]
    if "--v111-rules" in a:
        a.remove("--v111-rules")
        v111_rules()
    render(*a[1:3]) if a[0] == "render" else page(*a[1:3])
