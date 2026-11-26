"""Listening page: steady vowels and sentences, before and after each change.

    ./run.sh listen.py      -> results/listen.html (audio embedded, AAC; synthesis only)

Needs the logs of diag.py (base and the candidates) and sweep.py (base, c_press1).
Sentences are brought to the same RMS over their loud part. A row of steady vowels at
several F0 is normalized as a whole, so that the level differences between the F0 stay.
"""
import base64, subprocess, tempfile
from pathlib import Path
import numpy as np
from scipy.io import wavfile
import diag

HERE = Path(__file__).resolve().parent
OUT = HERE / "results"
B = diag.OUT

SENT = [("base", "v1.4.1 そのまま"),
        ("a_matched", "(a) 子音の声門形状を modal の声区(TA・CT)にし，開きは元の形状に合わせる"),
        ("e_fastclose_late15", "(a)＋(e) 無声子音の後，開きを 15 ms 長く保ってから速く閉じる(時定数 10 → 6 ms)"),
        ("c_press1", "(c) 肺圧を F0 に比例させる(声門形状はそのまま)"),
        ("ace_all", "(a)＋(e)＋(c)"),
        ("a_register", "参考：TA・CT だけ modal にしたもの(開きが半分になり VOT が縮む)")]
STEADY_F0 = [165, 205, 255, 310]


def rms(x, sr=diag.FS):
    n = int(.02 * sr)
    e = np.array([np.mean(x[i:i + n] ** 2) for i in range(0, len(x) - n, n)])
    return np.sqrt(e[e > e.max() * .01].mean())


def audio(x, sr=diag.FS):
    x = np.clip(x / rms(x) * .09, -.98, .98)
    with tempfile.TemporaryDirectory() as d:
        wavfile.write(f"{d}/a.wav", sr, (x * 32767).astype(np.int16))
        subprocess.run(["afconvert", "-f", "m4af", "-d", "aac", "-b", "64000", f"{d}/a.wav", f"{d}/a.m4a"], check=True)
        b = base64.b64encode(open(f"{d}/a.m4a", "rb").read()).decode()
    return f'<audio controls preload="none" src="data:audio/mp4;base64,{b}"></audio>'


def log_audio(path):
    return diag.load(path)["audio"]


def steady_row(variant, vowel):
    xs = [log_audio(B / f"sweep-{variant}" / f"steady-{vowel}-{f}.f32") for f in STEADY_F0]
    gap = np.zeros(int(.15 * diag.FS))
    return audio(np.concatenate([np.concatenate([x, gap]) for x in xs]))


CSS = """:root{--bg:#fbfaf8;--fg:#24211e;--mut:#6d665f;--line:#ddd7cf}
@media (prefers-color-scheme:dark){:root{--bg:#1c1a18;--fg:#ece7e1;--mut:#a39a91;--line:#3b3733}}
body{background:var(--bg);color:var(--fg);font:15px/1.7 "Hiragino Sans",sans-serif;max-width:960px;margin:0 auto;padding:24px 16px}
h1{font-size:22px}h2{font-size:17px;margin-top:32px}.w{overflow-x:auto}table{border-collapse:collapse;width:100%}
th,td{border-top:1px solid var(--line);padding:8px;text-align:left;vertical-align:middle;font-weight:normal}
thead th{font-weight:600;border-top:0}small{display:block;color:var(--mut)}audio{width:230px;height:34px}"""


def main():
    OUT.mkdir(exist_ok=True)
    h = [f'<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
         f'<title>TBCM の制御</title><style>{CSS}</style></head><body><h1>嘉音 TBCM の制御：定常と文</h1>'
         '<p>すべて合成です．話者は v1.4.1(TBCM)．文は音量をそろえてあります．採否は聴いて決めてください(ここでは候補を並べただけです)．</p>']
    h.append('<h2>定常の母音，F0 を変える(165 → 205 → 255 → 310 Hz)</h2>'
             '<p>4 つの高さを続けて鳴らし，全体で音量をそろえました．F0 ごとの音量差はそのまま残っています．'
             '「そのまま」は圧が一定(8000 dPa)なので，高い音ほど弱く細くなります．(c) は圧を F0 に比例させたもの(165 Hz で 6000，310 Hz で 11300 dPa)．'
             '子音の形状を変える (a) は定常母音には効かないので省きました．</p>')
    h.append('<div class="w"><table><thead><tr><th></th><th>そのまま</th><th>(c) 圧を F0 に比例</th></tr></thead><tbody>')
    for v in ("a", "i", "o"):
        h.append(f"<tr><th>/{v}/</th><td>{steady_row('base', v)}</td><td>{steady_row('c_press1', v)}</td></tr>")
    h.append("</tbody></table></div>")
    h.append('<h2>文</h2><div class="w"><table><thead><tr><th></th>' +
             "".join(f"<th>{t}</th>" for t in diag.SENTENCES.values()) + "</tr></thead><tbody>")
    for v, label in SENT:
        cells = [audio(log_audio(B / v / f"{k}.f32")) for k in diag.SENTENCES]
        h.append(f"<tr><th>{label}<small>{v}</small></th>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>")
    h.append("</tbody></table></div>")
    h.append('<p><small>作り方は experiments/tbcm-control/README.md．</small></p></body></html>')
    (OUT / "listen.html").write_text("\n".join(h))


if __name__ == "__main__":
    main()
