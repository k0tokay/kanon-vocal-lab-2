"""Listening page: v1.1.0 with the old rules, v1.1.0 with the new rules, v1.1.1 with the new rules.

    listen.py      -> results/listen.html (audio embedded, AAC; synthesis only, no recordings)

Needs out/sent/{v110,rules,v111} (compare.py) and out/{base,new} (ctune.py run, see README).
Every clip is brought to the same RMS over its loud part.
"""
import base64
import subprocess
import tempfile

from compare import *

ROWS = {"か行": "ka ki ku ke ko", "が行": "ga gi gu ge go", "た・て・と": "ta te to", "だ・で・ど": "da de do",
        "ぱ行": "pa pi pu pe po", "ば行": "ba bi bu be bo", "さ・す・せ・そ": "sa su se so", "ざ・ず・ぜ・ぞ": "za zu ze zo",
        "しゃ・し・しゅ・しょ": "sha shi shu sho", "ちゃ・ち・ちゅ・ちょ": "cha chi chu cho", "じゃ・じ・じゅ・じょ": "ja ji ju jo",
        "つ": "tsu", "は行": "ha hi fu he ho", "ひゃ・ひゅ・ひょ": "hya hyu hyo", "ふぁ行": "fa fi fu fe fo",
        "ま行": "ma mi mu me mo", "な行": "na ni nu ne no", "ら行": "ra ri ru re ro", "や・ゆ・よ・わ": "ya yu yo wa"}
NOTE = {"か行": "閉鎖が短く破裂が弱い．「き」は離した後も狭い", "が行": "「か」とほぼ同じ音．閉鎖中の声がない", "た・て・と": "歯の隙間が閉じたまま離れ，破裂が弱い",
        "だ・で・ど": "閉鎖中の声がない", "ぱ行": "破裂が弱い", "ば行": "閉鎖中の声がない", "さ・す・せ・そ": "狭めが浅く，3–5 kHz に寄る",
        "ざ・ず・ぜ・ぞ": "狭めに届かない", "しゃ・し・しゅ・しょ": "狭めがない．「しゅ」は閉鎖して「ちゅ」のよう", "ちゃ・ち・ちゅ・ちょ": "低いところの雑音になる",
        "じゃ・じ・じゅ・じょ": "同上．文中では閉鎖なしの [ʑ] に変えた（ここは語中なので新しい版も閉鎖つき）", "つ": "短い",
        "は行": "「ひ」が舌ではなく前歯で狭まる", "ひゃ・ひゅ・ひょ": "同上", "ふぁ行": "「ふぃ」の唇が閉じる", "ま行": "鼻音の響きが弱い", "な行": "鼻音の響きが弱い",
        "ら行": "未解決（接触が深すぎる）", "や・ゆ・よ・わ": "短い"}


def rms(x, sr):
    n = int(.02 * sr)
    e = np.array([np.mean(x[i:i + n] ** 2) for i in range(0, len(x) - n, n)])
    return np.sqrt(e[e > e.max() * .01].mean())


def clip(xs, sr):
    """Concatenate at equal RMS and return an <audio> element."""
    x = np.concatenate([x / rms(x, sr) for x in xs])
    x = x / rms(x, sr) * .09
    x = np.clip(x, -.98, .98)
    with tempfile.TemporaryDirectory() as d:
        wavfile.write(f"{d}/a.wav", sr, (x * 32767).astype(np.int16))
        subprocess.run(["afconvert", "-f", "m4af", "-d", "aac", "-b", "64000", f"{d}/a.wav", f"{d}/a.m4a"], check=True)
        b = base64.b64encode(open(f"{d}/a.m4a", "rb").read()).decode()
    return f'<audio controls preload="none" src="data:audio/mp4;base64,{b}"></audio>'


def load(p):
    sr, x = wavfile.read(p)
    return sr, x / 32768.0


def main():
    h = []
    for u, text in SENTENCES.items():
        cells = []
        for l in ("v110", "rules", "v111"):
            sr, x = load(OUT / f"sent/{l}/{u}.wav")
            cells.append(clip([x], sr))
        h.append(f"<tr><th>{text}</th>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>")
    g = []
    for name, syl in ROWS.items():
        cells = []
        for k in ("base", "new"):
            xs = []
            for s in syl.split():
                sr, x = load(OUT / f"{k}/{s}.wav")
                xs.append(x)
            cells.append(clip(xs, sr))
        g.append(f"<tr><th>{name}<small>{NOTE[name]}</small></th>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>")
    page = f"""<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>嘉音の子音 前後比較</title><style>
:root{{--bg:#fbfaf8;--fg:#24211e;--mut:#6d665f;--line:#ddd7cf}}
@media (prefers-color-scheme:dark){{:root{{--bg:#1c1a18;--fg:#ece7e1;--mut:#a39a91;--line:#3b3733}}}}
body{{background:var(--bg);color:var(--fg);font:15px/1.7 "Hiragino Sans",sans-serif;max-width:1080px;margin:0 auto;padding:24px 16px}}
h1{{font-size:22px}}h2{{font-size:17px;margin-top:36px}}p{{max-width:46em}}
.w{{overflow-x:auto}}table{{border-collapse:collapse;width:100%}}th,td{{border-top:1px solid var(--line);padding:8px;text-align:left;vertical-align:middle;font-weight:normal}}
thead th{{font-weight:600;border-top:0}}small{{display:block;color:var(--mut)}}audio{{width:230px;height:34px}}</style></head><body>
<h1>嘉音 v1.1.0 → v1.1.1 子音の前後比較</h1>
<p>すべて VocalTractLab の合成です．音量はそろえてあります．モーダルの声質，母音は変えていません．
「規則だけ」は話者 v1.1.0 のまま，長さ・破裂の時間・鼻音の規則を新しくしたものです．</p>
<h2>文</h2><div class="w"><table><thead><tr><th></th><th>前（v1.1.0）</th><th>規則だけ</th><th>後（v1.1.1）</th></tr></thead><tbody>{''.join(h)}</tbody></table></div>
<h2>音節（「あ＋音節」を続けたもの）</h2><p>小さい字は v1.1.0 で測って見つけた失敗です．耳での印象と合うか，合わない行があれば教えてください．</p>
<div class="w"><table><thead><tr><th></th><th>前（v1.1.0）</th><th>後（v1.1.1）</th></tr></thead><tbody>{''.join(g)}</tbody></table></div>
</body></html>"""
    (HERE / "results/listen.html").write_text(page)
    print(len(page) // 1024, "KB")


if __name__ == "__main__":
    main()
