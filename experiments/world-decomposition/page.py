"""Self-contained listening page (local only: it contains JVS audio)."""
import base64
import subprocess
import tempfile
from pathlib import Path

from common import HERE, LABEL, OUT, SENTENCES, VER

PREV = "v1-1-0"                # the version heard next to it

SPK, UTT = ["jvs064", "jvs053", "jvs015"], ["001", "013"]
ROWS = [("original", "元の音", "WORLDを通していない音"), ("none", "WORLDのみ", "分解して戻しただけ。劣化の基準"),
        ("F0", "F0", "声の高さの曲線"), ("AP", "AP", "非周期性（息・雑音の混ざり方）"), ("S", "S", "長時間の平均スペクトル（声の色・声道長・収録系）"),
        ("E", "E", "音量の時間変化"), ("D", "D", "スペクトル形状の動き（調音・フォルマントの動き）"),
        ("F0+AP+E", "F0 + AP + E", "嘉音のスペクトルのまま、韻律と雑音を実声に"), ("F0+AP+E+D", "F0 + AP + E + D", "Sだけ嘉音。残りは実声")]


def enc(p):
    with tempfile.TemporaryDirectory() as d:
        o = Path(d) / "a.flac"
        subprocess.run(["afconvert", "-f", "flac", "-d", "flac", str(p), str(o)], check=True)
        return "data:audio/flac;base64," + base64.b64encode(o.read_bytes()).decode()


def btn(p, label):
    return f'<button data-src="{enc(p)}">{label}</button>' if p.exists() else '<span class="na">—</span>'


h = []
for u in UTT:
    h.append(f"<h2>{u}　{SENTENCES[u]}</h2>")
    rule = lambda v: HERE / f"out/{v}/audio/vtl/{u}.wav"
    h.append(f'<p>ルール韻律（差し替えなし、48 kHz）：{btn(rule(VER), LABEL)} {btn(rule(PREV), PREV.replace("-", "."))}</p>')
    for s in SPK:
        h.append(f'<section><h3>{s}</h3><div class="wrap"><table><tr><th>差し替える部品</th><th>実声が土台<br><small>その部品だけ{LABEL}に</small></th><th>{LABEL}が土台<br><small>その部品だけ実声に</small></th><th>{PREV.replace("-", ".")}が土台<br><small>前の版との比較</small></th></tr>')
        for k, name, note in ROWS:
            c = [btn(HERE / f"out/{v}/swap/{s}-{u}-{b}-{k}.wav", "▶ 再生") for v, b in ((VER, "R"), (VER, "V"), (PREV, "V"))]
            h.append(f"<tr><td><b>{name}</b><small>{note}</small></td><td>{c[0]}</td><td>{c[1]}</td><td>{c[2]}</td></tr>")
        h.append("</table></div></section>")
(OUT / "listen.html").write_text("""<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>WORLD部品の差し替え試聴</title>
<style>:root{--bg:#fcfcfb;--fg:#0b0b0b;--mut:#52514e;--line:#e1e0d9;--on:#2a78d6}@media(prefers-color-scheme:dark){:root{--bg:#1a1a19;--fg:#f0efec;--mut:#c3c2b7;--line:#3a3936;--on:#3987e5}}
body{background:var(--bg);color:var(--fg);font:15px/1.6 "Hiragino Sans",sans-serif;max-width:860px;margin:0 auto;padding:24px 16px 80px}h2{margin-top:2.2em;font-size:1.1em}h3{margin-bottom:.3em}
table{border-collapse:collapse;width:100%}td,th{border-bottom:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:middle}td small,th small{display:block;color:var(--mut);font-weight:400}.wrap{overflow-x:auto}
button{font:inherit;padding:4px 14px;border:1px solid var(--line);border-radius:6px;background:none;color:var(--fg);cursor:pointer}button.on{background:var(--on);color:#fff;border-color:var(--on)}.na{color:var(--mut)}.bar{position:sticky;top:0;background:var(--bg);padding:8px 0;border-bottom:1px solid var(--line)}</style>
<h1>WORLD部品の差し替え試聴</h1><p>実声（JVS）と、同じ時間構造・F0で合成した嘉音をWORLDで分解し、部品を1つずつ入れ替えた音です。帯域は8 kHzまで。「元の音」と「WORLDのみ」の差がWORLD自体の劣化です。</p>
<div class="bar"><label><input type="checkbox" id="cont"> 別の音を押したとき、同じ位置から続ける</label> <button id="stop">停止</button></div>
""" + "\n".join(h) + """<script>let a=null,b=null;const stop=()=>{if(a){a.pause();b.classList.remove('on');a=null}};document.getElementById('stop').onclick=stop;
document.querySelectorAll('button[data-src]').forEach(x=>x.onclick=()=>{const t=a&&document.getElementById('cont').checked?a.currentTime:0;const same=a&&b===x;stop();if(same)return;a=new Audio(x.dataset.src);b=x;const me=a;a.onloadedmetadata=()=>{me.currentTime=Math.min(t,me.duration-.05)};a.onended=()=>x.classList.remove('on');a.play();x.classList.add('on')})</script></html>""")
