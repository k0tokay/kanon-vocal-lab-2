"""Parallel VTL synthesis of frame sequences with per-utterance anatomy.

Each worker process owns one VTL instance (the API keeps global state).
Frames are 10 ms apart; audio is returned at 16 kHz.
"""
import ctypes as ct
import multiprocessing as mp
import os
import tempfile

import numpy as np
from scipy.signal import resample_poly

from vtl import Vtl, _ptr

FRAME_RATE = 100
AUDIO_RATE = 16000
MAX_FRAMES = 2000

_vtl = None
_tmp = None


def _init():
    global _vtl, _tmp
    _vtl = Vtl()
    _tmp = tempfile.mkdtemp(prefix="vtl-worker-")


def _set_anatomy(anatomy):
    return _vtl.set_anatomy(anatomy)


def _render(anatomy, tract, glottis):
    """Synthesizes absolute tract/glottis frames with the given anatomy; returns 16 kHz audio."""
    _set_anatomy(anatomy)
    audio = _vtl.synthesize(tract, glottis, _vtl.rate // FRAME_RATE)
    audio = resample_poly(audio, AUDIO_RATE, _vtl.rate)
    # Pad to one sample per 10 ms frame so that frames and audio line up.
    return np.concatenate([np.zeros(AUDIO_RATE // FRAME_RATE), audio]).astype(np.float32)


def _score_frames(job):
    """Builds a gestural score from a segment list with the given anatomy and samples its frames."""
    anatomy, segments = job
    applied = _set_anatomy(anatomy)
    seg = os.path.join(_tmp, "u.seg")
    ges = os.path.join(_tmp, "u.ges")
    with open(seg, "w") as f:
        for name, duration in segments:
            f.write(f"name = {name}; duration_s = {duration:.4f};\n")
    if _vtl.lib.vtlSegmentSequenceToGesturalScore(seg.encode(), ges.encode()):
        raise RuntimeError("segment sequence")
    tract = np.empty(MAX_FRAMES * _vtl.num_tract)
    glottis = np.empty(MAX_FRAMES * _vtl.num_glottis)
    frames = ct.c_int()
    status = _vtl.lib.vtlGesturalScoreToParamFrames(ges.encode(), _vtl.rate // FRAME_RATE, _ptr(tract),
                                                     _ptr(glottis), MAX_FRAMES, ct.byref(frames))
    if status:
        raise RuntimeError(f"vtlGesturalScoreToParamFrames: {status}")
    n = frames.value
    return (applied, tract[: n * _vtl.num_tract].reshape(n, -1), glottis[: n * _vtl.num_glottis].reshape(n, -1),
            _vtl.tract_min.copy(), _vtl.tract_max.copy())


def _render_job(job):
    anatomy, tract, glottis = job
    try:
        return _render(anatomy, tract, glottis)
    except RuntimeError:
        return None


def _ranges(anatomy):
    _set_anatomy(anatomy)
    return _vtl.tract_min.copy(), _vtl.tract_max.copy()


class Pool:
    def __init__(self, workers=None):
        self.pool = mp.get_context("spawn").Pool(workers or os.cpu_count(), initializer=_init)

    def score_frames(self, jobs):
        return self.pool.map(_score_frames, jobs, chunksize=1)

    def render(self, jobs):
        return self.pool.map(_render_job, jobs, chunksize=1)

    def ranges(self, anatomies):
        return self.pool.map(_ranges, anatomies, chunksize=1)

    def close(self):
        self.pool.close()
        self.pool.join()
