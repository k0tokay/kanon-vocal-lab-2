"""Render the manual inverse solutions and inspect the entire interpolated vocal tract path."""
import csv
import os
from pathlib import Path

import numpy as np
from scipy.io import wavfile

root = Path(__file__).resolve().parents[2]
os.environ["VTL_EXPERIMENT_SPEAKER"] = str(root / "speakers/fulkhisa-kanon/fulkhisa-kanon-v0-8-vowel-variation.speaker")
from run import area, call, final, labels, out, rate, sound, spectrum

folder = out / "manual"
clips = {}
diagnostics = []
baselines = {}
def geometry(x):
    distance, areas = area(x)
    j = np.argmin(areas)
    return areas[j], distance[j]

def inspect(vowel, stage, name, x):
    db = spectrum(x, 8192)
    if stage == "reference":
        baselines[vowel] = db
    hz = np.arange(len(db))*rate/8192
    delta = (db-baselines[vowel])[(hz>=200)&(hz<=8000)]
    path = [geometry(x+(final-x)*k/64) for k in range(65)]
    k = np.argmin([point[0] for point in path])
    diagnostics.append([vowel,stage,name,*path[0],*path[k],2.5*k,np.sqrt(np.mean(delta**2))])

with (folder / "shapes.csv").open() as f:
    for row in csv.DictReader(f):
        v, stage, name = row["vowel"], row["stage"], row["start"].removeprefix("from-")
        x = np.array([float(row[key]) for key in labels])
        inspect(v,stage,name,x)
        clips[v,stage,name] = sound(x)
# Re-evaluate the last ABAB pair with its actual original speaker.
from run import speaker
call("vtlClose")
old = speaker.with_name("fulkhisa-kanon-v0-8-vtl24.speaker")
call("vtlInitialize",bytes(old))
from run import shape
final = shape("i")
with (out / "wide-starts/o.csv").open() as f:
    for row in csv.DictReader(f):
        if row["start"] in ("reference","from-a"):
            inspect("prior-o","reference" if row["start"]=="reference" else "fitted",row["start"],np.array([float(row[key]) for key in labels]))
call("vtlClose")
with (folder / "geometry.csv").open("w") as f:
    w=csv.writer(f);w.writerow(["vowel","stage","shape","static_min_cm2","static_position_cm_from_glottis","transition_min_cm2","transition_position_cm_from_glottis","transition_time_ms","transfer_delta_rms_dB"]);w.writerows(diagnostics)
gain=30000/max(np.max(np.abs(y)) for y in clips.values())
for v in ("a","o"):
    playlist=[]
    for (vowel,stage,name),y in clips.items():
        if vowel!=v:continue
        pcm=np.round(y*gain).astype(np.int16)
        assert len(pcm)==round(.615*rate) and pcm.min()<0<pcm.max()
        wavfile.write(folder/f"{v}-{name}-{stage}.wav",rate,pcm)
        playlist.extend([pcm,np.zeros(round(.30*rate),dtype=np.int16)])
    wavfile.write(folder/f"{v}-comparison.wav",rate,np.concatenate(playlist[:-1]))
