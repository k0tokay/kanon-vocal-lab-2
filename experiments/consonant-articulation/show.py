"""Side-by-side table of saved comparisons: show.py v110 v111 ... (results/compare-<label>.json).

Only measures where some version is at least 1.5 JVS SDs away are printed (--all for every one).
"""
import json
import sys

from pathlib import Path

HERE = Path(__file__).resolve().parent
args = [a for a in sys.argv[1:] if not a.startswith("-")]
res = {l: json.loads((HERE / f"results/compare-{l}.json").read_text()) for l in args}
first = res[args[0]]
for c in first:
    print("==", c)
    for k, q in first[c].items():
        z = [res[l][c].get(k, {}).get("z", 0) for l in args]
        if "--all" not in sys.argv and max(map(abs, z)) < 1.5 or k in ("nb_0.08k", "nb_0.5k", "peak_hi", "dip_full"):
            continue
        print(f"  {k:12s} JVS {q['jvs']:7.1f} | " + " | ".join(
            f"{l} {res[l][c][k]['syn']:7.1f} ({res[l][c][k]['z']:+4.1f})" if k in res[l][c] else f"{l}    -" for l in args))
common = [(c, k) for c in first for k in first[c] if all(k in res[l][c] for l in args)]
t = {l: [abs(res[l][c][k]["z"]) for c, k in common] for l in args}
print(f"{len(common)} common measures, mean |z|:", {l: round(sum(v) / len(v), 2) for l, v in t.items()},
      " share |z|>2:", {l: round(sum(x > 2 for x in v) / len(v), 2) for l, v in t.items()})
