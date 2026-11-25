"""Listening page: v1.3.1 and the enlarged tracts (synthesis only).   listen.py -> results/listen.html"""
import multiprocessing
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "consonant-articulation"))
from listen131 import CSS, OUT, SENTENCES, WORDS, Path, accent, clip, load  # noqa: E402

BASE = HERE.parents[1] / "speakers/fulkhisa-kanon/fulkhisa-kanon-v1-3-1.speaker"
COLS = [("v131", "v1.3.1（1 倍）", BASE)] + [(f"k{k}", f"{k} 倍", HERE / f"out/k{k}.speaker") for k in ("1.08", "1.14", "1.2", "1.25")]
SETS = {"母音": ("母音", "あー。いー。うー。えー。おー。あいうえお。", 1.0)} | {f"文{u}": ("文", t, 1.0) for u, t in SENTENCES.items()} | \
    {"早口": ("1.5 倍速", SENTENCES["017"], 1.5)} | {k: (k, t, 1.0) for k, t in WORDS.items()}


def job(a):
    c, spk, n, t, r = a
    accent.render(t, OUT / f"listen/{c}s/{n}", speaker=spk, rate=r)


if __name__ == "__main__":
    with multiprocessing.Pool(8) as pool:
        pool.map(job, [(c, spk, n, t, r) for c, _, spk in COLS for n, (_, t, r) in SETS.items()], chunksize=1)
    rows = ""
    for n, (h, t, r) in SETS.items():
        cells = ""
        for c, _, _ in COLS:
            sr, x = load(OUT / f"listen/{c}s/{n}.wav")
            cells += f"<td>{clip([x], sr)}</td>"
        rows += f"<tr><th>{h}<small>{t}</small></th>{cells}</tr>"
    css = CSS.replace("max-width:960px", "max-width:1400px").replace("width:230px", "width:190px") + "th:first-child{min-width:180px}"
    (HERE / "results/listen.html").write_text(f"""<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>嘉音の声道の大きさ</title><style>{css}</style></head><body><h1>嘉音 v1.3.1 の声道を大きくする</h1>
<p>すべて合成です．音量はそろえてあります．声門，F0，規則は同じ v1.3.1 のもので，声道の大きさだけが違います（長さの倍率．フォルマントはおよそその逆数倍）．</p>
<div class="w"><table><thead><tr><th></th>{"".join(f"<th>{l}</th>" for _, l, _ in COLS)}</tr></thead><tbody>{rows}</tbody></table></div></body></html>""")
