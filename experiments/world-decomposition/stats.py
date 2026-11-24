"""WORLD statistics of Kanon (rule prosody / copied prosody) against all JVS women."""
import json
from concurrent.futures import ProcessPoolExecutor

from common import *
from copysynth import read_wav

SPK = ["jvs064", "jvs053", "jvs015"]


def runs(mask, min_len):
    e = np.flatnonzero(np.diff(np.r_[0, mask.astype(int), 0])).reshape(-1, 2)
    return [(a, b) for a, b in e if b - a >= min_len]


def modspec(tracks, fs=200, n=64):
    """Mean modulation power (per Hz) of the runs in tracks (linear detrend, Hann)."""
    w = np.hanning(n); acc = []
    for x in tracks:
        for s in range(0, len(x) - n + 1, n // 2):
            y = x[s:s + n]; k = np.arange(n); y = y - np.polyval(np.polyfit(k, y, 1), k)
            acc.append(np.abs(np.fft.rfft(y * w)) ** 2 / (fs * (w ** 2).sum()))
    return np.mean(acc, 0) if acc else np.full(n // 2 + 1, np.nan)


def collect(signals):
    """One dict of scalars and curves over a list of utterances of one voice."""
    P = [analyse(x) for x in signals]
    G = dict(f0run=[], f0slow=[], c0=[], mc=[], mel=[], mc_v=[], ap3=[], ap6=[], apm=[], uv=[], sil=[], gap=[], vf=[])
    for p in P:
        m = logmel(p["sp"], 1e-14); e = m.mean(1)
        speech = e > np.quantile(e, .95) - 35
        v = (p["f0"] > 0) & speech
        # Voiced runs, 20 ms trimmed at both ends where F0 and D4C are unreliable.
        R = [(a + 4, b - 4) for a, b in runs(v, 28)]
        for a, b in R:
            c = 1200 * np.log2(p["f0"][a:b] / 100)
            G["f0run"].append(c)
            mc = dct(m[a:b], norm="ortho", axis=1)[:, :13]
            G["c0"].append(m[a:b].mean(1)); G["mc"].append(mc)
            for k, f in (("ap3", 3000), ("ap6", 6000)):
                # Noise-to-harmonic power ratio: unlike the aperiodicity in dB it has no ceiling at 0,
                # so the spread of a breathy voice is not compressed.
                q = np.clip(p["ap"][a:b, round(f * FFT / FS)], 1e-4, .9999) ** 2
                G[k].append(10 * np.log10(q / (1 - q)))
            G["mel"].append(m[a:b])
        uv = (p["f0"] == 0) & speech
        G["uv"].append(m[uv]); G["vf"].append(v.sum() / speech.sum())
        G["sil"].append(np.median(m[~speech].mean(1)) if (~speech).sum() > 20 else np.nan)
    mel = np.vstack(G["mel"]); ltas = 10 * np.log10(np.mean(10 ** (mel / 10), 0)); uv = np.vstack(G["uv"])
    f0 = np.concatenate(G["f0run"]); mc = np.vstack(G["mc"])
    fm = modspec(G["f0run"]); em = modspec(G["c0"])
    am = modspec(G["ap3"]); sm = np.mean([modspec([r[:, k] for r in G["mc"]]) for k in range(1, 13)], 0)
    q = np.arange(33) * 200 / 64
    band = lambda s, lo, hi: float(10 * np.log10(s[(q >= lo) & (q < hi)].mean()))
    ref = ltas[(MEL_F > 200) & (MEL_F < 1000)].mean()
    lv = lambda l, lo, hi: float(10 * np.log10(np.mean(10 ** (l[(MEL_F >= lo) & (MEL_F < hi)] / 10))))
    uvl = 10 * np.log10(np.mean(10 ** (uv / 10), 0)) if len(uv) else np.full(40, np.nan)
    s = {"F0_median_Hz": float(100 * 2 ** (np.median(f0) / 1200)), "F0_sd_semitone": float(f0.std() / 100),
         "F0_mod_3-8Hz": band(fm, 3, 9), "F0_mod_9-25Hz": band(fm, 9, 25), "F0_mod_25-60Hz": band(fm, 25, 60),
         "E_sd_dB": float(np.concatenate(G["c0"]).std()), "E_mod_3-8Hz": band(em, 3, 9), "E_mod_9-25Hz": band(em, 9, 25),
         "E_mod_25-60Hz": band(em, 25, 60),
         "S_1-2k_vs_low": lv(ltas, 1000, 2000) - lv(ltas, 200, 1000), "S_2-4k_vs_low": lv(ltas, 2000, 4000) - lv(ltas, 200, 1000),
         "S_4-7.5k_vs_low": lv(ltas, 4000, 7600) - lv(ltas, 200, 1000),
         "D_GV_c1-4": float(mc[:, 1:5].var(0).mean() ** .5), "D_GV_c5-12": float(mc[:, 5:13].var(0).mean() ** .5),
         "D_mod_3-8Hz": band(sm, 3, 9), "D_mod_9-25Hz": band(sm, 9, 25), "D_mod_25-60Hz": band(sm, 25, 60),
         "AP_3k_dB": float(np.mean(np.concatenate(G["ap3"]))), "AP_6k_dB": float(np.mean(np.concatenate(G["ap6"]))),
         "AP_3k_sd": float(np.std(np.concatenate(G["ap3"]))), "AP_6k_sd": float(np.std(np.concatenate(G["ap6"]))),
         "AP_energy_corr": float(np.corrcoef(np.concatenate(G["ap3"]), np.concatenate(G["c0"]))[0, 1]),
         "AP_mod_3-25Hz": band(am, 3, 25), "AP_mod_25-60Hz": band(am, 25, 60),
         "UV_4-7.5k_vs_voicedlow": lv(uvl, 4000, 7600) - lv(ltas, 200, 1000), "UV_1-4k_vs_voicedlow": lv(uvl, 1000, 4000) - lv(ltas, 200, 1000),
         "voiced_fraction": float(np.mean(G["vf"])), "silence_vs_voiced_dB": float(np.nanmedian(G["sil"]) - mel.mean())}
    dmel = mel - mel.mean(1, keepdims=True)
    ap_all = np.concatenate(G["ap3"])
    return dict(scalar=s, msd=dmel.std(0).tolist(), nhr_hist=np.histogram(ap_all, np.arange(-40, 22, 2), density=True)[0].tolist(), ltas=(ltas - lv(ltas, 200, 1000)).tolist(), uv=(uvl - lv(ltas, 200, 1000)).tolist(),
                fm=(10 * np.log10(fm)).tolist(), em=(10 * np.log10(em)).tolist(), sm=(10 * np.log10(sm)).tolist(), am=(10 * np.log10(am)).tolist())


def jvs(name):
    return name, collect(list(load_jvs(name, SENTENCES).values()))


if __name__ == "__main__":
    meta = json.loads((JVS / "meta.json").read_text())
    women = [n for n, t in meta["tags"].items() if t.get("gender") == "F"]
    with ProcessPoolExecutor(8) as ex:
        pop = dict(ex.map(jvs, women))
    A = OUT / "audio"
    vtl = {"rule": collect([read_wav(A / f"vtl/{u}.wav") for u in SENTENCES])}
    for s in SPK:
        vtl[f"copy-{s}"] = collect([read_wav(A / f"{s}/{u}.wav") for u in SENTENCES])
    (OUT / "stats.json").write_text(json.dumps(dict(pop=pop, vtl=vtl)))
    keys = list(next(iter(pop.values()))["scalar"])
    table = {}
    print(f"{'':26s}{'JVS mean':>9s}{'sd':>7s}{'[min':>8s}{'max]':>8s}  " + "  ".join(f"{k[-11:]:>11s}" for k in vtl) + "   z(rule) z(copy)")
    for k in keys:
        x = np.array([p["scalar"][k] for p in pop.values()]); r = [v["scalar"][k] for v in vtl.values()]
        z = lambda a: (a - np.nanmean(x)) / np.nanstd(x)
        table[k] = dict(mean=np.nanmean(x), sd=np.nanstd(x), min=np.nanmin(x), max=np.nanmax(x), rule=r[0], copy=np.mean(r[1:]),
                        z_rule=z(r[0]), z_copy=z(np.mean(r[1:])),
                        z_pairs=float(np.mean([r[1 + i] - pop[s]["scalar"][k] for i, s in enumerate(SPK)])))
        print(f"{k:26s}{np.nanmean(x):9.2f}{np.nanstd(x):7.2f}{np.nanmin(x):8.2f}{np.nanmax(x):8.2f}  " + "  ".join(f"{a:11.2f}" for a in r) + f"   {z(r[0]):6.1f} {z(np.mean(r[1:])):6.1f}")
    (HERE / "results").mkdir(exist_ok=True)
    (HERE / f"results/stats-{VER}.json").write_text(json.dumps({k: {a: round(float(b), 3) for a, b in t.items()} for k, t in table.items()}, indent=1))
