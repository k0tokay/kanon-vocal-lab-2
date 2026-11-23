"""EmJEm training of an articulatory inference network with VTL (Sun, Huang & Wu, Interspeech 2022).

Run from this directory:
  python3 emjem.py DATA_DIR RUN_DIR --mode {fix,ut,sp,oracle} [--iterations 120] [--resume]

DATA_DIR is either synthetic (gen_dataset.py, with ground truth) or real speech (prep_jvs.py, meta "real": true).
For real speech the synthesized audio is brought to the corpus level and noise floor before the mel features.

--mode oracle skips EmJEm and trains on the true parameters of the training speakers
(a supervised upper bound for how much of the anatomy the audio reveals).

Each iteration: infer parameters for a subset of the target corpus, perturb them with
Gaussian noise (sigma = 0.5 * 0.98**iteration, temporally smoothed for the frame tracks),
synthesize with VTL, and train the network on the new (mel, parameter) pairs.
The ground-truth parameters of the target corpus are never used for training.
"""
import argparse
import json
import os
import re
import sys
import threading
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torchaudio
from scipy.ndimage import gaussian_filter1d

from synth import Pool

N_TRACT, N_GLOTTIS, N_ANATOMY = 19, 10, 13
N_FRAME = N_TRACT + N_GLOTTIS
N_MELS = 144
CROP = 200
TEST_SPEAKERS = 8


# ---------------------------------------------------------------------------
# Parameter normalization to [-1, 1]
# ---------------------------------------------------------------------------

def start_memory_guard(limit_gb):
    """Exits (status 75) if this process and its children use more than LIMIT_GB of resident memory.

    Swapping a large run on a laptop can stall the whole machine; a run stopped this way resumes with --resume.
    """
    if not limit_gb:
        return
    import psutil
    me = psutil.Process()

    def watch():
        while True:
            used = 0
            for p in [me] + me.children(recursive=True):
                try:
                    used += p.memory_info().rss
                except psutil.Error:
                    pass
            if used > limit_gb * 2**30:
                print(f"memory guard: {used / 2**30:.1f} GB > {limit_gb} GB, stopping", file=sys.stderr, flush=True)
                for p in me.children(recursive=True):
                    try:
                        p.kill()
                    except psutil.Error:
                        pass
                os._exit(75)
            time.sleep(2)

    threading.Thread(target=watch, daemon=True).start()


def use_run_speaker(run, meta, speaker=None, glottis_model=None):
    """Makes VTL (here and in synthesis workers) use the run's speaker file and refreshes the speaker-dependent meta.

    With SPEAKER, the file is copied to RUN/speaker.speaker (optionally selecting GLOTTIS_MODEL, e.g.
    "Geometric glottis 2019"); a run that already has that file keeps it, so --resume and evaluation reuse it.
    Without either, the default speaker (vtl.SPEAKER) and the corpus meta are used unchanged.
    """
    own = Path(run) / "speaker.speaker"
    if speaker and not own.exists():
        text = Path(speaker).read_text()
        if glottis_model:
            if f'type="{glottis_model}"' not in text:
                raise SystemExit(f"{speaker} has no glottis model {glottis_model!r}")
            text = re.sub(r'(<glottis_model type="([^"]+)" selected=")[01]"',
                          lambda m: m.group(1) + ("1" if m.group(2) == glottis_model else "0") + '"', text)
        own.write_text(text)
    if not own.exists():
        return meta
    os.environ["VTL_EXPERIMENT_SPEAKER"] = str(own.resolve())
    from vtl import Vtl
    vtl = Vtl()
    if vtl.glottis_names != meta["glottis_names"] or vtl.anatomy_names != meta["anatomy_names"]:
        raise SystemExit(f"{own}: its glottis/anatomy parameters differ from the corpus meta; "
                         "select a glottis model with the same parameters (--glottis-model)")
    return dict(meta, speaker=str(speaker or own), anatomy_reference=vtl.anatomy_reference.tolist(),
                anatomy_min=vtl.anatomy_min.tolist(), anatomy_max=vtl.anatomy_max.tolist(),
                glottis_min=vtl.glottis_min.tolist(), glottis_max=vtl.glottis_max.tolist())


class Normalizer:
    def __init__(self, meta):
        self.a_lo, self.a_hi = np.array(meta["anatomy_min"]), np.array(meta["anatomy_max"])
        self.g_lo, self.g_hi = np.array(meta["glottis_min"]), np.array(meta["glottis_max"])
        self.f0 = meta["glottis_names"].index("f0")
        self.g_lo[self.f0], self.g_hi[self.f0] = np.log(self.g_lo[self.f0]), np.log(self.g_hi[self.f0])

    def anatomy(self, a):
        return 2 * (a - self.a_lo) / (self.a_hi - self.a_lo) - 1

    def anatomy_inv(self, u):
        return self.a_lo + (np.clip(u, -1, 1) + 1) / 2 * (self.a_hi - self.a_lo)

    def frames(self, tract, glottis, t_lo, t_hi):
        g = glottis.copy()
        g[:, self.f0] = np.log(np.maximum(g[:, self.f0], 1.0))
        t = 2 * (tract - t_lo) / (t_hi - t_lo) - 1
        g = 2 * (g - self.g_lo) / (self.g_hi - self.g_lo) - 1
        return np.concatenate([t, g], axis=1).astype(np.float32)

    def frames_inv(self, u, t_lo, t_hi):
        u = np.clip(u, -1, 1)
        tract = t_lo + (u[:, :N_TRACT] + 1) / 2 * (t_hi - t_lo)
        g = self.g_lo + (u[:, N_TRACT:] + 1) / 2 * (self.g_hi - self.g_lo)
        g[:, self.f0] = np.exp(g[:, self.f0])
        return tract, g


# ---------------------------------------------------------------------------
# Features
# ---------------------------------------------------------------------------

_mel = torchaudio.transforms.MelSpectrogram(sample_rate=16000, n_fft=1024, win_length=400, hop_length=160,
                                            n_mels=N_MELS, f_min=50, f_max=8000, center=True)


def pick_device():
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("mps" if torch.backends.mps.is_available() else "cpu")


def active_rms(audio, rate=16000, range_db=40.0):
    """RMS over the 10 ms frames within range_db of the loudest frame."""
    hop = rate // 100
    n = len(audio) // hop
    if n == 0:
        return float(np.sqrt(np.mean(np.square(audio)) + 1e-20))
    energy = np.mean(np.square(audio[: n * hop].reshape(n, hop)), axis=1)
    active = energy >= energy.max() * 10 ** (-range_db / 10)
    return float(np.sqrt(energy[active].mean() + 1e-20))


def match_level(audio, meta, rng):
    """Scales synthesized audio to the corpus level and adds its noise floor (real corpora only)."""
    if "level_rms" not in meta:
        return audio
    audio = audio * (meta["level_rms"] / max(active_rms(audio), 1e-9))
    return (audio + meta["noise_floor"] * rng.standard_normal(len(audio))).astype(np.float32)


def log_mel(audio, frames):
    """Log-mel frames aligned with the 10 ms parameter frames (frame k at k*10 ms)."""
    m = _mel(torch.from_numpy(np.asarray(audio, dtype=np.float32)))
    m = torch.log(m + 1e-9).T.numpy()
    if len(m) < frames:
        m = np.concatenate([m, np.repeat(m[-1:], frames - len(m), 0)])
    return m[:frames]


# ---------------------------------------------------------------------------
# Network
# ---------------------------------------------------------------------------

class Inference(nn.Module):
    def __init__(self, with_anatomy):
        super().__init__()
        d = 144
        self.conv = nn.Sequential(
            nn.Conv1d(N_MELS, d, 5, padding=2), nn.GELU(),
            nn.Conv1d(d, d, 5, padding=2), nn.GELU(),
            nn.Conv1d(d, d, 5, padding=2), nn.GELU())
        self.conformer = torchaudio.models.Conformer(input_dim=d, num_heads=4, ffn_dim=4 * d, num_layers=3,
                                                     depthwise_conv_kernel_size=31, dropout=0.1)
        self.frame_head = nn.Linear(d, N_FRAME)
        self.with_anatomy = with_anatomy
        if with_anatomy:
            # A bidirectional LSTM summary of the whole utterance, written as two directional
            # LSTMs because packed sequences are very slow on MPS.
            self.lstm_fwd = nn.LSTM(d, 128, batch_first=True)
            self.lstm_bwd = nn.LSTM(d, 128, batch_first=True)
            self.anatomy_head = nn.Linear(256, N_ANATOMY)

    def forward(self, mel, lengths):
        x = self.conv(mel.transpose(1, 2)).transpose(1, 2)
        x, _ = self.conformer(x, lengths)
        frames = torch.tanh(self.frame_head(x))
        anatomy = None
        if self.with_anatomy:
            t = torch.arange(x.shape[1], device=x.device)[None]
            last = (lengths - 1).long()
            # Reverse each sequence within its own length (padding stays at the end).
            reverse = torch.where(t < lengths[:, None], lengths[:, None] - 1 - t, t).long()
            x_rev = torch.gather(x, 1, reverse[..., None].expand_as(x))
            out_f, _ = self.lstm_fwd(x)
            out_b, _ = self.lstm_bwd(x_rev)
            pick = lambda out: out[torch.arange(len(out), device=x.device), last]
            anatomy = torch.tanh(self.anatomy_head(torch.cat([pick(out_f), pick(out_b)], dim=1)))
        return frames, anatomy


def batches(items, size, rng, crop=CROP):
    order = rng.permutation(len(items))
    for i in range(0, len(order), size):
        chosen = [items[j] for j in order[i:i + size]]
        mels, targets, anatomies, lengths = [], [], [], []
        for mel, frames, anatomy in chosen:
            start = rng.integers(0, max(1, len(mel) - crop + 1))
            mels.append(mel[start:start + crop]); targets.append(frames[start:start + crop])
            anatomies.append(anatomy); lengths.append(len(mels[-1]))
        n = max(lengths)
        pad = lambda xs: np.stack([np.pad(x, ((0, n - len(x)), (0, 0))) for x in xs])
        yield (torch.from_numpy(pad(mels)).float(), torch.from_numpy(pad(targets)),
               torch.from_numpy(np.stack(anatomies).astype(np.float32)), torch.tensor(lengths))


@torch.no_grad()
def infer(model, mels, device, mel_stats):
    model.eval()
    out_frames, out_anatomy = [], []
    for mel in mels:
        x = torch.from_numpy(((mel - mel_stats[0]) / mel_stats[1]).astype(np.float32)).unsqueeze(0).to(device)
        frames, anatomy = model(x, torch.tensor([len(mel)], device=device))
        out_frames.append(frames[0].cpu().numpy())
        out_anatomy.append(None if anatomy is None else anatomy[0].cpu().numpy())
    return out_frames, out_anatomy


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

def load_corpus(data_dir, norm):
    """Utterances with log-mel features; true_frames/true_anatomy only for synthetic corpora.

    Synthetic corpora hold out the last speakers as test speakers; real corpora have no test split.
    """
    speakers = sorted(data_dir.glob("spk*.npz"))
    real = json.loads((data_dir / "meta.json").read_text()).get("real", False)
    n_test = 0 if real else min(TEST_SPEAKERS, max(1, len(speakers) // 4))
    corpus = []
    for s, path in enumerate(speakers):
        # Decompress each array once (indexing an NpzFile decompresses the whole array every time).
        d = dict(np.load(path))
        audio_off = np.concatenate([[0], np.cumsum(d["audio_len"])])
        frame_off = np.concatenate([[0], np.cumsum(d["frames"])])
        for u in range(len(d["frames"])):
            n = int(d["frames"][u])
            item = {"speaker": s, "test": s >= len(speakers) - n_test, "utterance": u,
                    # float16 halves the corpus in memory (JVS: 4.5 -> 2.2 GB); log-mel needs no more precision.
                    "mel": log_mel(d["audio"][audio_off[u]:audio_off[u + 1]], n).astype(np.float16)}
            if not real:
                tract, glottis = d["tract"][frame_off[u]:frame_off[u + 1]], d["glottis"][frame_off[u]:frame_off[u + 1]]
                item["true_frames"] = norm.frames(tract, glottis, d["tract_min"], d["tract_max"])
                item["true_anatomy"] = norm.anatomy(d["anatomy"]).astype(np.float32)
            corpus.append(item)
    return corpus


def smooth_noise(rng, frames, dims, sigma, width=3.0):
    noise = gaussian_filter1d(rng.standard_normal((frames, dims)), width, axis=0, mode="nearest")
    return sigma * noise / noise.std(axis=0, keepdims=True).clip(1e-6)


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("data", type=Path)
    parser.add_argument("run", type=Path)
    parser.add_argument("--mode", choices=["fix", "ut", "sp", "oracle"], required=True)
    parser.add_argument("--iterations", type=int, default=120)
    parser.add_argument("--per-iteration", type=int, default=600)
    parser.add_argument("--buffer", type=int, default=6000)
    parser.add_argument("--steps", type=int, default=150, help="optimizer steps per iteration")
    parser.add_argument("--batch", type=int, default=32)
    parser.add_argument("--sigma0", type=float, default=0.5)
    parser.add_argument("--decay", type=float, default=0.98)
    parser.add_argument("--lambda-anatomy", type=float, default=0.1)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--workers", type=int, default=None, help="synthesis processes (default: all CPUs)")
    parser.add_argument("--synth-crop", type=int, default=None,
                        help="synthesize only a random segment of this many frames per utterance (training uses "
                             f"{CROP}-frame crops, so long real utterances need not be synthesized whole)")
    parser.add_argument("--resume", action="store_true", help="continue from RUN_DIR/checkpoint.pt")
    parser.add_argument("--speaker", type=Path, default=None,
                        help="VTL speaker file to synthesize with (default: the corpus/vtl.py default); "
                             "its anatomy is the FIX-AM reference")
    parser.add_argument("--glottis-model", default=None, help="glottis model to select in --speaker")
    parser.add_argument("--max-memory-gb", type=float, default=10.0,
                        help="stop (resumable) if the run and its workers exceed this resident memory; 0 disables")
    args = parser.parse_args()
    args.run.mkdir(parents=True, exist_ok=True)
    start_memory_guard(args.max_memory_gb)
    (args.run / "args.json").write_text(json.dumps({k: str(v) for k, v in vars(args).items()}, indent=1))

    meta = json.loads((args.data / "meta.json").read_text())
    if args.speaker and not meta.get("real", False):
        raise SystemExit("--speaker only applies to real corpora (a synthetic corpus fixes its speaker)")
    meta = use_run_speaker(args.run, meta, args.speaker, args.glottis_model)
    norm = Normalizer(meta)
    if args.mode == "oracle" and meta.get("real", False):
        raise SystemExit("--mode oracle needs a synthetic corpus")
    start_it = 0
    if args.resume and (args.run / "checkpoint.pt").exists():
        start_it = len((args.run / "log.jsonl").read_text().splitlines())
    rng = np.random.default_rng(args.seed + start_it)
    torch.manual_seed(args.seed + start_it)
    device = pick_device()

    corpus = load_corpus(args.data, norm)
    train = [c for c in corpus if not c["test"]]
    if start_it and (args.run / "mel_stats.npz").exists():
        # A resumed model must keep the normalization it was trained with.
        stats = np.load(args.run / "mel_stats.npz")
        mel_stats = (stats["mean"], stats["std"])
    else:
        # Accumulated per utterance so that the corpus is not copied into one array.
        total = sum(len(c["mel"]) for c in train)
        mean = sum(c["mel"].astype(np.float64).sum(0) for c in train) / total
        var = sum(((c["mel"].astype(np.float64) - mean) ** 2).sum(0) for c in train) / total
        mel_stats = (mean.astype(np.float32), np.sqrt(var).astype(np.float32) + 1e-5)
        np.savez(args.run / "mel_stats.npz", mean=mel_stats[0], std=mel_stats[1])
    print(f"corpus: {len(train)} train / {len(corpus) - len(train)} test utterances", flush=True)

    with_anatomy = args.mode != "fix"
    reference = norm.anatomy(np.array(meta["anatomy_reference"]))
    model = Inference(with_anatomy).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=5e-4, betas=(0.5, 0.999))
    if start_it:
        checkpoint = torch.load(args.run / "checkpoint.pt", map_location=device)
        model.load_state_dict(checkpoint["model"])
        optimizer.load_state_dict(checkpoint["optimizer"])
        # Drop log lines written after the checkpoint.
        start_it = checkpoint["iteration"] + 1
        lines = (args.run / "log.jsonl").read_text().splitlines()[:start_it]
        (args.run / "log.jsonl").write_text("".join(l + "\n" for l in lines))
        print(f"resuming at iteration {start_it}", flush=True)
    pool = Pool(args.workers)
    buffer = []
    log = open(args.run / "log.jsonl", "a")

    if args.mode == "oracle":
        buffer = [(((c["mel"] - mel_stats[0]) / mel_stats[1]).astype(np.float32), c["true_frames"], c["true_anatomy"])
                  for c in train]

    for it in range(start_it, args.iterations):
        t0 = time.time()
        sigma = args.sigma0 * args.decay ** it
        t_synth, new = 0.0, 0
        rejected = {"nan": 0, "clip": 0}
        if args.mode == "oracle":
            chosen = []
        else:
            chosen = [train[i] for i in rng.choice(len(train), min(args.per_iteration, len(train)), replace=False)]
            frames_hat, anatomy_hat = infer(model, [c["mel"] for c in chosen], device, mel_stats)

            # Anatomy for each utterance (normalized).
            if args.mode == "fix":
                anatomy_u = [reference.copy() for _ in chosen]
            elif args.mode == "ut":
                anatomy_u = [np.clip(a + sigma * rng.standard_normal(N_ANATOMY), -1, 1) for a in anatomy_hat]
            else:
                per_speaker = {}
                for c, a in zip(chosen, anatomy_hat):
                    per_speaker.setdefault(c["speaker"], []).append(a)
                drawn = {s: np.clip(np.mean(v, 0) + sigma * rng.standard_normal(N_ANATOMY), -1, 1)
                         for s, v in per_speaker.items()}
                anatomy_u = [drawn[c["speaker"]] for c in chosen]

            if args.synth_crop:
                starts = [rng.integers(0, max(1, len(f) - args.synth_crop + 1)) for f in frames_hat]
                frames_hat = [f[t:t + args.synth_crop] for f, t in zip(frames_hat, starts)]
            frames_u = [np.clip(f + smooth_noise(rng, len(f), N_FRAME, sigma), -1, 1) for f in frames_hat]
            anatomy_abs = [norm.anatomy_inv(a) for a in anatomy_u]
            ranges = pool.ranges(anatomy_abs)
            jobs = []
            for a, f, (lo, hi) in zip(anatomy_abs, frames_u, ranges):
                tract, glottis = norm.frames_inv(f, lo, hi)
                jobs.append((a, tract, glottis))
            audio = pool.render(jobs)
            t_synth = time.time() - t0

            new = 0
            for a_n, f, wav in zip(anatomy_u, frames_u, audio):
                if wav is None or not np.all(np.isfinite(wav)):
                    rejected["nan"] += 1
                    continue
                # Real corpora rescale every synthesis to the corpus level, so only synthetic data needs the
                # [-1, 1] range of the stored int16-like audio.
                if not meta.get("real", False) and np.max(np.abs(wav)) >= 1.0:
                    rejected["clip"] += 1
                    continue
                mel = (log_mel(match_level(wav, meta, rng), len(f)) - mel_stats[0]) / mel_stats[1]
                buffer.append((mel.astype(np.float16), f.astype(np.float32), a_n.astype(np.float32)))
                new += 1
            buffer = buffer[-args.buffer:]

        model.train()
        losses = []
        step = 0
        while step < args.steps:
            for mel, target, anatomy, lengths in batches(buffer, args.batch, rng):
                mel, target, anatomy, lengths = mel.to(device), target.to(device), anatomy.to(device), lengths.to(device)
                frames, anatomy_pred = model(mel, lengths)
                mask = (torch.arange(mel.shape[1], device=device)[None] < lengths[:, None]).float()[..., None]
                loss_frames = ((frames - target) ** 2 * mask).sum() / (mask.sum() * N_FRAME)
                loss = loss_frames
                loss_anatomy = torch.tensor(0.0)
                if with_anatomy:
                    loss_anatomy = ((anatomy_pred - anatomy) ** 2).mean()
                    loss = loss + args.lambda_anatomy * loss_anatomy
                optimizer.zero_grad()
                loss.backward()
                nn.utils.clip_grad_norm_(model.parameters(), 20.0)
                optimizer.step()
                losses.append((loss_frames.item(), loss_anatomy.item()))
                step += 1
                if step >= args.steps:
                    break

        record = {"iteration": it, "sigma": sigma, "new": new, "rejected": rejected, "buffer": len(buffer),
                  "loss_frames": float(np.mean([l[0] for l in losses])),
                  "loss_anatomy": float(np.mean([l[1] for l in losses])),
                  "synth_s": t_synth, "total_s": time.time() - t0}
        log.write(json.dumps(record) + "\n"); log.flush()
        print(json.dumps(record), flush=True)
        if (it + 1) % 5 == 0 or it == args.iterations - 1:
            torch.save(model.state_dict(), args.run / "model.pt")
            torch.save({"model": model.state_dict(), "optimizer": optimizer.state_dict(), "iteration": it},
                       args.run / "checkpoint.pt")

    pool.close()


if __name__ == "__main__":
    main()
