"""Calls into VTL's C++ backend through `libVocalTractLabApi` (ctypes).

The API holds one speaker at a time and only loads speakers from files, so
`Backend.use(speaker)` writes the speaker tree to a temporary file and calls
`vtlInitialize` -- but only when the parts the computation depends on (the
anatomy and the glottis models) changed. Shape parameters are passed with
each call, so editing a shape never reloads.

What it computes from a vector of vocal tract parameters:

- `tube`: the area function (VTL's 40 tube sections);
- `spectrum`: the volume velocity transfer function (glottis to lips);
- `formants`: peaks of that spectrum;
- `contours`: the midsagittal outline, from `vtlExportTractSvg`;
- `sustained`: a held vowel (time-domain synthesis, `vtlSynthesisAddTract`);
- `glottis_wave`: glottal area, glottal flow and output of a held vowel, per
  sample, from the "misc" file of `vtlGesturalScoreToAudio` (the only API
  call that gives the glottis signals).

The library is found through `VTL_LIB`, else `build-mac/gui/libVocalTractLabApi.dylib`
of this checkout.
"""

from __future__ import annotations

import ctypes as ct
import hashlib
import os
import re
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .speaker import Speaker

REPO = Path(__file__).resolve().parents[2]
SVG_SCALE = 37.8  # VocalTract::exportTractContourSvg: 1 cm = 37.8 units, y flipped

# Polylines of exportTractContourSvg, in order (includeTeeth on, ribs and center line off).
CONTOUR_NAMES = (
    "upper_cover_back", "uvula", "upper_front",  # upper front: palate, upper incisors, upper lip
    "lower_cover_larynx", "epiglottis", "lower_front",  # lower front: tongue floor, lower incisors, lower lip
    "tongue", "tongue_side",
    "upper_teeth_inner", "upper_teeth_outer", "upper_teeth_back",
    "lower_teeth_inner", "lower_teeth_outer", "lower_teeth_back",
)


def library_path() -> Path:
    env = os.environ.get("VTL_LIB")
    return Path(env) if env else REPO / "build-mac" / "gui" / "libVocalTractLabApi.dylib"


_D = ct.POINTER(ct.c_double)
_I = ct.POINTER(ct.c_int)


def _arr(n: int) -> np.ndarray:
    return np.zeros(n, dtype=np.float64)


def _p(a: np.ndarray):
    return a.ctypes.data_as(_D)


@dataclass
class Tube:
    length_cm: np.ndarray  # per section
    area_cm2: np.ndarray
    articulator: np.ndarray  # VTL's articulator code per section
    position_cm: np.ndarray  # start of each section, from the glottis
    incisor_pos_cm: float
    tongue_tip_side_elevation: float
    velum_opening_cm2: float

    def to_json(self) -> dict:
        return {k: (v.tolist() if isinstance(v, np.ndarray) else v) for k, v in self.__dict__.items()}


class Backend:
    """The one VTL instance of this process. Calls are serialized by a lock."""

    def __init__(self, lib: str | Path | None = None):
        self.lib_path = Path(lib) if lib else library_path()
        if not self.lib_path.exists():
            raise FileNotFoundError(
                f"{self.lib_path} not found: build it with "
                "`cmake -S . -B build-mac/gui && cmake --build build-mac/gui -j8`, or set VTL_LIB")
        L = ct.CDLL(str(self.lib_path))
        L.vtlInitialize.argtypes = [ct.c_char_p]
        L.vtlGetConstants.argtypes = [_I, _I, _I, _I]
        L.vtlGetTractParamInfo.argtypes = [ct.c_char_p, _D, _D, _D]
        L.vtlGetTractParams.argtypes = [ct.c_char_p, _D]
        L.vtlTractToTube.argtypes = [_D, _D, _D, _I, _D, _D, _D]
        L.vtlGetTransferFunction.argtypes = [_D, ct.c_int, _D, _D]
        L.vtlExportTractSvg.argtypes = [_D, ct.c_char_p]
        L.vtlSynthesisAddTract.argtypes = [ct.c_int, _D, _D, _D]
        L.vtlGesturalScoreToAudio.argtypes = [ct.c_char_p, ct.c_char_p, ct.c_char_p, _D, _I, ct.c_int, ct.c_int]
        self.L = L
        self.lock = threading.RLock()
        self._key: str | None = None
        self._tmp = tempfile.TemporaryDirectory(prefix="vtl-")
        self.sampling_rate = 0
        self.num_tube_sections = 0
        self.num_tract_params = 0
        self.num_glottis_params = 0

    # -- loading ------------------------------------------------------------

    @staticmethod
    def _key_of(speaker: Speaker) -> str:
        """Hash of what the API state depends on: everything but the vocal tract shapes."""
        h = hashlib.sha256()
        out: list[str] = []
        speaker.anatomy.write(out)
        speaker.doc.root.child("glottis_models").write(out)
        h.update("".join(out).encode())
        return h.hexdigest()

    def use(self, speaker: Speaker) -> None:
        with self.lock:
            key = self._key_of(speaker)
            if key == self._key:
                return
            f = Path(self._tmp.name) / "speaker.speaker"
            f.write_text(speaker.text(), encoding="utf-8", newline="")
            if self.L.vtlInitialize(str(f).encode()) != 0:
                self._key = None
                raise RuntimeError("vtlInitialize failed")
            sr, nt, nv, ng = ct.c_int(), ct.c_int(), ct.c_int(), ct.c_int()
            self.L.vtlGetConstants(ct.byref(sr), ct.byref(nt), ct.byref(nv), ct.byref(ng))
            self.sampling_rate, self.num_tube_sections = sr.value, nt.value
            self.num_tract_params, self.num_glottis_params = nv.value, ng.value
            self._key = key

    def load_all(self, speaker: Speaker) -> None:
        """Load the whole speaker, shapes included (gestural scores name their shapes)."""
        with self.lock:
            self._key = None
            self.use(speaker)

    def invalidate(self) -> None:
        with self.lock:
            self._key = None

    # -- queries --------------------------------------------------------------

    def _params(self, speaker: Speaker, params) -> np.ndarray:
        self.use(speaker)
        if isinstance(params, str):
            params = speaker.tract_shape(params)
        x = np.ascontiguousarray(params, dtype=np.float64)
        if x.size != self.num_tract_params:
            raise ValueError(f"{x.size} vocal tract parameters, the API has {self.num_tract_params}")
        return x

    def tract_params_of_shape(self, speaker: Speaker, shape: str) -> np.ndarray:
        """The shape as VTL read it from the file (for checks)."""
        with self.lock:
            self._key = None  # the loaded shapes may be stale: reload
            self.use(speaker)
            x = _arr(self.num_tract_params)
            if self.L.vtlGetTractParams(shape.encode(), _p(x)) != 0:
                raise KeyError(shape)
            return x

    def tract_param_info(self, speaker: Speaker) -> dict:
        with self.lock:
            self.use(speaker)
            n = self.num_tract_params
            names = ct.create_string_buffer(32 * n)
            lo, hi, neutral = _arr(n), _arr(n), _arr(n)
            self.L.vtlGetTractParamInfo(names, _p(lo), _p(hi), _p(neutral))
            return {"names": names.value.decode().split(), "min": lo, "max": hi, "neutral": neutral}

    def tube(self, speaker: Speaker, params) -> Tube:
        """Area function of a shape (name) or a parameter vector."""
        with self.lock:
            x = self._params(speaker, params)
            n = self.num_tube_sections
            length, area = _arr(n), _arr(n)
            art = np.zeros(n, dtype=np.int32)
            inc, tts, velum = ct.c_double(), ct.c_double(), ct.c_double()
            self.L.vtlTractToTube(_p(x), _p(length), _p(area), art.ctypes.data_as(_I),
                                  ct.byref(inc), ct.byref(tts), ct.byref(velum))
        pos = np.concatenate([[0.0], np.cumsum(length)[:-1]])
        return Tube(length, area, art, pos, inc.value, tts.value, velum.value)

    def spectrum(self, speaker: Speaker, params, n: int = 8192) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Transfer function: (frequency [Hz], magnitude, phase [rad]) up to Nyquist."""
        with self.lock:
            x = self._params(speaker, params)
            mag, phase = _arr(n), _arr(n)
            self.L.vtlGetTransferFunction(_p(x), n, _p(mag), _p(phase))
            sr = self.sampling_rate
        half = n // 2 + 1
        return np.arange(half) * sr / n, mag[:half], phase[:half]

    def formants(self, speaker: Speaker, params, count: int = 4, n: int = 8192,
                 fmin: float = 150.0, fmax: float = 7000.0) -> list[float]:
        """Peaks of the transfer function in dB, parabolically interpolated [Hz]."""
        f, mag, _ = self.spectrum(speaker, params, n)
        db = 20 * np.log10(np.maximum(mag, 1e-12))
        df = f[1] - f[0]
        out: list[float] = []
        for i in range(1, len(db) - 1):
            if not (fmin <= f[i] <= fmax and db[i] > db[i - 1] and db[i] >= db[i + 1]):
                continue
            a, b, c = db[i - 1], db[i], db[i + 1]
            den = a - 2 * b + c
            off = 0.5 * (a - c) / den if den != 0 else 0.0
            out.append(float(f[i] + off * df))
            if len(out) == count:
                break
        return out

    def contours(self, speaker: Speaker, params) -> dict[str, np.ndarray]:
        """Midsagittal outline: name -> (k, 2) array of (x, y) in cm, VTL's coordinates."""
        with self.lock:
            x = self._params(speaker, params)
            f = Path(self._tmp.name) / "contour.svg"
            if self.L.vtlExportTractSvg(_p(x), str(f).encode()) != 0:
                raise RuntimeError("vtlExportTractSvg failed")
            svg = f.read_text()
        lines = re.findall(r'<polyline[^>]*points="([^"]*)"', svg)
        if len(lines) != len(CONTOUR_NAMES):
            raise RuntimeError(f"expected {len(CONTOUR_NAMES)} polylines, got {len(lines)}")
        out = {}
        for name, pts in zip(CONTOUR_NAMES, lines):
            a = np.array(pts.split(), dtype=np.float64).reshape(-1, 2) / SVG_SCALE
            a[:, 1] = -a[:, 1]
            out[name] = a
        return out

    # -- sound ------------------------------------------------------------------

    def sustained(self, speaker: Speaker, params, duration: float = 1.0,
                  glottis_shape: str = "modal", fade: float = 0.03) -> tuple[np.ndarray, int]:
        """A held vowel: the tract shape `params` with the selected glottis model's
        `glottis_shape` (its f0 and pressure are the speaker's). The lung pressure
        rises over the first and falls over the last `fade` seconds, and the
        output fades the same way. Returns (samples, sampling rate)."""
        glottis = glottis_vector(speaker, glottis_shape)
        step = 96  # 2 ms chunks at 48 kHz
        with self.lock:
            x = self._params(speaker, params)
            if len(glottis) != self.num_glottis_params:
                raise ValueError(f"{len(glottis)} glottis parameters, the API has {self.num_glottis_params}")
            sr = self.sampling_rate
            n = int(round(duration * sr / step))
            p_index = _pressure_index(speaker)
            t = np.arange(n + 1) * step / sr
            ramp = np.clip(np.minimum(t / fade, (n * step / sr - t) / fade), 0.0, 1.0)
            out = np.zeros(n * step)
            buf = _arr(step)
            self.L.vtlResetTractSynthesis()
            for k in range(n + 1):
                g = np.array(glottis, dtype=np.float64)
                if p_index is not None:
                    g[p_index] *= ramp[k]
                if self.L.vtlSynthesisAddTract(0 if k == 0 else step, _p(buf), _p(x), _p(g)) != 0:
                    raise RuntimeError("vtlSynthesisAddTract failed")
                if k:
                    out[(k - 1) * step:k * step] = buf
        m = min(len(out), int(fade * sr))  # output fade on top of the pressure ramp
        if m:
            w = 0.5 - 0.5 * np.cos(np.pi * np.arange(m) / m)
            out[:m] *= w
            out[-m:] *= w[::-1]
        return out, sr

    def glottis_wave(self, speaker: Speaker, tract_shape: str, glottis_shape: str = "modal",
                     duration: float = 0.3, periods: int = 4) -> dict:
        """A held vowel of `duration` s through a gestural score (tract shape and glottis
        shape by name, f0 and lung pressure from the glottis shape), and of its last
        `periods` periods (ending 5 ms before the end): glottal area [cm^2] (the
        narrower of the lower and upper area, plus the posterior or chink area where
        the model has one), glottal flow [cm^3/s] and the output (radiated) signal.
        Also the f0 asked for and the f0 measured from the flow."""
        m = speaker.selected_glottis
        if glottis_shape not in m.shapes:
            raise KeyError(f"{m.type}: no glottis shape {glottis_shape!r}")
        if tract_shape not in speaker.tract_shapes:
            raise KeyError(f"no vocal tract shape {tract_shape!r}")
        values = dict(zip((p.abbr for p in sorted(m.control, key=lambda p: p.index)),
                          m.shape_values(glottis_shape)))
        f0 = float(values.get("f0", 120.0))
        pressure = float(values.get("pressure", 8000.0))
        st = 12 * np.log2(max(f0, 1.0))  # semitones re 1 Hz (GesturalScore::REFERENCE_FREQUENCY)
        x = lambda v: _xml_attr(v)  # noqa: E731
        ges = (
            "<gestural_score>\n"
            f'  <gesture_sequence type="vowel-gestures" unit=""><gesture value="{x(tract_shape)}" slope="0" duration_s="{duration}" time_constant_s="0.012" neutral="0" /></gesture_sequence>\n'
            '  <gesture_sequence type="lip-gestures" unit=""></gesture_sequence>\n'
            '  <gesture_sequence type="tongue-tip-gestures" unit=""></gesture_sequence>\n'
            '  <gesture_sequence type="tongue-body-gestures" unit=""></gesture_sequence>\n'
            '  <gesture_sequence type="velic-gestures" unit=""></gesture_sequence>\n'
            f'  <gesture_sequence type="glottal-shape-gestures" unit=""><gesture value="{x(glottis_shape)}" slope="0" duration_s="{duration}" time_constant_s="0.012" neutral="0" /></gesture_sequence>\n'
            f'  <gesture_sequence type="f0-gestures" unit="st"><gesture value="{st:.6f}" slope="0" duration_s="{duration}" time_constant_s="0.03" neutral="0" /></gesture_sequence>\n'
            '  <gesture_sequence type="lung-pressure-gestures" unit="dPa">'
            '<gesture value="0" slope="0" duration_s="0.01" time_constant_s="0.005" neutral="0" />'
            f'<gesture value="{pressure:.3f}" slope="0" duration_s="{duration - 0.01}" time_constant_s="0.005" neutral="0" />'
            "</gesture_sequence>\n"
            "</gestural_score>\n")
        with self.lock:
            self.load_all(speaker)  # the current shapes, edits included
            d = Path(self._tmp.name)
            (d / "wave.ges").write_text(ges, encoding="utf-8")
            misc = d / "wave.misc.txt"
            sr = self.sampling_rate
            audio = _arr(int(duration * sr) + 4 * sr // 100)
            n = ct.c_int()
            r = self.L.vtlGesturalScoreToAudio(str(d / "wave.ges").encode(), b"", str(misc).encode(),
                                               _p(audio), ct.byref(n), 0, 0)
            if r != 0:
                raise RuntimeError(f"vtlGesturalScoreToAudio failed ({r})")
            with open(misc) as f:
                names = [h.split("[")[0] for h in f.readline().split()]
                cols = {k: names.index(k) for k in ("glottal_flow", "lower_area", "upper_area",
                                                    "posterior_area", "chink_area") if k in names}
                data = np.loadtxt(f, usecols=sorted(cols.values()), ndmin=2)
        col = {k: data[:, sorted(cols.values()).index(i)] for k, i in cols.items()}
        flow = col["glottal_flow"]
        area = np.minimum(col["lower_area"], col["upper_area"])
        if "posterior_area" in col:  # TBCM: the posterior gap is in parallel
            area = area + col["posterior_area"]
        out = audio[:n.value]
        k = min(len(flow), len(out))
        f0_measured = _f0_autocorr(flow[max(0, k - sr // 10):k], sr)
        span = int(round(periods * sr / max(f0, 40.0)))
        end = k - sr // 200
        a = max(0, end - span)
        return {
            "sampling_rate": sr,
            "start_s": a / sr,
            "f0_target": f0,
            "f0_measured": f0_measured,
            "pressure": pressure,
            "area_cm2": area[a:end],
            "flow_cm3_s": flow[a:end],
            "output": out[a:end],
        }


def _xml_attr(v: str) -> str:
    return v.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;")


def _f0_autocorr(x: np.ndarray, sr: int, lo: float = 50.0, hi: float = 1000.0) -> float | None:
    """F0 of a periodic signal from the autocorrelation peak; None if not periodic."""
    if len(x) < sr // lo * 2:
        return None
    x = x - x.mean()
    if not np.any(x):
        return None
    n = len(x)
    f = np.fft.rfft(x, 2 * n)
    r = np.fft.irfft(f * np.conj(f))[:n]
    a, b = int(sr / hi), int(sr / lo)
    i = a + int(np.argmax(r[a:b]))
    if r[i] < 0.3 * r[0]:
        return None
    if 0 < i < n - 1:  # parabolic interpolation
        y0, y1, y2 = r[i - 1], r[i], r[i + 1]
        den = y0 - 2 * y1 + y2
        i = i + (0.5 * (y0 - y2) / den if den else 0.0)
    return float(sr / i)


def glottis_vector(speaker: Speaker, shape: str = "modal") -> list[float]:
    """Control parameters of the selected glottis model for one of its shapes;
    the parameters' defaults when the model has no such shape."""
    m = speaker.selected_glottis
    if shape in m.shapes:
        return m.shape_values(shape)
    return [p.default for p in sorted(m.control, key=lambda p: p.index)]


def _pressure_index(speaker: Speaker) -> int | None:
    for p in speaker.selected_glottis.control:
        if p.abbr == "pressure" or p.name.lower().startswith("lung pressure") or "pressure" in p.name.lower():
            return p.index
    return None


def wav_bytes(x: np.ndarray, sr: int, peak: float = 0.9) -> bytes:
    """16-bit mono WAV. Scaled down only if it would clip."""
    import io
    import wave
    a = np.max(np.abs(x)) if len(x) else 0.0
    y = x * (peak / a) if a > peak else x
    pcm = np.round(np.clip(y, -1, 1) * 32767).astype("<i2")
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())
    return b.getvalue()


_backend: Backend | None = None


def backend() -> Backend:
    global _backend
    if _backend is None:
        _backend = Backend()
    return _backend
