"""Run from the repository root with the macOS API built (numpy, scipy, matplotlib)."""
import ctypes as ct
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.io.wavfile import write
from scipy.optimize import least_squares
from scipy.signal import find_peaks

root = Path(__file__).resolve().parents[2]
out = Path(__file__).resolve().parent / "results"
out.mkdir(exist_ok=True)
speaker = root / "speakers/fulkhisa-kanon/fulkhisa-kanon-v0-8-vtl24.speaker"
lib = ct.CDLL(str(root / "build-mac/gui/libVocalTractLabApi.dylib"))
def call(function, *args):
    status = getattr(lib, function)(*args)
    if status:
        raise RuntimeError(f"{function}: {status}")

def ptr(values):
    return values.ctypes.data_as(ct.POINTER(ct.c_double))

call("vtlInitialize", bytes(speaker))
constants = [ct.c_int() for _ in range(4)]
call("vtlGetConstants", *map(ct.byref, constants))
rate, sections, size, glottis_size = [v.value for v in constants]
def shape(name):
    values = np.empty(size)
    call("vtlGetTractParams", name.encode(), ptr(values))
    return values

reference, final = shape("a"), shape("i")
low, high, neutral = [np.empty(size) for _ in range(3)]
names = ct.create_string_buffer(1024)
call("vtlGetTractParamInfo", names, *map(ptr, [low, high, neutral]))
labels = names.value.decode().split()
def spectrum(x, n):
    mag, phase = np.empty(n), np.empty(n)
    call("vtlGetTransferFunction", ptr(x), n, ptr(mag), ptr(phase))
    return 20*np.log10(np.maximum(mag[:n//2], 1e-12))

def peaks(db, n):
    ids, _ = find_peaks(db, prominence=5)
    ids = ids[(ids*rate/n > 150) & (ids*rate/n < 6500)][:3]
    if len(ids) != 3:
        raise ValueError("Missing oral resonance")
    left, mid, right = db[ids-1], db[ids], db[ids+1]
    return (ids + 0.5*(left-right)/(left-2*mid+right))*rate/n

def area(x):
    lengths, areas = np.empty(sections), np.empty(sections)
    arts = (ct.c_int*sections)()
    scalars = [ct.c_double() for _ in range(3)]
    call("vtlTractToTube", ptr(x), ptr(lengths), ptr(areas), arts, *map(ct.byref, scalars))
    return np.cumsum(lengths)-lengths/2, areas

model = ET.parse(speaker).find('.//glottis_model[@selected="1"]')
modal = model.find('./shapes/shape[@name="modal"]')
voice = np.array([float(p.get("value")) for p in modal])
assert len(voice) == glottis_size
def sound(x):
    call("vtlResetTractSynthesis")
    chunks = []
    previous, previous_pressure = x, 0
    for duration, target, pressure in [(0,x,0),(.035,x,8000),(.22,x,8000),
                                       (.16,final,8000),(.16,final,8000),(.04,final,0)]:
        steps = max(1, round(duration/.0025))
        for step in range(1,steps+1):
            fraction = step/steps
            glottis = voice.copy()
            glottis[1] = previous_pressure + fraction*(pressure-previous_pressure)
            samples = np.zeros(round(duration*rate/steps))
            tract = previous + fraction*(target-previous)
            call("vtlSynthesisAddTract", len(samples), ptr(samples), ptr(tract), ptr(glottis))
            chunks.append(samples)
        previous, previous_pressure = target, pressure
    return np.concatenate(chunks)

# Keep each named perturbation fixed; solve only the compensating tongue coordinates.
tongue = [labels.index(name) for name in ["TCX","TCY","TBX","TBY"]]
candidates = {"reference": reference}
formants = {}
starts = {"open-jaw":{"JA":-0.8}, "protruded-lips":{"LP":0.35}, "raised-jaw":{"JA":0.85}}
def initial(offsets):
    x = reference.copy()
    for key, shift in offsets.items():
        k = labels.index(key)
        x[k] = np.clip(x[k]+shift,low[k],high[k])
    return x

def fit(x, free):
    for n in [1024,4096]:
        goal = peaks(spectrum(reference,n),n)
        def residual(v):
            candidate = x.copy()
            candidate[free] = v
            return (peaks(spectrum(candidate,n),n)-goal)/goal
        sol = least_squares(residual,x[free],bounds=(low[free],high[free]),
                            diff_step=.002,max_nfev=45,gtol=1e-8)
        x[free] = sol.x
    return x

if __name__ == "__main__":
    for name, offsets in starts.items():
        candidates[name] = fit(initial(offsets), tongue)
        candidates["free-"+name] = fit(initial(offsets), tongue+[labels.index("JA"), labels.index("LP")])
        print(name, flush=True)

    n = 8192
    freq = np.arange(n//2)*rate/n
    mask = (freq>=200)&(freq<=8000)
    ref_db = spectrum(reference,n)
    ref_xy, ref_area = area(reference)
    figure, axes = plt.subplots(3,1,figsize=(9,10),layout="constrained")
    audio = {}
    for name,x in candidates.items():
        db = spectrum(x,n)
        xy, areas = area(x)
        show = name == "reference" or name.startswith("free-")
        if show:
            axes[0].plot(xy,areas,label=name)
        if show:
            axes[1].plot(freq[mask],db[mask],label=name)
        track = []
        for t in np.linspace(0,1,17):
            track.append(peaks(spectrum(x*(1-t)+final*t,n),n))
        track = np.array(track)
        if show:
            axes[2].plot(np.linspace(0,160,17),track[:,1],label=name)
        audio[name] = sound(x)
        call("vtlExportTractSvg",ptr(x),bytes(out/(name+".svg")))
        formants[name] = dict(params=dict(zip(labels,x)),formants_Hz=peaks(db,n).tolist(),
                            transfer_rms_dB=float(np.sqrt(np.mean((db[mask]-ref_db[mask])**2))),
                            transition_Hz=track.tolist())
    scale = 30000/max(np.max(np.abs(y)) for y in audio.values())
    for name,y in audio.items():
        write(out/(name+".wav"),rate,np.round(y*scale).astype(np.int16))
    axes[0].set(xlabel="Distance from glottis (cm)",ylabel="Area (cm²)")
    axes[1].set(xlabel="Frequency (Hz)",ylabel="Transfer magnitude (dB)")
    axes[2].set(xlabel="Linear /a/ to /i/ transition (ms)",ylabel="F2 (Hz)")
    axes[0].legend()
    figure.savefig(out/"comparison.png",dpi=145)
    (out/"measurements.json").write_text(json.dumps(formants,indent=2)+"\n")
    call("vtlClose")
