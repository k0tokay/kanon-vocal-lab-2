"""Which part of a human prosody makes the copy more natural: pauses (P), timing (T) or F0 (F)?

Every condition is VTL only. A letter in the condition name = taken from the JVS recording
(through the copy of copysynth.py), otherwise from the rules:
  P  where the pauses are and how long
  T  durations of the single segments; the rule durations are scaled to the same speech time,
     so the speaking rate is the recording's in every condition
  F  F0 at 3 points per segment; the rule F0 is shifted to the recording's mean in every condition
  R  rule F0, also scaled to the recording's F0 range
"rule" is accent.py as it is (its own rate and register).

The copies are made again here with the pauses pinned to the forced alignment (ALIGN); sentence 012
is left out because all alignments put the pause inside "hagane", so the recordings may read it otherwise.

    KANON=v1-1-3 VTL_LIB=... ALIGN=<align.pkl> python factor.py jvs064 jvs053 jvs015
"""
import contextlib
import io
import json
import pickle
import sys
from concurrent.futures import ProcessPoolExecutor
from copy import deepcopy

from copysynth import *

OUT = OUT / "factor"
AUDIO = OUT / "copy"
UTT = [u for u in SENTENCES if u != "012"]
CONDS = ["none", "P", "T", "F", "R", "PT", "PF", "TF", "PTF"]
VOICED = set("aieouMmnNv4jbdgz") | {"z\\", "dz\\", "u"}
pause = lambda s: s.name == ""


def rule_parts(text):
    """Rule segments without their pauses, and the pauses as {index of the next segment: seconds}."""
    units = accent.parse(text)
    segs, spans = accent.to_segments(units)
    ph, ac = accent.commands(units, spans, accent.Fujisaki())
    for s in segs:
        s.f0 = list(accent.f0_curve(np.array([s.t0 + r * s.duration for r in (.2, .5, .8)]), ph, ac, accent.Fujisaki()))
    core, pauses = [], {}
    for s in segs:
        if pause(s):
            pauses[len(core)] = pauses.get(len(core), 0) + s.duration
        else:
            core.append(s)
    return core, pauses


def copy_parts(text, seg_file):
    """The copy's segments (tags from the rules), durations and F0 from its seg file."""
    units = [u for u in accent.parse(text) if not (isinstance(u, accent.Pause) and u.kind == "pau")]
    tagged = [s for s in accent.to_segments(units)[0] if not pause(s)]
    core, pauses = [], {}
    for l in seg_file.read_text().splitlines():
        d = dict(q.strip().split(" = ") for q in l.replace("name = ;", "name = _;").strip().rstrip(";").split(";"))
        if d["name"] == "_":
            pauses[len(core)] = pauses.get(len(core), 0) + float(d["duration_s"])
        else:
            s = deepcopy(tagged[len(core)]); assert s.name == d["name"], (s.name, d["name"])
            s.duration = float(d["duration_s"]); s.f0 = [float(d[f"f0_{p}%_Hz"]) for p in (20, 50, 80)]
            core.append(s)
    assert len(core) == len(tagged)
    return core, pauses


def logf0(core):
    """Duration-weighted mean and SD of log F0 over the voiced segments."""
    v = [s for s in core if s.name in VOICED and s.tag != "devoiced"]
    x = np.log([s.f0 for s in v]); w = np.array([s.duration for s in v])[:, None] * np.ones(3)
    m = (x * w).sum() / w.sum()
    return m, np.sqrt(((x - m) ** 2 * w).sum() / w.sum())


def compose(cond, rule_, copy_):
    (rs, rp), (cs, cp) = rule_, copy_
    assert len(rs) == len(cs)
    k = sum(s.duration for s in cs) / sum(s.duration for s in rs)
    (mr, sr), (mc, sc) = logf0(rs), logf0(cs)
    g = sc / sr if "R" in cond else 1.0
    P = cp if "P" in cond else {i: v * k if 0 < i < len(rs) else cp.get(i, .1) for i, v in rp.items()}
    out, t = [], 0.0
    for i in range(len(cs) + 1):
        if i in P or i in (0, len(cs)):
            d = P.get(i, .12)
            d = max(d, .12) if i == 0 else d
            out.append(accent.Segment("", d, t)); t += d
        if i == len(cs):
            break
        a, b = rs[i], cs[i]
        s = deepcopy(b if "P" in cond else a)       # [ʑ] after a vowel, [dʑ] after a pause
        s.t0, s.duration = t, b.duration if "T" in cond else a.duration * k
        s.f0 = list(b.f0) if "F" in cond else [float(np.exp(mc + g * (np.log(f) - mr))) for f in a.f0]
        out.append(s); t += s.duration
    return out


def pause_index(text, spans):
    """Segment index of every pause of at least .1 s of a forced alignment (phones of align.py)."""
    units = [u for u in accent.parse(text) if not (isinstance(u, accent.Pause) and u.kind == "pau")]
    segs, times = accent.to_segments(units)
    ends = np.round([s.t0 + s.duration for s in segs if not pause(s)], 6)
    # number of phones up to the end of each mora -> index of the next segment
    after, n = {}, 0
    for u, (_, t1) in zip(units, times):
        if isinstance(u, accent.Mora):
            n += 2 if u.consonant else 1
            after[n] = int(np.searchsorted(ends, t1 - 1e-5)) + 1
    out, n = [], 0
    for name, a, b in spans:
        if name != "sil":
            n += 1
        elif b - a >= .1 and 0 < n < max(after):
            out.append(after[n])
    return out


def make_copy(a):
    spk, u = a
    real = load_jvs(spk, [u])[u]
    al = pickle.load(open(os.environ["ALIGN"], "rb"))["align"][spk, u]
    cuts = pause_index(SENTENCES[u], al)
    _, _, score = copy(SENTENCES[u], AUDIO / spk / u, real, analyse(real), rounds=4, cuts=cuts)
    return a, cuts, round(float(score), 3)


def job(a):
    spk, u, cond = a
    text = SENTENCES[u]; stem = OUT / f"{spk}-{u}-{cond}"
    segs = compose(cond, rule_parts(text), copy_parts(text, AUDIO / f"{spk}/{u}.seg"))
    accent.write_seg(segs, stem.with_suffix(".seg"))
    with contextlib.redirect_stdout(io.StringIO()):
        accent.synthesize(stem.with_suffix(".seg"), stem.with_suffix(".wav"), segs)
    x = read_wav(stem.with_suffix(".wav")); f = analyse(x)["f0"]
    core = [s for s in segs if not pause(s)]
    want = np.zeros(len(f))                 # requested F0 at the segment middles, against the measured one
    err = []
    for s in core:
        q = int((s.t0 + .5 * s.duration) / .005)
        if s.name in "aieouM" and q < len(f) and f[q] > 0 and s.tag != "devoiced":
            err.append(1200 * abs(np.log2(f[q] / s.f0[1])))
    v = f[f > 0]
    return a, dict(total_s=round(len(x) / RS, 3), speech_s=round(sum(s.duration for s in core), 3),
                   pauses=sum(pause(s) for s in segs) - 2, pause_s=round(sum(s.duration for s in segs[1:-1] if pause(s)), 3),
                   f0_median=round(float(np.median(v)), 1), f0_sd_st=round(float(np.std(12 * np.log2(v / 100))), 2),
                   f0_err_cent=round(float(np.median(err)), 1))


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    jobs = [(s, u, c) for s in sys.argv[1:] for u in UTT for c in CONDS]
    with ProcessPoolExecutor(8) as ex:
        for r in ex.map(make_copy, [(s, u) for s in sys.argv[1:] for u in UTT]):
            print(*r, flush=True)
        res = list(ex.map(job, jobs))
    info = {"-".join(a): r for a, r in res}
    (OUT / "info.json").write_text(json.dumps(info, indent=1))
    for c in CONDS:
        r = [v for (s, u, q), v in res if q == c]
        print(f"{c:5s}", {k: round(float(np.mean([x[k] for x in r])), 2) for k in r[0]})
