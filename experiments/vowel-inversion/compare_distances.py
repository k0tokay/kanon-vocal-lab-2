"""Compare static endpoints against their own speaker/vowel reference."""
import csv
import json
import xml.etree.ElementTree as ET
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

base = Path(__file__).resolve().parent
results = base / "results"
speakers = base.parents[1] / "speakers/fulkhisa-kanon"
rows = []

def read(path):
    with (results / path).open() as f:
        return list(csv.DictReader(f))

def record(group, vowel, label, candidate, ref, db, err):
    file = "fulkhisa-kanon-v0-8-" + ("vowel-variation" if group == "manual" else "vtl24") + ".speaker"
    anatomy = ET.parse(speakers / file).find(".//vocal_tract_model/anatomy")
    assert anatomy.find("tongue/root").get("automatic_calc") == "1"
    differences = {}
    for p in anatomy.findall("param"):
        key = p.get("name")
        if key in ("TRX","TRY","VO"):
            continue
        differences[key] = (float(candidate[key])-float(ref[key]))/(float(p.get("max"))-float(p.get("min")))
    assert len(differences) == 16
    d = np.array(list(differences.values()))
    top = sorted(differences,key=lambda k:abs(differences[k]),reverse=True)[:3]
    rows.append(dict(group=group,vowel=vowel,shape=label,L2=np.linalg.norm(d),RMS_percent=100*np.sqrt(np.mean(d*d)),
                     F123_RMS_percent=float(err),transfer_dB=float(db),largest=" ".join(top),**differences))

original = json.loads((results/"measurements.json").read_text())
ref = original["reference"]
for label, item in original.items():
    if label != "reference":
        error = 100*np.sqrt(np.mean((np.array(item["formants_Hz"])/ref["formants_Hz"]-1)**2))
        record("first","a",label,item["params"],ref["params"],item["transfer_rms_dB"],error)
for group in ("native","wide"):
    prefix = "improved-audio" if group=="native" else "wide-starts"
    for v in ("a","o"):
        path = ("improve-formants"+("-o" if v=="o" else "")+".csv") if group=="native" else f"{prefix}/{v}.csv"
        shapes = {r["start"]:r for r in read(path)}
        for r in read(prefix+"/comparison.csv"):
            if r["vowel"]==v and r["start"]!="reference":
                record(group,v,r["start"],shapes[r["start"]],shapes["reference"],r["static_transfer_rms_dB_200_8000Hz"],r["F123_relative_rms_percent"])
manual = read("manual/shapes.csv")
for r in read("manual/geometry.csv"):
    v,s,k = r["vowel"],r["stage"],r["shape"]
    if v=="prior-o" or s=="reference": continue
    item = next(x for x in manual if x["stage"]==s and x["start"]=="from-"+k)
    ref = next(x for x in manual if x["vowel"]==v and x["stage"]=="reference")
    record("manual",v,k+" "+s,item,ref,r["transfer_delta_rms_dB"],item["rms_percent"])
with (results/"shape-distances.csv").open("w") as f:
    writer=csv.DictWriter(f,rows[0]);writer.writeheader();writer.writerows(rows)
fig, axes=plt.subplots(1,2,sharex=True,sharey=True,figsize=(9,4),layout="constrained")
for ax,v in zip(axes,("a","o")):
    for group,color in zip(("first","native","wide","manual"),("gray","royalblue","darkorange","seagreen")):
        samples=[r for r in rows if r["group"]==group and r["vowel"]==v]
        for i,r in enumerate(samples):
            ax.scatter(r["L2"],r["transfer_dB"],facecolors=color if r["F123_RMS_percent"]<=1 else "none",
                       edgecolors=color,label=group if i==0 else None)
    ax.set(title=f"/{v}/",xlabel="Range-normalized parameter distance (L2)")
    ax.legend()
axes[0].set_ylabel("Static transfer magnitude difference (dB RMS)")
fig.savefig(results/"shape-distances.png",dpi=160)
