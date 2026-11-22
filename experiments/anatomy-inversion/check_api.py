"""Checks the anatomy API: identity, repeatability, acoustic effect and trajectory synthesis."""
import ctypes as ct
import json
import time
from pathlib import Path

import numpy as np
from scipy.io.wavfile import write
from scipy.signal import find_peaks

from vtl import Vtl, _ptr

out = Path(__file__).resolve().parent / "results/api-check"
out.mkdir(parents=True, exist_ok=True)
vtl = Vtl()


def db(tract):
    return 20 * np.log10(np.maximum(vtl.transfer_function(tract), 1e-12))


def formants(tract, n=4096):
    level = db(tract)
    ids, _ = find_peaks(level, prominence=5)
    freq = ids * vtl.rate / n
    return [float(f) for f in freq[(freq > 150) & (freq < 6500)][:3]]


def band_rms(a, b, n=4096):
    freq = np.arange(n // 2) * vtl.rate / n
    keep = (freq >= 200) & (freq <= 8000)
    return float(np.sqrt(np.mean((a[keep] - b[keep]) ** 2)))


report = {"names": vtl.anatomy_names, "reference": vtl.anatomy_reference.tolist(),
          "min": vtl.anatomy_min.tolist(), "max": vtl.anatomy_max.tolist(),
          "tract_names": vtl.tract_names, "glottis_names": vtl.glottis_names}
base_a, base_ranges = vtl.shape("a"), (vtl.tract_min.copy(), vtl.tract_max.copy())
base_db = db(base_a)

# 1. Setting the reference anatomy should leave shapes, ranges and acoustics unchanged.
vtl.set_anatomy(vtl.anatomy_reference)
report["identity"] = {
    "shape_max_abs": float(np.max(np.abs(vtl.shape("a") - base_a))),
    "range_max_abs": float(max(np.max(np.abs(vtl.tract_min - base_ranges[0])), np.max(np.abs(vtl.tract_max - base_ranges[1])))),
    "transfer_rms_db": band_rms(db(vtl.shape("a")), base_db),
}

# 2. One-parameter changes of +/-15 % of each range, applied to the adapted /a/ shape.
effects = {}
for i, name in enumerate(vtl.anatomy_names):
    row = {}
    for sign in (-1, 1):
        x = vtl.anatomy_reference.copy()
        x[i] += sign * 0.15 * (vtl.anatomy_max[i] - vtl.anatomy_min[i])
        applied = vtl.set_anatomy(x)
        a = vtl.shape("a")
        row["+" if sign > 0 else "-"] = {"value": float(applied[i]), "formants": formants(a),
                                          "transfer_rms_db": band_rms(db(a), base_db)}
    effects[name] = row
report["formants_reference"] = formants(base_a)
report["one_parameter"] = effects

# 3. Repeatability: A, B, A must give the same acoustics.
rng = np.random.default_rng(0)
x_a = vtl.anatomy_min + rng.uniform(0.2, 0.8, 13) * (vtl.anatomy_max - vtl.anatomy_min)
x_b = vtl.anatomy_min + rng.uniform(0.2, 0.8, 13) * (vtl.anatomy_max - vtl.anatomy_min)
vtl.set_anatomy(x_a); first = db(vtl.shape("a")); vtl.export_svg(vtl.shape("a"), out / "random-a.svg")
vtl.set_anatomy(x_b); vtl.export_svg(vtl.shape("a"), out / "random-b.svg")
vtl.set_anatomy(x_a); again = db(vtl.shape("a"))
report["repeat_transfer_max_abs_db"] = float(np.max(np.abs(first - again)))

# 4. Long pharynx vs short pharynx /a/ and SVGs.
for label, frac in (("short-pharynx", 0.1), ("long-pharynx", 0.9)):
    x = vtl.anatomy_reference.copy(); k = vtl.anatomy_names.index("H0")
    x[k] = vtl.anatomy_min[k] + frac * (vtl.anatomy_max[k] - vtl.anatomy_min[k])
    vtl.set_anatomy(x); vtl.export_svg(vtl.shape("a"), out / f"{label}-a.svg")
vtl.set_anatomy(vtl.anatomy_reference); vtl.export_svg(base_a, out / "reference-a.svg")

# 5. Trajectory synthesis equals the frame-by-frame API and its speed.
step = vtl.rate // 100
frames = 101
w = 0.5 - 0.5 * np.cos(np.linspace(0, np.pi, frames))[:, None]
tract = vtl.shape("a") + w * (vtl.shape("i") - vtl.shape("a"))
glottis = np.tile(vtl.glottis_neutral, (frames, 1))
t = time.time(); audio = vtl.synthesize(tract, glottis, step); fast = time.time() - t
vtl._call("vtlResetTractSynthesis")
buffer = np.zeros(step); loop = []
vtl._call("vtlSynthesisAddTract", 0, _ptr(buffer), _ptr(tract[0].copy()), _ptr(glottis[0].copy()))
for k in range(1, frames):
    vtl._call("vtlSynthesisAddTract", step, _ptr(buffer), _ptr(tract[k].copy()), _ptr(glottis[k].copy()))
    loop.append(buffer.copy())
loop = np.concatenate(loop)
report["trajectory"] = {"seconds": len(audio) / vtl.rate, "max_abs_diff_vs_loop": float(np.max(np.abs(audio - loop))),
                        "real_time_factor": fast / (len(audio) / vtl.rate), "peak": float(np.max(np.abs(audio)))}
write(out / "ai-reference.wav", vtl.rate, (audio / max(1e-9, np.max(np.abs(audio))) * 0.9 * 32767).astype(np.int16))
(out / "report.json").write_text(json.dumps(report, indent=1))
print(json.dumps({k: report[k] for k in ("identity", "repeat_transfer_max_abs_db", "trajectory", "formants_reference")}, indent=1))
for name, row in effects.items():
    print(name, {s: (round(v["value"], 2), [round(f) for f in v["formants"]], round(v["transfer_rms_db"], 2)) for s, v in row.items()})
