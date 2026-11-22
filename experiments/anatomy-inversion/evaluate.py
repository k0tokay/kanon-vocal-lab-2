"""Evaluates an EmJEm run against the known synthetic ground truth.

Run from this directory: python3 evaluate.py DATA_DIR RUN_DIR [--resynth 120]
Writes RUN_DIR/eval.json.
"""
import argparse
import json
from pathlib import Path

import numpy as np
import torch
from scipy.fft import dct

from emjem import N_TRACT, Inference, Normalizer, infer, load_corpus, log_mel
from synth import Pool


def pearson(a, b):
    a, b = a - a.mean(), b - b.mean()
    den = np.sqrt((a * a).sum() * (b * b).sum())
    return float((a * b).sum() / den) if den > 1e-12 else np.nan


def mel_cepstral_distance(mel_a, mel_b, order=25):
    """MCD-style distance in dB between log-amplitude mel cepstra (DCT of the 144 log-mel bins, c0 ignored).

    The cepstrum is not SPTK's mel-cepstrum, so absolute values are not comparable with published MCD;
    use it only to compare runs.
    """
    m = mel_a.shape[1]
    ca = dct(0.5 * mel_a, type=2, norm="ortho", axis=1)[:, 1:order] / np.sqrt(m / 2)
    cb = dct(0.5 * mel_b, type=2, norm="ortho", axis=1)[:, 1:order] / np.sqrt(m / 2)
    db = 10 / np.log(10) * np.sqrt(2 * ((ca - cb) ** 2).sum(1))
    return float(db.mean())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("data", type=Path)
    parser.add_argument("run", type=Path)
    parser.add_argument("--resynth", type=int, default=120, help="test utterances to resynthesize")
    args = parser.parse_args()
    meta = json.loads((args.data / "meta.json").read_text())
    run_args = json.loads((args.run / "args.json").read_text())
    mode = run_args["mode"]
    norm = Normalizer(meta)
    stats = np.load(args.run / "mel_stats.npz")
    mel_stats = (stats["mean"], stats["std"])
    device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
    model = Inference(mode != "fix").to(device)
    model.load_state_dict(torch.load(args.run / "model.pt", map_location=device))

    corpus = load_corpus(args.data, norm)
    frames_hat, anatomy_hat = infer(model, [c["mel"] for c in corpus], device, mel_stats)
    reference = norm.anatomy(np.array(meta["anatomy_reference"]))
    speakers = sorted({c["speaker"] for c in corpus})

    # Speaker-level anatomy (mean over the speaker's utterances).
    speaker_true, speaker_hat, test_flag = [], [], []
    for s in speakers:
        ids = [i for i, c in enumerate(corpus) if c["speaker"] == s]
        speaker_true.append(corpus[ids[0]]["true_anatomy"])
        speaker_hat.append(reference if mode == "fix" else np.mean([anatomy_hat[i] for i in ids], 0))
        test_flag.append(corpus[ids[0]]["test"])
    speaker_true, speaker_hat, test_flag = map(np.array, (speaker_true, speaker_hat, test_flag))
    names = meta["anatomy_names"]
    result = {"mode": mode, "anatomy": {}}
    for split, keep in (("train_speakers", ~test_flag), ("test_speakers", test_flag), ("all_speakers", np.ones_like(test_flag))):
        t, h = speaker_true[keep], speaker_hat[keep]
        result["anatomy"][split] = {
            "rmse_norm": float(np.sqrt(((t - h) ** 2).mean())),
            "rmse_norm_predict_mean": float(np.sqrt(((t - t.mean(0)) ** 2).mean())),
            "per_param_r": {n: pearson(t[:, k], h[:, k]) for k, n in enumerate(names)} if mode != "fix" else None,
            "per_param_rmse": {n: float(np.sqrt(((t[:, k] - h[:, k]) ** 2).mean())) for k, n in enumerate(names)}}
    # Utterance-level spread of the anatomy estimate around the speaker mean.
    if mode != "fix":
        spread = []
        for s, mean in zip(speakers, speaker_hat):
            ids = [i for i, c in enumerate(corpus) if c["speaker"] == s]
            spread.append(np.std([anatomy_hat[i] for i in ids], 0))
        result["anatomy"]["within_speaker_std_norm"] = dict(zip(names, np.mean(spread, 0).round(4).tolist()))

    # Frame tracks: per-utterance correlation per dimension, then averaged.
    frame_names = meta["tract_names"] + meta["glottis_names"]
    for split, test in (("train", False), ("test", True)):
        ids = [i for i, c in enumerate(corpus) if c["test"] == test]
        r = np.array([[pearson(corpus[i]["true_frames"][:, k], frames_hat[i][:, k]) for k in range(len(frame_names))]
                      for i in ids])
        f0 = norm.f0 + N_TRACT
        log_f0_err = []
        for i in ids:
            true_g = norm.frames_inv(corpus[i]["true_frames"], np.zeros(N_TRACT), np.ones(N_TRACT))[1]
            hat_g = norm.frames_inv(frames_hat[i], np.zeros(N_TRACT), np.ones(N_TRACT))[1]
            voiced = true_g[:, 1] > 0.5 * true_g[:, 1].max()
            log_f0_err.append(np.log(hat_g[voiced, norm.f0]) - np.log(true_g[voiced, norm.f0]))
        log_f0_err = np.concatenate(log_f0_err)
        result[f"frames_{split}"] = {
            "mean_r_tract": float(np.nanmean(r[:, :N_TRACT])),
            "mean_r_glottis": float(np.nanmean(r[:, N_TRACT:])),
            "per_dim_r": dict(zip(frame_names, np.nanmean(r, 0).round(3).tolist())),
            "log_f0_rmse": float(np.sqrt((log_f0_err ** 2).mean())),
            "rmse_norm_tract": float(np.sqrt(np.mean([((corpus[i]["true_frames"][:, :N_TRACT] - frames_hat[i][:, :N_TRACT]) ** 2).mean() for i in ids])))}

    # Acoustic match on resynthesized test utterances.
    rng = np.random.default_rng(0)
    test_ids = [i for i, c in enumerate(corpus) if c["test"]]
    chosen = rng.choice(test_ids, min(args.resynth, len(test_ids)), replace=False)
    speaker_of = {s: h for s, h in zip(speakers, speaker_hat)}
    pool = Pool()
    anat = [norm.anatomy_inv(reference if mode == "fix" else (anatomy_hat[i] if mode == "ut" else speaker_of[corpus[i]["speaker"]])) for i in chosen]
    ranges = pool.ranges(anat)
    jobs = []
    for i, a, (lo, hi) in zip(chosen, anat, ranges):
        tract, glottis = norm.frames_inv(frames_hat[i], lo, hi)
        jobs.append((a, tract, glottis))
    audio = pool.render(jobs)
    pool.close()
    mcd = [mel_cepstral_distance(corpus[i]["mel"], log_mel(wav, len(corpus[i]["mel"])))
           for i, wav in zip(chosen, audio) if wav is not None]
    result["resynthesis_test"] = {"utterances": len(mcd), "cepstral_distance_db": float(np.mean(mcd))}
    (args.run / "eval.json").write_text(json.dumps(result, indent=1))
    summary = {k: result["anatomy"]["all_speakers"][k] for k in ("rmse_norm", "rmse_norm_predict_mean")}
    print(json.dumps({"mode": mode, "anatomy_all": summary,
                      "frames_test": {k: result["frames_test"][k] for k in ("mean_r_tract", "mean_r_glottis", "log_f0_rmse")},
                      "resynthesis_test": result["resynthesis_test"]}, indent=1))


if __name__ == "__main__":
    main()
