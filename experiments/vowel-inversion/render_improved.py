"""Render the native formant solver's CSV shapes with a shared source and gain."""
import csv
import numpy as np
from scipy.io import wavfile
from run import call, labels, out, rate, sound, spectrum

folder = out / "improved-audio"
folder.mkdir(exist_ok=True)
clips = {}
rows = []
for vowel, filename in [("a", "improve-formants.csv"), ("o", "improve-formants-o.csv")]:
    with (out / filename).open() as stream:
        candidates = list(csv.DictReader(stream))
    assert [c["start"] for c in candidates] == ["reference", "open-jaw", "protruded-lips", "raised-jaw"]
    for candidate in candidates:
        name = candidate["start"]
        tract = np.array([float(candidate[key]) for key in labels])
        clips[vowel, name] = sound(tract)
        db = spectrum(tract, 8192)
        if name == "reference":
            baseline = db
        hz = np.arange(len(db)) * rate / 8192
        difference = (db - baseline)[(hz >= 200) & (hz <= 8000)]
        rows.append([vowel, name, candidate["rms_percent"], np.sqrt(np.mean(difference**2))])
call("vtlClose")
gain = 30000 / max(np.max(np.abs(clip)) for clip in clips.values())
for vowel in ["a", "o"]:
    playlist = []
    for (v, name), clip in clips.items():
        if v != vowel:
            continue
        pcm = np.round(clip * gain).astype(np.int16)
        assert len(pcm) == round(.615 * rate) and pcm.min() < 0 < pcm.max()
        wavfile.write(folder / f"{vowel}-{name}.wav", rate, pcm)
        if playlist:
            playlist.append(np.zeros(round(.35 * rate), dtype=np.int16))
        playlist.append(pcm)
    wavfile.write(folder / f"{vowel}-comparison.wav", rate, np.concatenate(playlist))
with (folder / "comparison.csv").open("w") as stream:
    writer = csv.writer(stream)
    writer.writerow(["vowel","start","F123_relative_rms_percent","static_transfer_rms_dB_200_8000Hz"])
    writer.writerows(rows)
