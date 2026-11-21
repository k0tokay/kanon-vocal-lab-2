"""Hold the reference, traverse the measured path at constant normalized speed, hold the endpoint."""
import json
import os
from pathlib import Path
import numpy as np
from scipy.io import wavfile
os.environ["VTL_EXPERIMENT_SPEAKER"]=str(Path(__file__).resolve().parents[2]/"speakers/fulkhisa-kanon/fulkhisa-kanon-v0-8-vowel-variation.speaker")
from run import out,call,ptr,shape,rate,labels,voice
folder=out/"integrated"
audio={}
for vowel in "ao":
    ref=shape(vowel)
    ref[labels.index("VO")]=min(0.,ref[labels.index("VO")])
    for mode in ["insensitive","sensitive"]:
        path=json.loads((folder/f"{vowel}-{mode}.json").read_text())
        length=np.array([0.]+[p["length"] for p in path])
        points=np.vstack([ref]+[p["x"] for p in path])
        call("vtlResetTractSynthesis")
        chunks=[]
        for i in range(601):
            t=i*.0025
            at=length[-1]*np.clip((t-.25)/1.,0,1)
            x=np.array([np.interp(at,length,column) for column in points.T])
            g=voice.copy()
            g[1]=8000*np.clip(min(t,1.5-t)/.035,0,1)
            block=np.empty(120 if i else 0)
            call("vtlSynthesisAddTract",len(block),ptr(block),ptr(x),ptr(g))
            chunks.append(block)
        audio[vowel,mode]=np.concatenate(chunks)
call("vtlClose")
gain=30000/max(np.max(np.abs(y)) for y in audio.values())
for vowel in "ao":
    parts=[]
    for mode in ["insensitive","sensitive"]:
        pcm=np.round(gain*audio[vowel,mode]).astype(np.int16)
        assert len(pcm)==round(1.5*rate) and pcm.min()<0<pcm.max()
        parts.append(pcm)
    wavfile.write(folder/f"{vowel}-paths.wav",rate,np.concatenate([parts[0],np.zeros(rate//3,dtype=np.int16),parts[1]]))
