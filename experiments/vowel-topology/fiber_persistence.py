"""H0 persistence on native VTL /a/ path samples. Run with NumPy and SciPy."""
import csv
from pathlib import Path
from xml.etree import ElementTree

import numpy as np
from scipy.cluster.hierarchy import linkage

root = Path(__file__).resolve().parents[2]
results = Path(__file__).resolve().parent / "results"
out = results / "fiber-persistence"
out.mkdir(exist_ok=True)
speaker = root / "speakers/fulkhisa-kanon/fulkhisa-kanon-v0-8-vowel-variation.speaker"
params = {p.get("name"): float(p.get("max")) - float(p.get("min"))
          for p in ElementTree.parse(speaker).findall(".//vocal_tract_model/anatomy/param")}
points = {}
errors = []
edges = set()
for file in sorted((results / "fiber-paths").glob("*.csv")):
    previous = None
    with file.open() as stream:
        for row in csv.DictReader(stream):
            labels = list(row)[list(row).index("HX"):]
            if float(row["min_area_cm2"]) < .12:
                previous = None
                continue
            x = tuple(round(float(row[k]), 10) for k in labels)
            e = float(row["error_log"])
            if x not in points:
                points[x] = len(errors)
                errors.append(e)
            i = points[x]
            assert abs(errors[i]-e) < 1e-8
            if previous is not None and previous != i:
                edges.add(tuple(sorted((previous, i))))
            previous = i

# On a graph an edge enters at the larger endpoint value. Elder rule pairing.
parent = list(range(len(errors)))
def find(i):
    while parent[i] != i:
        parent[i] = parent[parent[i]]
        i = parent[i]
    return i

def save(name, fields, rows):
    with (out / name).open("w") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(fields)
        writer.writerows(rows)

bars = []
for death, i, j in sorted((max(errors[i], errors[j]), i, j) for i,j in edges):
    a, b = sorted((find(i), find(j)), key=lambda k: (errors[k], k))
    if a != b:
        parent[b] = a
        if errors[b] < death:
            bars.append((errors[b], death))
bars.extend((errors[i], np.inf) for i in range(len(errors)) if find(i) == i)
save("path-error-H0.csv", ["birth_log","death_log"], sorted(bars))
coords = np.asarray(list(points)) / [params[k] for k in labels]
radii = [.005,.01,.02,.05,.1]
summary = []
distance_bars = []
for tolerance in [.001,.003,.01,.02,.04]:
    cloud = coords[np.asarray(errors) <= tolerance]
    # H0 of the Rips filtration equals single-linkage clustering.
    deaths = [*linkage(cloud, method="single")[:,2], np.inf]
    distance_bars.extend((tolerance, 0, d) for d in deaths)
    counts = [sum(d > radius for d in deaths) for radius in radii]
    summary.append((tolerance,len(cloud),sum(b <= tolerance < d for b,d in bars),*counts))
save("distance-H0.csv", ["tolerance_log","birth_radius","death_radius"], distance_bars)
save("counts.csv", ["tolerance_log","points","path_components",*[f"r={r}" for r in radii]], summary)
print("vertices, edges:",len(points), len(edges))
for row in summary:
    print(*row)

# Show the full component-count curves, including all short-lived bars.
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

fig, (left, right) = plt.subplots(1, 2, figsize=(10, 4), layout="constrained")
events = sorted({v for bar in bars for v in bar if np.isfinite(v)})
left.step(np.asarray(events)*100, [sum(b <= t < d for b,d in bars) for t in events],
          where="post")
left.set(xlabel="Maximum log-formant error × 100", ylabel="Connected components",
         title="Along measured paths")
for tolerance, *_ in summary:
    ds = np.sort([d for t, _, d in distance_bars if t == tolerance])
    radius = np.r_[0.,ds[np.isfinite(ds)],max(.1,ds[-2])]
    right.step(radius,len(ds)-np.searchsorted(ds,radius,side="right"),where="post",
               label=f"{100*tolerance:g}")
right.set(xscale="log", yscale="log", xlim=(.001,.25), xlabel="Normalized shape distance",
          ylabel="Connected components", title="Within each formant band")
right.legend(title="Log error × 100", fontsize=8)
fig.savefig(out / "components.png", dpi=160)
