"""Render the native formant solver's CSV shapes with a shared source and gain."""
import argparse
import csv
import numpy as np
from scipy.io import wavfile
from run import call, labels, out, rate, sound, spectrum

parser = argparse.ArgumentParser()
parser.add_argument("--wide", action="store_true")
wide = parser.parse_args().wide
folder = out / ("wide-starts" if wide else "improved-audio")
folder.mkdir(exist_ok=True)
clips = {}
rows = []
for vowel, filename in [("a", "improve-formants.csv"), ("o", "improve-formants-o.csv")]:
    with ((folder / (vowel+".csv")) if wide else (out / filename)).open() as stream:
        candidates = list(csv.DictReader(stream))
    if not wide:
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
    if wide:
        eligible = [row for row in rows if row[0] == vowel and row[1] != "reference" and float(row[2]) <= 1]
        if eligible:
            best = max(eligible, key=lambda row: row[3])[1]
            clips[vowel, "ABAB"] = np.concatenate(
                [np.concatenate([clips[vowel, name], np.zeros(round(.25*rate))])
                 for name in ["reference", best, "reference", best]])
            print(vowel, "ABAB candidate:", best)
call("vtlClose")
gain = 30000 / max(np.max(np.abs(clip)) for clip in clips.values())
for vowel in ["a", "o"]:
    playlist = []
    for (v, name), clip in clips.items():
        if v != vowel:
            continue
        pcm = np.round(clip * gain).astype(np.int16)
        assert pcm.min() < 0 < pcm.max()
        if name != "ABAB":
            assert len(pcm) == round(.615 * rate)
        wavfile.write(folder / f"{vowel}-{name}.wav", rate, pcm)
        if name == "ABAB":
            continue
        if playlist:
            playlist.append(np.zeros(round(.35 * rate), dtype=np.int16))
        playlist.append(pcm)
    wavfile.write(folder / f"{vowel}-comparison.wav", rate, np.concatenate(playlist))
with (folder / "comparison.csv").open("w") as stream:
    writer = csv.writer(stream)
    writer.writerow(["vowel","start","F123_relative_rms_percent","static_transfer_rms_dB_200_8000Hz"])
    writer.writerows(rows)
