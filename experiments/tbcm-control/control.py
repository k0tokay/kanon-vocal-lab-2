"""Prototype of the upper control layer: the changes that the diagnosis supports.

1. Consonants keep the register of the vowel (make_register_speaker): the consonant glottal
   shapes take TA and CT (and flutter) from "modal", and LCA, IA, PCA are solved so that the
   glottal opening (vocal process position and posterior opening) stays that of the old
   shape (invert.py). Only the speaker file changes.
2. The glottal gesture right after a voiceless consonant begins 15 ms later and is approached
   faster (time constant 6 ms instead of 10 ms): the glottis stays open as long as before
   (same VOT) and then closes early in the vowel.
3. The lung pressure follows the F0 (pressure_follows_f0): p = p0 (F0 / 220 Hz)^k, k = 1.
   2 and 3 change only the gestural score.

    ./run.sh control.py in.speaker out.speaker    # change 1
    from control import render                    # accent.render with changes 2 and 3
"""
import sys
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[0] / "japanese-accent"))
import accent                                         # noqa: E402
import invert, variants                               # noqa: E402


def make_register_speaker(src, dst):
    inv = invert.main(src)
    ch = {s: {k: inv[s][k] for k in ("lca", "ia", "pca", "ct", "ta", "flutter")} for s in variants.CONSONANT_SHAPES}
    out = variants.make_speaker("tmp-register", ch, src=src)
    Path(dst).write_text(out.read_text())
    out.unlink()
    return Path(dst)


def render(text, stem, speaker=accent.SPEAKER, pressure_k=1.0, ref_hz=220.0, close_tau=.006, close_delay=.015, **kw):
    """accent.render, then edits of the score, which is synthesized again into stem.wav:
    the lung pressure follows the F0 (pressure_k, 0 = off) and the glottal gesture after a
    voiceless one begins close_delay later and is approached with the time constant close_tau
    (None = off)."""
    r = accent.render(text, Path(stem), speaker=Path(speaker), **kw)
    edits = ([variants.pressure_follows_f0(pressure_k, ref_hz)] if pressure_k else []) + \
            ([variants.fast_close(close_tau, close_delay)] if close_tau else [])
    if edits:
        ges = Path(stem).with_suffix(".ges")
        variants.edit_xml(*edits)(ges, None)
        lib = accent.use_speaker(Path(speaker))
        import ctypes as ct
        from scipy.io.wavfile import write
        count = ct.c_int()
        assert lib.vtlGesturalScoreToAudio(bytes(ges), b"", b"", None, ct.byref(count), 0, 0) == 0
        buf = (ct.c_double * count.value)()
        assert lib.vtlGesturalScoreToAudio(bytes(ges), b"", b"", buf, ct.byref(count), 0, 0) == 0
        audio = np.frombuffer(buf, dtype=np.float64)
        audio = audio / max(1e-9, np.abs(audio).max()) * .8
        write(Path(stem).with_suffix(".wav"), lib.rate, (audio * 32767).astype(np.int16))
    return r


if __name__ == "__main__":
    make_register_speaker(*sys.argv[1:3])
