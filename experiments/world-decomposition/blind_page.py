"""Blind listening page (local only): shuffled buttons, 1-5 scores kept in the browser, optional factorial tally."""
import base64
import json
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from scipy.io import wavfile

from common import RMS, active_rms

def enc(x, rate):
    x = x * RMS / active_rms(x)
    x = x * min(1, .98 / np.abs(x).max())
    with tempfile.TemporaryDirectory() as d:
        w, o = Path(d) / "a.wav", Path(d) / "a.m4a"
        wavfile.write(w, rate, (x * 32767).astype(np.int16))
        subprocess.run(["afconvert", "-f", "m4af", "-d", "aac", "-b", "160000" if rate > 24000 else "48000", str(w), str(o)], check=True)
        return "data:audio/mp4;base64," + base64.b64encode(o.read_bytes()).decode()


def wav(p):
    rate, x = wavfile.read(p)
    return enc(x / 32768.0, rate)


HTML = """<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>__TITLE__</title>
<style>:root{--bg:#fcfcfb;--fg:#0b0b0b;--mut:#52514e;--line:#e1e0d9;--on:#2a78d6}@media(prefers-color-scheme:dark){:root{--bg:#1a1a19;--fg:#f0efec;--mut:#c3c2b7;--line:#3a3936;--on:#3987e5}}
body{background:var(--bg);color:var(--fg);font:15px/1.6 "Hiragino Sans",sans-serif;max-width:820px;margin:0 auto;padding:24px 16px 80px}h1{font-size:1.35em}h2{margin-top:2.2em;font-size:1.05em}small,.mut{color:var(--mut)}
button{font:inherit;padding:4px 14px;border:1px solid var(--line);border-radius:6px;background:none;color:var(--fg);cursor:pointer}button.on{background:var(--on);color:#fff;border-color:var(--on)}
.row{display:flex;flex-wrap:wrap;gap:6px 14px;align-items:center;border-bottom:1px solid var(--line);padding:6px 0}.row .ans{flex-basis:100%;color:var(--mut);display:none}.show .ans{display:block}
.sc label{margin-right:8px;white-space:nowrap}table{border-collapse:collapse}td,th{border-bottom:1px solid var(--line);padding:4px 10px;text-align:left}.num{text-align:right;font-variant-numeric:tabular-nums}.wrap{overflow-x:auto}.bar{position:sticky;top:0;background:var(--bg);padding:8px 0;border-bottom:1px solid var(--line);display:flex;gap:10px;flex-wrap:wrap}</style>
<h1>__TITLE__</h1>
<p>__INTRO__</p>
<div class="bar"><button id="reveal">答えを表示</button><button id="copy">採点をコピー</button><button id="clear">採点を消す</button><label class="mut"><input type="checkbox" id="cont"> 同じ位置から続ける</label></div>
<div id="blocks"></div><h2>集計</h2><p class="mut">採点した分だけ集計します。答えを表示する前に採点するのがおすすめです。</p><div id="sum" class="wrap"></div>
<script>
const B=__BLOCKS__,NAME=__NAME__;
const KEY='__KEY__',EFF=__EFF__;let st={};try{st=JSON.parse(localStorage.getItem(KEY)||'{}')}catch(e){}
st.seed=st.seed||Math.floor(Math.random()*1e9);st.score=st.score||{};
const save=()=>{try{localStorage.setItem(KEY,JSON.stringify(st))}catch(e){}};
let r=st.seed;const rnd=()=>{r=(r*1664525+1013904223)>>>0;return r/4294967296};
const shuffle=a=>{a=a.slice();for(let i=a.length-1;i>0;i--){const j=Math.floor(rnd()*(i+1));[a[i],a[j]]=[a[j],a[i]]}return a};
let au=null,btn=null;const stop=()=>{if(au){au.pause();btn.classList.remove('on');au=null}};
const play=(x,src)=>{const t=au&&document.getElementById('cont').checked?au.currentTime:0,same=au&&btn===x;stop();if(same)return;au=new Audio(src);btn=x;const me=au;me.onloadedmetadata=()=>{me.currentTime=Math.min(t,me.duration-.05)};me.onended=()=>{x.classList.remove('on')};me.play();x.classList.add('on')};
const el=(t,h,c)=>{const e=document.createElement(t);if(h!=null)e.textContent=h;if(c)e.className=c;return e};
const root=document.getElementById('blocks');
B.forEach(b=>{root.append(el('h2',b.text));const p=el('p');if(b.real){const rb=el('button','参考：実声（'+b.spk+'）');rb.onclick=()=>play(rb,b.real);p.append(rb)}root.append(p);
shuffle(Object.keys(b.src)).forEach((c,i)=>{const row=el('div',null,'row');const x=el('button','▶ '+String.fromCharCode(65+i));x.onclick=()=>play(x,b.src[c]);row.append(x);const sc=el('span',null,'sc');
for(let k=1;k<=5;k++){const l=el('label'),q=document.createElement('input');q.type='radio';q.name=b.id+c;q.checked=(st.score[b.id+'|'+c]===k);q.onchange=()=>{st.score[b.id+'|'+c]=k;save();sum()};l.append(q,' '+k);sc.append(l)}
row.append(sc,el('div',NAME[c],'ans'));root.append(row)})});
function sum(){const by={};Object.entries(st.score).forEach(([k,v])=>{const c=k.split('|')[1];(by[c]=by[c]||[]).push(v)});
const m=a=>a.reduce((x,y)=>x+y,0)/a.length;const t=el('table');const h=el('tr');['条件','平均','件数'].forEach(x=>h.append(el('th',x)));t.append(h);
const show=document.body.classList.contains('show');
if(show)Object.keys(NAME).forEach(c=>{if(by[c]){const r=el('tr');r.append(el('td',NAME[c]),el('td',m(by[c]).toFixed(2),'num'),el('td',by[c].length,'num'));t.append(r)}});
const d=document.getElementById('sum');d.replaceChildren();if(!show){d.append(el('p','答えを表示すると集計が出ます。','mut'));return}
d.append(t);if(!EFF)return;const eff=el('table');const g={};Object.entries(st.score).forEach(([k,v])=>{const[b,c]=k.split('|');(g[b]=g[b]||{})[c]=v});
const h2=el('tr');['要素','実声のものに替えたときの平均の変化','比べた組'].forEach(x=>h2.append(el('th',x)));eff.append(h2);
[['P','ポーズ'],['T','分節の長さ'],['F','F0']].forEach(([f,n])=>{const ds=[];Object.values(g).forEach(s=>['','P','T','F','PT','PF','TF','PTF'].forEach(c=>{if(c.includes(f))return;const a=c||'none',bb=[...'PTF'].filter(z=>c.includes(z)||z===f).join('');if(s[a]!=null&&s[bb]!=null)ds.push(s[bb]-s[a])}));
const r=el('tr');r.append(el('td',n),el('td',ds.length?(m(ds)>=0?'+':'')+m(ds).toFixed(2):'—','num'),el('td',ds.length,'num'));eff.append(r)});d.append(el('p',' '),eff)}
document.getElementById('reveal').onclick=e=>{document.body.classList.toggle('show');e.target.textContent=document.body.classList.contains('show')?'答えを隠す':'答えを表示';sum()};
document.getElementById('clear').onclick=()=>{if(!confirm('採点を消しますか？'))return;st.score={};save();document.querySelectorAll('input[type=radio]').forEach(q=>q.checked=false);sum()};
document.getElementById('copy').onclick=async e=>{const t=JSON.stringify(st.score);try{await navigator.clipboard.writeText(t);e.target.textContent='コピーしました'}catch(x){prompt('コピーしてください',t)}};
save();sum();
</script></html>"""


def page(out, title, intro, key, blocks, names, effects=False):
    """blocks: [{id, text, spk, real (data URI or None), src {condition: data URI}}]."""
    s = (HTML.replace("__TITLE__", title).replace("__INTRO__", intro).replace("__KEY__", key).replace("__EFF__", "true" if effects else "false")
         .replace("__NAME__", json.dumps(names, ensure_ascii=False)).replace("__BLOCKS__", json.dumps(blocks, ensure_ascii=False)))
    Path(out).write_text(s)
    print(len(s) / 1e6, "MB", len(blocks), "blocks")
