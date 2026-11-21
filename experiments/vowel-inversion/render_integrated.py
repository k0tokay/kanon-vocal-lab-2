"""Render static endpoints and a fixed-score tap crossover. Run after integrate.py."""
import copy
import ctypes as ct
import json
import sys
import os
import tempfile
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np
from scipy.io import wavfile

root=Path(__file__).resolve().parents[2]
os.environ["VTL_EXPERIMENT_SPEAKER"]=str(root/"speakers/fulkhisa-kanon/fulkhisa-kanon-v0-8-vowel-variation.speaker")
from run import call, labels, out, ptr, rate, shape, speaker, voice

long_path="--long" in sys.argv[1:]
folder=out/("integrated-long" if long_path else "integrated")
clips={}
records={}
modes=("reference","insensitive","sensitive")
endpoints={}
for v in "ao":
    ref=shape(v)
    ref[labels.index("VO")]=min(0.,ref[labels.index("VO")])
    endpoints[v,"reference"]=ref
    for mode in modes[1:]:
        endpoints[v,mode]=np.array(json.loads((folder/f"{v}-{mode}.json").read_text())[-1]["x"])
for (v,mode),x in endpoints.items():
    call("vtlResetTractSynthesis")
    blocks=[]
    for i in range(221):
        g=voice.copy()
        g[1]=8000*min(1.,i/14,(220-i)/16)
        block=np.empty(120 if i else 0)
        call("vtlSynthesisAddTract",len(block),ptr(block),ptr(x),ptr(g))
        blocks.append(block)
    clips[f"{v}-{mode}"]=np.concatenate(blocks)
call("vtlClose")

def contacts(tube):
    lines=[s for s in tube.read_text().splitlines() if s and s[0]!="#"][4:]
    times=[]
    for t in range(0,len(lines),5):
        a=np.fromstring(lines[t+2],sep=" ")
        l=np.fromstring(lines[t+3],sep=" ")
        k=np.fromstring(lines[t+4],sep=" ")
        tongue=np.flatnonzero(k==1)
        if tongue.size and any(a[j]<.0002 and sum(l[j:tongue[-1]+1])<2.2 for j in tongue):
            times.append(t//5*2.5)
    return times

for mode in modes:
    for adapted in ([False] if long_path or mode=="reference" else [False,True]):
        with tempfile.TemporaryDirectory() as tmp:
            tmp=Path(tmp)
            xml=ET.parse(speaker)
            shapes=xml.find(".//vocal_tract_model/shapes")
            base=shapes.find('shape[@name="a"]')
            alt=copy.deepcopy(base)
            alt.set("name","experiment-a")
            x=endpoints["a",mode]
            for p in alt:
                p.set("value",str(x[labels.index(p.get("name"))]))
            shapes.append(alt)
            tap=shapes.find('shape[@name="tt-tap-a"]')
            if adapted:
                for p in tap:
                    # Carry the baseline vowel-to-tap displacement to the new vowel posture.
                    j=labels.index(p.get("name"))
                    p.set("value",str(float(p.get("value"))+x[j]-endpoints["a","reference"][j]))
            sp=tmp/"test.speaker"
            xml.write(sp,encoding="utf-8")
            score=ET.parse(folder/"ara.ges")
            for g in score.findall('.//gesture_sequence[@type="vowel-gestures"]/gesture[@value="a"]'):
                g.set("value","experiment-a")
            ges=tmp/"test.ges"
            score.write(ges,encoding="utf-8")
            call("vtlInitialize",bytes(sp))
            # Query length before allocating the raw audio buffer.
            count=ct.c_int()
            call("vtlGesturalScoreToAudio",bytes(ges),b"",b"",None,ct.byref(count),0,0)
            y=np.empty(count.value)
            call("vtlGesturalScoreToAudio",bytes(ges),b"",b"",ptr(y),ct.byref(count),0,0)
            tube=tmp/"test.tube"
            call("vtlGesturalScoreToTubeSequence",bytes(ges),bytes(tube))
            name=f"ara-{mode}-"+("shifted" if adapted else "fixed")
            records[name]=contacts(tube)
            clips[name]=y
            call("vtlClose")
gain=30000/max(np.max(np.abs(y)) for y in clips.values())
for name,y in clips.items():
    assert np.isfinite(y).all() and np.min(y)<0<np.max(y)
    wavfile.write(folder/(name+".wav"),rate,np.round(y*gain).astype(np.int16))
def playlist(name, keys):
    gap=np.zeros(round(.28*rate),dtype=np.int16)
    parts=[]
    for key in keys:
        parts.extend([wavfile.read(folder/(key+".wav"))[1],gap])
    wavfile.write(folder/(name+".wav"),rate,np.concatenate(parts[:-1]))
for v in "ao":
    playlist(v+"-compare",[f"{v}-{m}" for m in modes])
playlist("ara-compare",[f"ara-{m}-fixed" for m in modes])
for m in ([] if long_path else modes[1:]):
    playlist("ara-"+m+"-pair",[f"ara-{m}-fixed",f"ara-{m}-shifted"])
(folder/"tap-contact-ms.json").write_text(json.dumps(records,indent=2)+"\n")
print(records)
