"""Thin ctypes wrapper around the macOS VocalTractLab API (build-mac/gui)."""
import ctypes as ct
import os
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
LIBRARY = ROOT / "build-mac/gui/libVocalTractLabApi.dylib"
SPEAKER = ROOT / "speakers/fulkhisa-kanon/fulkhisa-kanon-v0-8-vtl24.speaker"


def _ptr(values):
    return values.ctypes.data_as(ct.POINTER(ct.c_double))


class Vtl:
    def __init__(self, speaker=None, library=LIBRARY):
        self.lib = ct.CDLL(str(library))
        speaker = Path(speaker or os.environ.get("VTL_EXPERIMENT_SPEAKER", SPEAKER))
        self._call("vtlInitialize", bytes(speaker))
        constants = [ct.c_int() for _ in range(4)]
        self._call("vtlGetConstants", *map(ct.byref, constants))
        self.rate, self.sections, self.num_tract, self.num_glottis = [c.value for c in constants]
        self.tract_names, self.tract_min, self.tract_max, self.tract_neutral = self._info(
            "vtlGetTractParamInfo", self.num_tract)
        self.glottis_names, self.glottis_min, self.glottis_max, self.glottis_neutral = self._info(
            "vtlGetGlottisParamInfo", self.num_glottis)
        self.anatomy_names, self.anatomy_min, self.anatomy_max, self.anatomy_reference = self.anatomy_info()

    def _call(self, function, *args):
        status = getattr(self.lib, function)(*args)
        if status:
            raise RuntimeError(f"{function}: {status}")

    def _info(self, function, n):
        names = ct.create_string_buffer(4096)
        low, high, neutral = (np.empty(n) for _ in range(3))
        self._call(function, names, *map(_ptr, (low, high, neutral)))
        return names.value.decode().split(), low, high, neutral

    def anatomy_info(self):
        names = ct.create_string_buffer(256)
        low, high, value = (np.empty(13) for _ in range(3))
        count = self.lib.vtlGetAnatomyParamInfo(names, *map(_ptr, (low, high, value)))
        if count != 13:
            raise RuntimeError(f"vtlGetAnatomyParamInfo: {count}")
        return names.value.decode().split(), low, high, value

    def set_anatomy(self, values):
        """Sets the anatomy (cm/deg), refreshes the adapted tract ranges and returns the clamped values."""
        values = np.array(values, dtype=float)
        self._call("vtlSetAnatomyParams", _ptr(values))
        _, self.tract_min, self.tract_max, self.tract_neutral = self._info("vtlGetTractParamInfo", self.num_tract)
        return values

    def shape(self, name):
        values = np.empty(self.num_tract)
        self._call("vtlGetTractParams", name.encode(), _ptr(values))
        return values

    def transfer_function(self, tract, n=4096):
        mag, phase = np.empty(n), np.empty(n)
        self._call("vtlGetTransferFunction", _ptr(np.ascontiguousarray(tract, dtype=float)), n, _ptr(mag), _ptr(phase))
        return mag[: n // 2]

    def export_svg(self, tract, path):
        self._call("vtlExportTractSvg", _ptr(np.ascontiguousarray(tract, dtype=float)), str(path).encode())

    def synthesize(self, tract_frames, glottis_frames, samples_per_frame):
        tract = np.ascontiguousarray(tract_frames, dtype=float)
        glottis = np.ascontiguousarray(glottis_frames, dtype=float)
        frames = len(tract)
        audio = np.empty((frames - 1) * samples_per_frame)
        self._call("vtlSynthesizeTrajectory", _ptr(tract), _ptr(glottis), frames, samples_per_frame, _ptr(audio))
        return audio
