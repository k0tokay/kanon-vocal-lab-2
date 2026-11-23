"""Evaluates an EmJEm run on a real corpus (prep_jvs.py), where no ground truth exists.

Run from this directory: python3 evaluate_real.py DATA_DIR RUN_DIR [--resynth 200] [--examples 8]
Writes RUN_DIR/eval.json, RUN_DIR/speakers.csv and RUN_DIR/examples/*.wav. It reports
- per-speaker anatomy (mean over utterances), its within-speaker spread, and the female-male difference,
- the vocal tract length of the speaker's adapted /a/ (a sanity check: adult men are longer than women),
- the inferred median f0 against the speaker's tagged f0 range,
- the cepstral distance of resynthesized utterances (same measure as evaluate.py).
"""
import argparse
import json
from pathlib import Path

import numpy as np
import torch
from scipy.io.wavfile import write

from emjem import Inference, Normalizer, infer, load_corpus, log_mel, match_level, pick_device, start_memory_guard, use_run_speaker
from evaluate import mel_cepstral_distance, pearson
from synth import AUDIO_RATE, Pool
from vtl import Vtl


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("data", type=Path)
    parser.add_argument("run", type=Path)
    parser.add_argument("--resynth", type=int, default=200)
    parser.add_argument("--examples", type=int, default=8, help="speakers to write example wavs for")
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument("--max-memory-gb", type=float, default=10.0, help="0 disables the memory guard")
    args = parser.parse_args()
    start_memory_guard(args.max_memory_gb)
    meta = use_run_speaker(args.run, json.loads((args.data / "meta.json").read_text()))
    mode = json.loads((args.run / "args.json").read_text())["mode"]
    norm = Normalizer(meta)
    stats = np.load(args.run / "mel_stats.npz")
    mel_stats = (stats["mean"], stats["std"])
    device = pick_device()
    model = Inference(mode != "fix").to(device)
    model.load_state_dict(torch.load(args.run / "model.pt", map_location=device))

    corpus = load_corpus(args.data, norm)
    frames_hat, anatomy_hat = infer(model, [c["mel"] for c in corpus], device, mel_stats, np.float16)
    reference = norm.anatomy(np.array(meta["anatomy_reference"]))
    names = meta["anatomy_names"]
    speakers = sorted({c["speaker"] for c in corpus})
    labels = meta["speaker_names"]
    gender = np.array([meta["tags"].get(labels[s], {}).get("gender", "?") for s in speakers])

    ids_of = {s: [i for i, c in enumerate(corpus) if c["speaker"] == s] for s in speakers}
    if mode == "fix":
        speaker_hat = np.array([reference for _ in speakers])
        spread = np.zeros_like(speaker_hat)
    else:
        speaker_hat = np.array([np.mean([anatomy_hat[i] for i in ids_of[s]], 0) for s in speakers])
        spread = np.array([np.std([anatomy_hat[i] for i in ids_of[s]], 0) for s in speakers])

    # Inferred f0 (median over voiced frames) and tract length of /a/ with the speaker's anatomy.
    vtl = Vtl()
    f0_hat, length_a = [], []
    for s, a in zip(speakers, speaker_hat):
        f0s = []
        for i in ids_of[s]:
            _, g = norm.frames_inv(frames_hat[i].astype(np.float32), np.zeros(19), np.ones(19))
            voiced = g[:, 1] > 0.5 * max(g[:, 1].max(), 1e-9)
            f0s.append(g[voiced, norm.f0])
        f0_hat.append(float(np.median(np.concatenate(f0s))))
        vtl.set_anatomy(norm.anatomy_inv(a))
        length_a.append(float(vtl.tube(vtl.shape("a"))[0].sum()))
    f0_hat, length_a = np.array(f0_hat), np.array(length_a)
    tag_f0 = np.array([np.sqrt(meta["tags"].get(labels[s], {}).get("f0_min", np.nan) *
                               meta["tags"].get(labels[s], {}).get("f0_max", np.nan)) for s in speakers])
    vtl.set_anatomy(meta["anatomy_reference"])
    reference_length = float(vtl.tube(vtl.shape("a"))[0].sum())

    female, male = gender == "F", gender == "M"
    result = {"mode": mode, "vtl_speaker": meta.get("speaker", "default"), "speakers": len(speakers), "female": int(female.sum()), "male": int(male.sum()),
              "reference_length_a_cm": reference_length}
    if mode != "fix":
        diff = speaker_hat[female].mean(0) - speaker_hat[male].mean(0)
        pooled = np.sqrt((speaker_hat[female].var(0) + speaker_hat[male].var(0)) / 2) + 1e-9
        result["anatomy"] = {
            n: {"mean_female": float(speaker_hat[female, k].mean()), "mean_male": float(speaker_hat[male, k].mean()),
                "cohen_d_female_minus_male": float(diff[k] / pooled[k]),
                "between_speaker_std": float(speaker_hat[:, k].std()),
                "within_speaker_std": float(spread[:, k].mean()),
                "r_with_tag_f0": pearson(np.log(tag_f0), speaker_hat[:, k]) if np.all(np.isfinite(tag_f0)) else None}
            for k, n in enumerate(names)}
    result["length_a_cm"] = {"female_mean": float(length_a[female].mean()), "male_mean": float(length_a[male].mean()),
                             "female_std": float(length_a[female].std()), "male_std": float(length_a[male].std())}
    if np.all(np.isfinite(tag_f0)):
        result["f0"] = {"r_log_inferred_vs_tag": pearson(np.log(f0_hat), np.log(tag_f0)),
                        "median_ratio_inferred_to_tag": float(np.median(f0_hat / tag_f0))}

    # Resynthesis with the speaker-level anatomy (utterance-level for UT-AM).
    rng = np.random.default_rng(0)
    chosen = rng.choice(len(corpus), min(args.resynth, len(corpus)), replace=False)
    example_speakers = set(speakers[k] for k in np.concatenate(
        [np.flatnonzero(female)[: args.examples // 2], np.flatnonzero(male)[: args.examples - args.examples // 2]]))
    chosen = np.unique(np.concatenate([chosen, [ids_of[s][0] for s in example_speakers]]))
    speaker_of = dict(zip(speakers, speaker_hat))
    anat = [norm.anatomy_inv(reference if mode == "fix" else
                             (anatomy_hat[i] if mode == "ut" else speaker_of[corpus[i]["speaker"]])) for i in chosen]
    pool = Pool(args.workers)
    ranges = pool.ranges(anat)
    jobs = [(a, *norm.frames_inv(frames_hat[i].astype(np.float32), lo, hi)) for i, a, (lo, hi) in zip(chosen, anat, ranges)]
    audio = pool.render(jobs)
    pool.close()
    out = args.run / "examples"
    out.mkdir(exist_ok=True)
    mcd = []
    for i, wav in zip(chosen, audio):
        if wav is None or not np.all(np.isfinite(wav)):
            continue
        wav = match_level(wav, meta, rng)
        mcd.append(mel_cepstral_distance(corpus[i]["mel"], log_mel(wav, len(corpus[i]["mel"]))))
        c = corpus[i]
        if c["speaker"] in example_speakers and i == ids_of[c["speaker"]][0]:
            d = np.load(args.data / f"spk{c['speaker']:03d}.npz")
            original = d["audio"][: d["audio_len"][0]]
            peak = lambda x: x / max(np.max(np.abs(x)), 1e-9) * 0.8
            pair = np.concatenate([peak(original), np.zeros(AUDIO_RATE // 2), peak(wav)])
            write(out / f"{labels[c['speaker']]}-original-then-resynth.wav", AUDIO_RATE, (pair * 32767).astype(np.int16))
    result["resynthesis"] = {"utterances": len(mcd), "cepstral_distance_db": float(np.mean(mcd))}

    with open(args.run / "speakers.csv", "w") as f:
        f.write("speaker,gender,tag_f0,inferred_f0,length_a_cm," + ",".join(names) + "\n")
        for k, s in enumerate(speakers):
            f.write(f"{labels[s]},{gender[k]},{tag_f0[k]:.1f},{f0_hat[k]:.1f},{length_a[k]:.2f},"
                    + ",".join(f"{v:.3f}" for v in norm.anatomy_inv(speaker_hat[k])) + "\n")
    (args.run / "eval.json").write_text(json.dumps(result, indent=1))
    print(json.dumps({k: result[k] for k in ("mode", "length_a_cm", "resynthesis") if k in result}
                     | ({"f0": result["f0"]} if "f0" in result else {}), indent=1))


if __name__ == "__main__":
    main()
