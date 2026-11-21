"""Compare fixed and re-timed alveolar gestures with independent copies of the vowel shapes."""
import csv
import ctypes as c
import json
import subprocess
import tempfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from xml.etree import ElementTree as ET
import numpy as np
from scipy.io import wavfile

base=Path(__file__).resolve().parent
root=base.parents[1]
results=base/"results"
folder=results/"large-ara"
speaker=results/"integrated-long/kanon-long-paths.speaker"
template=results/"integrated-long/ara.ges"
def render(job):
    name, params=job
    lib=c.CDLL(str(root/"build-mac/gui/libVocalTractLabApi.dylib"))
    metrics=[]
    with tempfile.TemporaryDirectory() as tmp:
        tmp=Path(tmp)
        tree=ET.parse(speaker)
        shapes=tree.find(".//vocal_tract_model/shapes")
        vowel=ET.fromstring(ET.tostring(shapes.find('shape[@name="a"]')))
        vowel.set("name","evaluation-a")
        for param in vowel:
            param.set("value",str(params[param.get("name")]))
        shapes.append(vowel)
        sp=tmp/"speaker.xml"
        tree.write(sp)
        assert lib.vtlInitialize(bytes(sp))==0
        score=ET.parse(template)
        for g in score.findall('.//gesture_sequence[@type="vowel-gestures"]/gesture[@value="a"]'):
            g.set("value","evaluation-a")
        fixed=tmp/"fixed.ges";score.write(fixed)
        tier=score.find('.//gesture_sequence[@type="tongue-tip-gestures"]')
        total=sum(float(g.get("duration_s")) for g in tier)
        for g in list(tier)[1:]:tier.remove(g)
        tier[0].set("duration_s",f"{total:.6f}")
        neutral=tmp/"neutral.ges";score.write(neutral)
        tuned=folder/f"{name}-retimed.ges"
        subprocess.run([str(root/"build-mac/retime-tap"),str(sp),str(neutral),str(tuned)],cwd=root,check=True)
        for kind,ges in [("fixed",fixed),("retimed",tuned)]:
            tube=tmp/"score.tube"
            assert lib.vtlGesturalScoreToTubeSequence(bytes(ges),bytes(tube))==0
            lines=[l for l in tube.read_text().splitlines() if l and not l.startswith("#")][4:]
            times=[];minimum=np.inf
            for i in range(0,len(lines),5):
                ms=i//5*2.5
                if not 200<=ms<=400:continue
                a,l,k=[np.fromstring(line,sep=" ") for line in lines[i+2:i+5]]
                tongue=np.where(k==1)[0]
                if not tongue.size:continue
                end=np.cumsum(l)
                region=tongue[end[tongue[-1]]-(end[tongue]-l[tongue]*.5)<2.2]
                val=min(a[region]);minimum=min(minimum,val)
                if val<.0002:times.append(ms)
            count=c.c_int()
            assert lib.vtlGesturalScoreToAudio(bytes(ges),b"",b"",None,c.byref(count),0,0)==0
            buf=(c.c_double*count.value)()
            assert lib.vtlGesturalScoreToAudio(bytes(ges),b"",b"",buf,c.byref(count),0,0)==0
            metrics.append((name,kind,times,minimum,np.array(buf)))
        assert lib.vtlClose()==0
    return metrics
def export_gui_and_pairs():
    tree=ET.parse(root/"speakers/fulkhisa-kanon/fulkhisa-kanon-v0-8-vowel-variation.speaker")
    shapes=tree.find(".//vocal_tract_model/shapes")
    params=list(csv.DictReader((results/"manual/shapes.csv").open()))
    checkpoints=list(csv.DictReader((results/"integrated-long/checkpoints.csv").open()))
    for name in ("reference","a-compare","a-compare-2","insensitive","sensitive"):
        if name in ("insensitive","sensitive"):
            row=[r for r in checkpoints if r["shape"].startswith("a-"+name+"-")][-1]
        else:
            row=next(r for r in params if r["vowel"]=="a" and r["start"].removeprefix("from-")==name and r["stage"] in ("reference","fitted"))
        alias="eval-"+name
        alt=ET.fromstring(ET.tostring(shapes.find('shape[@name="a"]')))
        alt.set("name",alias)
        for par in alt:par.set("value",row[par.get("name")])
        shapes.append(alt)
        for kind in ("fixed","retimed"):
            dest=folder/f"{name}-{kind}.ges"
            ges=ET.parse(template if kind=="fixed" else dest)
            for g in ges.findall('.//gesture_sequence[@type="vowel-gestures"]/gesture'):
                if g.get("value") in ("evaluation-a","a"):g.set("value",alias)
            ges.write(dest,encoding="utf-8")
        if name!="reference":
            clips=[wavfile.read(folder/f"{name}-{k}.wav")[1] for k in ("fixed","retimed")]
            wavfile.write(folder/f"{name}-pair.wav",48000,np.concatenate([clips[0],np.zeros(14400,dtype="int16"),clips[1]]))
    tree.write(folder/"ara-evaluation.speaker",encoding="utf-8")

if __name__=="__main__":
    folder.mkdir(exist_ok=True)
    jobs=[]
    for row in csv.DictReader((results/"manual/shapes.csv").open()):
        if row["vowel"]=="a" and row["stage"] in ("reference","fitted"):
            jobs.append((row["start"].removeprefix("from-"),row))
    checkpoints=list(csv.DictReader((results/"integrated-long/checkpoints.csv").open()))
    for mode in ("insensitive","sensitive"):
        row=[r for r in checkpoints if r["shape"].startswith("a-"+mode+"-")][-1]
        jobs.append((mode,row))
    with ProcessPoolExecutor(5) as pool:
        records=[r for group in pool.map(render,jobs) for r in group]
    gain=30000/max(np.max(abs(r[-1])) for r in records)
    groups={"fixed":[],"retimed":[]}
    summary=[]
    for name,kind,times,minimum,y in records:
        pcm=np.round(y*gain).astype("int16");assert pcm.min()<0<pcm.max()
        wavfile.write(folder/f"{name}-{kind}.wav",48000,pcm)
        groups[kind].append(pcm)
        summary.append(dict(shape=name,condition=kind,closed_ms=2.5*len(times),frames_ms=times,min_area_cm2=minimum))
    for kind,clips in groups.items():
        pieces=[]
        for y in clips:pieces.extend([y,np.zeros(14400,dtype="int16")])
        wavfile.write(folder/f"compare-{kind}.wav",48000,np.concatenate(pieces[:-1]))
    (folder/"summary.json").write_text(json.dumps(summary,indent=2)+"\n")
    for r in summary: print(r)
    export_gui_and_pairs()
