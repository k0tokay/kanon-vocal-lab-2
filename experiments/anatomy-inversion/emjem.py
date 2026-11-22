"""EmJEm training of an articulatory inference network with VTL (Sun, Huang & Wu, Interspeech 2022).

Run from this directory:
  python3 emjem.py DATA_DIR RUN_DIR --mode {fix,ut,sp,oracle} [--iterations 120]

--mode oracle skips EmJEm and trains on the true parameters of the training speakers
(a supervised upper bound for how much of the anatomy the audio reveals).

Each iteration: infer parameters for a subset of the target corpus, perturb them with
Gaussian noise (sigma = 0.5 * 0.98**iteration, temporally smoothed for the frame tracks),
synthesize with VTL, and train the network on the new (mel, parameter) pairs.
The ground-truth parameters of the target corpus are never used for training.
"""
import argparse
import json
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
        yield (torch.from_numpy(pad(mels)), torch.from_numpy(pad(targets)),
               torch.from_numpy(np.stack(anatomies).astype(np.float32)), torch.tensor(lengths))


@torch.no_grad()
def infer(model, mels, device, mel_stats):
    model.eval()
    out_frames, out_anatomy = [], []
    for mel in mels:
        x = torch.from_numpy((mel - mel_stats[0]) / mel_stats[1]).unsqueeze(0).to(device)
        frames, anatomy = model(x, torch.tensor([len(mel)], device=device))
        out_frames.append(frames[0].cpu().numpy())
        out_anatomy.append(None if anatomy is None else anatomy[0].cpu().numpy())
    return out_frames, out_anatomy


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

def load_corpus(data_dir, norm):
    speakers = sorted(data_dir.glob("spk*.npz"))
    n_test = min(TEST_SPEAKERS, max(1, len(speakers) // 4))
    corpus = []
    for s, path in enumerate(speakers):
        d = np.load(path)
        audio_off = np.concatenate([[0], np.cumsum(d["audio_len"])])
        frame_off = np.concatenate([[0], np.cumsum(d["frames"])])
        for u in range(len(d["frames"])):
            n = int(d["frames"][u])
            tract, glottis = d["tract"][frame_off[u]:frame_off[u + 1]], d["glottis"][frame_off[u]:frame_off[u + 1]]
            corpus.append({
                "speaker": s, "test": s >= len(speakers) - n_test,
                "mel": log_mel(d["audio"][audio_off[u]:audio_off[u + 1]], n),
                "true_frames": norm.frames(tract, glottis, d["tract_min"], d["tract_max"]),
                "true_anatomy": norm.anatomy(d["anatomy"]).astype(np.float32)})
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
    args = parser.parse_args()
    args.run.mkdir(parents=True, exist_ok=True)
    (args.run / "args.json").write_text(json.dumps({k: str(v) for k, v in vars(args).items()}, indent=1))

    meta = json.loads((args.data / "meta.json").read_text())
    norm = Normalizer(meta)
    rng = np.random.default_rng(args.seed)
    torch.manual_seed(args.seed)
    device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")

    corpus = load_corpus(args.data, norm)
    train = [c for c in corpus if not c["test"]]
    all_mel = np.concatenate([c["mel"] for c in train])
    mel_stats = (all_mel.mean(0).astype(np.float32), all_mel.std(0).astype(np.float32) + 1e-5)
    np.savez(args.run / "mel_stats.npz", mean=mel_stats[0], std=mel_stats[1])
    print(f"corpus: {len(train)} train / {len(corpus) - len(train)} test utterances", flush=True)

    with_anatomy = args.mode != "fix"
    reference = norm.anatomy(np.array(meta["anatomy_reference"]))
    model = Inference(with_anatomy).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=5e-4, betas=(0.5, 0.999))
    pool = Pool()
    buffer = []
    log = open(args.run / "log.jsonl", "a")

    if args.mode == "oracle":
        buffer = [(((c["mel"] - mel_stats[0]) / mel_stats[1]).astype(np.float32), c["true_frames"], c["true_anatomy"])
                  for c in train]

    for it in range(args.iterations):
        t0 = time.time()
        sigma = args.sigma0 * args.decay ** it
        t_synth, new = 0.0, 0
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
                if wav is None or not np.all(np.isfinite(wav)) or np.max(np.abs(wav)) >= 1.0:
                    continue
                mel = (log_mel(wav, len(f)) - mel_stats[0]) / mel_stats[1]
                buffer.append((mel.astype(np.float32), f.astype(np.float32), a_n.astype(np.float32)))
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

        record = {"iteration": it, "sigma": sigma, "new": new, "buffer": len(buffer),
                  "loss_frames": float(np.mean([l[0] for l in losses])),
                  "loss_anatomy": float(np.mean([l[1] for l in losses])),
                  "synth_s": t_synth, "total_s": time.time() - t0}
        log.write(json.dumps(record) + "\n"); log.flush()
        print(json.dumps(record), flush=True)
        if (it + 1) % 10 == 0 or it == args.iterations - 1:
            torch.save(model.state_dict(), args.run / "model.pt")

    pool.close()


if __name__ == "__main__":
    main()
