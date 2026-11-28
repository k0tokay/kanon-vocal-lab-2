"""The operations themselves. Importing this module registers them.

- `tract.set_param`: one parameter of a vocal tract shape;
- `glottis.set_param`: one control parameter of a glottis shape;
- `glottis.set_static`: one static parameter of a glottis model;
- `glottis.select_model`: which glottis model VTL uses;
- `tract.add_shape`, `.duplicate_shape`, `.rename_shape`, `.delete_shape`, and the
  same for `glottis.`: whole shapes;
- `status.set`: the status mark of a shape or glottis model;
- `gesture.*`: the gestures of a gestural score (see the section at the end).

Values are clamped to the parameter's range in the speaker file, as VTL does.
"""

from __future__ import annotations

from . import xmltree
from .ops import Context, operator


def _clamp(v: float, lo: float, hi: float) -> float:
    return min(max(float(v), lo), hi)


@operator("tract.set_param", "Set vocal tract parameter")
def tract_set_param(ctx: Context, speaker: str, shape: str, param: str, value: float) -> float:
    """Set one parameter (e.g. "TCX") of the vocal tract shape `shape`. Returns the stored value."""
    sp = ctx.speaker(speaker)
    info = next((p for p in sp.tract_params if p.name == param), None)
    if info is None:
        raise KeyError(f"no vocal tract parameter {param!r}")
    if shape not in sp.tract_shapes:
        raise KeyError(f"no vocal tract shape {shape!r}")
    return ctx.set(speaker, ("tract_shape", shape, param), _clamp(value, info.min, info.max))


@operator("glottis.set_param", "Set glottis parameter")
def glottis_set_param(ctx: Context, speaker: str, shape: str, param: str | int, value: float,
                      model: str | None = None) -> float:
    """Set one control parameter (abbreviation such as "f0", or index) of the glottis shape
    `shape` of `model` (default: the selected glottis model). Returns the stored value."""
    sp = ctx.speaker(speaker)
    m = sp.glottis_models[model] if model else sp.selected_glottis
    if shape not in m.shapes:
        raise KeyError(f"{m.type}: no glottis shape {shape!r}")
    info = m.control[m.control_index(param)]
    return ctx.set(speaker, ("glottis_shape", m.type, shape, info.index),
                   _clamp(value, info.min, info.max))


@operator("glottis.set_static", "Set glottis static parameter")
def glottis_set_static(ctx: Context, speaker: str, param: str | int, value: float,
                       model: str | None = None) -> float:
    """Set one static parameter (abbreviation such as "rest_length", or index) of `model`
    (default: the selected glottis model). Returns the stored value."""
    sp = ctx.speaker(speaker)
    m = sp.glottis_models[model] if model else sp.selected_glottis
    info = m.static_param(param)
    lo, hi = (info.min, info.max) if info.min < info.max else (-float("inf"), float("inf"))
    return ctx.set(speaker, ("glottis_static", m.type, info.abbr), _clamp(value, lo, hi))


@operator("glottis.select_model", "Select glottis model")
def glottis_select_model(ctx: Context, speaker: str, model: str) -> str:
    """Make `model` the glottis model VTL uses for this speaker."""
    sp = ctx.speaker(speaker)
    if model not in sp.glottis_models:
        raise KeyError(f"no glottis model {model!r}")
    return ctx.set(speaker, ("glottis_selected",), model)


# ---------------------------------------------------------------------------
# Whole shapes: add, duplicate, rename, delete. A shape is one `*_def` value
# (see `speaker`), so each of these is one undo step that gives the file back
# byte for byte. Its status mark moves with a rename and goes with a delete.

NAME_MAX = 64


def _check_name(name: str, taken) -> str:
    if not isinstance(name, str) or name != name.strip() or not name:
        raise ValueError(f"a shape name must not be empty or start or end with space: {name!r}")
    if len(name) > NAME_MAX or any(ord(ch) < 32 for ch in name):
        raise ValueError(f"not a usable shape name: {name!r}")
    if name in taken:
        raise ValueError(f"a shape named {name!r} already exists")
    return name


# (def address, status address, existing shapes) of the shape `name`
def _tract(sp, name):
    return ("tract_shape_def", name), ("status", "tract_shape", name), sp.tract_shapes


def _glottis(sp, model, name):
    m = sp.glottis_models[model] if model else sp.selected_glottis
    return ("glottis_shape_def", m.type, name), ("status", "glottis_shape", m.type, name), m.shapes


def _add(ctx, speaker, addr, text):
    sp = ctx.speaker(speaker)
    pos = len(list(sp._shapes_parent(addr)[0].elements("shape")))
    return ctx.set(speaker, addr, (pos, text))


def _rename(ctx, speaker, d_old, s_old, d_new, s_new):
    sp = ctx.speaker(speaker)
    pos, text = sp.get(d_old)
    level = sp.get(s_old)
    ctx.set(speaker, d_old, None)
    ctx.set(speaker, d_new, (pos, _renamed(text, d_new[-1])))
    if level != "todo":
        ctx.set(speaker, s_old, "todo")
        ctx.set(speaker, s_new, level)


def _renamed(text: str, name: str) -> str:
    k = text.find("<")
    e = xmltree.parse(text[k:]).root
    e.set("name", name)
    out: list[str] = []
    e.write(out)
    return text[:k] + "".join(out)


def _delete(ctx, speaker, d, s, names):
    if len(names) <= 1:
        raise ValueError("the last shape cannot be deleted")
    if ctx.get(speaker, s) != "todo":
        ctx.set(speaker, s, "todo")
    ctx.set(speaker, d, None)


@operator("tract.add_shape", "Add vocal tract shape")
def tract_add_shape(ctx: Context, speaker: str, name: str) -> str:
    """Add the vocal tract shape `name` with every parameter at its neutral value."""
    sp = ctx.speaker(speaker)
    d, _, names = _tract(sp, name)
    _check_name(name, names)
    _add(ctx, speaker, d, sp.new_shape_text(d, {p.name: p.neutral for p in sp.tract_params}))
    return name


@operator("tract.duplicate_shape", "Duplicate vocal tract shape")
def tract_duplicate_shape(ctx: Context, speaker: str, shape: str, name: str) -> str:
    """Add the vocal tract shape `name` as a copy of `shape`."""
    sp = ctx.speaker(speaker)
    d, _, names = _tract(sp, name)
    if shape not in names:
        raise KeyError(f"no vocal tract shape {shape!r}")
    _check_name(name, names)
    _add(ctx, speaker, d, sp.new_shape_text(d, like=shape))
    return name


@operator("tract.rename_shape", "Rename vocal tract shape")
def tract_rename_shape(ctx: Context, speaker: str, shape: str, name: str) -> str:
    """Rename the vocal tract shape `shape` to `name` (it keeps its place in the file)."""
    sp = ctx.speaker(speaker)
    d_old, s_old, names = _tract(sp, shape)
    if shape not in names:
        raise KeyError(f"no vocal tract shape {shape!r}")
    _check_name(name, names)
    d_new, s_new, _ = _tract(sp, name)
    _rename(ctx, speaker, d_old, s_old, d_new, s_new)
    return name


@operator("tract.delete_shape", "Delete vocal tract shape")
def tract_delete_shape(ctx: Context, speaker: str, shape: str) -> None:
    """Delete the vocal tract shape `shape`."""
    sp = ctx.speaker(speaker)
    d, s, names = _tract(sp, shape)
    if shape not in names:
        raise KeyError(f"no vocal tract shape {shape!r}")
    _delete(ctx, speaker, d, s, names)


@operator("glottis.add_shape", "Add glottis shape")
def glottis_add_shape(ctx: Context, speaker: str, name: str, model: str | None = None) -> str:
    """Add the glottis shape `name` to `model` (default: the selected one), every control
    parameter at its default value."""
    sp = ctx.speaker(speaker)
    d, _, names = _glottis(sp, model, name)
    _check_name(name, names)
    m = sp.glottis_models[d[1]]
    _add(ctx, speaker, d, sp.new_shape_text(d, {p.index: p.default for p in m.control}))
    return name


@operator("glottis.duplicate_shape", "Duplicate glottis shape")
def glottis_duplicate_shape(ctx: Context, speaker: str, shape: str, name: str,
                            model: str | None = None) -> str:
    """Add the glottis shape `name` to `model` as a copy of `shape`."""
    sp = ctx.speaker(speaker)
    d, _, names = _glottis(sp, model, name)
    if shape not in names:
        raise KeyError(f"{d[1]}: no glottis shape {shape!r}")
    _check_name(name, names)
    _add(ctx, speaker, d, sp.new_shape_text(d, like=shape))
    return name


@operator("glottis.rename_shape", "Rename glottis shape")
def glottis_rename_shape(ctx: Context, speaker: str, shape: str, name: str,
                         model: str | None = None) -> str:
    """Rename the glottis shape `shape` of `model` to `name`."""
    sp = ctx.speaker(speaker)
    d_old, s_old, names = _glottis(sp, model, shape)
    if shape not in names:
        raise KeyError(f"{d_old[1]}: no glottis shape {shape!r}")
    _check_name(name, names)
    d_new, s_new, _ = _glottis(sp, d_old[1], name)
    _rename(ctx, speaker, d_old, s_old, d_new, s_new)
    return name


@operator("glottis.delete_shape", "Delete glottis shape")
def glottis_delete_shape(ctx: Context, speaker: str, shape: str, model: str | None = None) -> None:
    """Delete the glottis shape `shape` of `model`."""
    sp = ctx.speaker(speaker)
    d, s, names = _glottis(sp, model, shape)
    if shape not in names:
        raise KeyError(f"{d[1]}: no glottis shape {shape!r}")
    _delete(ctx, speaker, d, s, names)


# ---------------------------------------------------------------------------
# How far a shape or a glottis model is worked out (未整備 / 調整中 / 整備済み).
# Set by hand; kept in `.meta.json`, so the `.speaker` stays as VTL reads it.


@operator("status.set", "Set status")
def status_set(ctx: Context, speaker: str, what: list, level: str) -> str:
    """Set the status of `what`: ["tract_shape", shape], ["glottis_shape", model, shape] or
    ["glottis_model", model]. `level`: "todo", "wip" or "done"."""
    sp = ctx.speaker(speaker)
    what = tuple(what)
    kind = what[0] if what else None
    if kind == "tract_shape" and len(what) == 2:
        ok = what[1] in sp.tract_shapes
    elif kind == "glottis_shape" and len(what) == 3:
        ok = what[1] in sp.glottis_models and what[2] in sp.glottis_models[what[1]].shapes
    elif kind == "glottis_model" and len(what) == 2:
        ok = what[1] in sp.glottis_models
    else:
        raise ValueError(f"not something with a status: {list(what)}")
    if not ok:
        raise KeyError(f"no such {kind}: {list(what[1:])}")
    return ctx.set(speaker, ("status",) + what, level)


# ---------------------------------------------------------------------------
# Gestural scores. Every operation sets whole sequences (see `score`).
#
# - `gesture.set`: value, slope, duration, time constant or neutral of one gesture;
# - `gesture.set_boundary`: move the end of a gesture (the next one gives or takes
#   the time, so nothing after them moves); a drag is one undo step;
# - `gesture.split`: cut the gesture under a time in two;
# - `gesture.delete`: remove a gesture; the one before it (or after it, for the
#   first) takes its time, so the other gestures keep their times;
# - `gesture.add`: a new gesture at a time, cut out of the gesture there.

from .score import DEFAULT_TAU, MIN_DURATION, SEQUENCE, quantize, starts  # noqa: E402


def _sequence(ctx: Context, score: str, sequence: str) -> list:
    sc = ctx.score(score)
    if sequence not in SEQUENCE:
        raise KeyError(f"no gesture sequence {sequence!r}")
    return [list(g) for g in sc.sequences[sequence]]


def _index(gs: list, index: int) -> int:
    i = int(index)
    if not 0 <= i < len(gs):
        raise IndexError(f"no gesture {index} (the sequence has {len(gs)})")
    return i


def _rest(info, gs: list) -> str:
    """A number value for a gesture with nothing to copy: the middle of the range."""
    return str(0.5 * (info.min + info.max))


def _at(gs: list, t: float) -> int:
    """The gesture under time `t` (the last one when `t` is at or after the end)."""
    st = starts(gs)
    for i in range(len(gs) - 1, -1, -1):
        if t >= st[i]:
            return i
    return 0


@operator("gesture.set", "Set gesture")
def gesture_set(ctx: Context, score: str, sequence: str, index: int, value=None, slope=None,
                duration=None, time_constant=None, neutral=None) -> list:
    """Set fields of gesture `index` of `sequence` (only those given). Values outside
    VTL's ranges are clamped. Returns the gesture as stored."""
    gs = _sequence(ctx, score, sequence)
    i = _index(gs, index)
    g = gs[i]
    for k, v in ((0, value), (1, slope), (2, duration), (3, time_constant), (4, neutral)):
        if v is not None:
            g[k] = v
    out = ctx.set(score, ("sequence", sequence), gs)
    return list(out[i])


@operator("gesture.set_boundary", "Move gesture boundary")
def gesture_set_boundary(ctx: Context, score: str, sequence: str, index: int, time: float) -> float:
    """Move the end of gesture `index` to `time` (s). The next gesture starts there too,
    so the gestures after it keep their times; the last gesture just gets longer or
    shorter. Each keeps at least 1 ms. Returns the boundary as stored."""
    gs = _sequence(ctx, score, sequence)
    i = _index(gs, index)
    st = starts(gs)
    lo = st[i] + MIN_DURATION
    if i + 1 < len(gs):
        hi = st[i + 1] + gs[i + 1][2] - MIN_DURATION
        end_next = st[i + 1] + gs[i + 1][2]
        t = quantize(_clamp(time, lo, hi))
        gs[i][2] = t - st[i]
        gs[i + 1][2] = end_next - t
    else:
        t = quantize(max(float(time), lo))
        gs[i][2] = t - st[i]
    ctx.set(score, ("sequence", sequence), gs)
    return t


@operator("gesture.split", "Split gesture")
def gesture_split(ctx: Context, score: str, sequence: str, time: float) -> int:
    """Cut the gesture under `time` in two equal-valued gestures. Returns the index
    of the second one."""
    gs = _sequence(ctx, score, sequence)
    t = float(time)
    i = _at(gs, t)
    st = starts(gs)
    left = quantize(t - st[i])
    right = gs[i][2] - left
    if left < MIN_DURATION or right < MIN_DURATION:
        raise ValueError("the time is not inside a gesture")
    second = list(gs[i])
    gs[i][2], second[2] = left, right
    gs.insert(i + 1, second)
    ctx.set(score, ("sequence", sequence), gs)
    return i + 1


@operator("gesture.delete", "Delete gesture")
def gesture_delete(ctx: Context, score: str, sequence: str, index: int) -> None:
    """Remove gesture `index`. Its time goes to the gesture before it (or after it,
    for the first), so no other gesture moves. The last gesture of a sequence stays."""
    gs = _sequence(ctx, score, sequence)
    i = _index(gs, index)
    if len(gs) == 1:
        raise ValueError("a sequence keeps at least one gesture")
    j = i - 1 if i > 0 else 1
    gs[j][2] += gs[i][2]
    del gs[i]
    ctx.set(score, ("sequence", sequence), gs)


@operator("gesture.add", "Add gesture")
def gesture_add(ctx: Context, score: str, sequence: str, time: float, duration: float = 0.1,
                value=None) -> int:
    """A new gesture from `time` for `duration` s, taken out of the gesture there (which
    is cut; what is left of it after the new one stays). At or after the end of the
    sequence it is appended. The new gesture is neutral for shape sequences unless
    `value` is given, and has the value of the gesture it cuts for number sequences.
    Returns its index."""
    gs = _sequence(ctx, score, sequence)
    info = SEQUENCE[sequence]
    t, d = float(time), max(float(duration), MIN_DURATION)
    end = sum(g[2] for g in gs)
    if t >= end - MIN_DURATION:  # after the end (or an empty sequence): a pause, then the gesture
        if t - end >= MIN_DURATION:
            gs.append(["" if info.nominal else _rest(info, gs), 0.0, t - end, DEFAULT_TAU, True])
        base_value = gs[-1][0] if gs else _rest(info, gs)
        new = [value if value is not None else ("" if info.nominal else base_value),
               0.0, d, DEFAULT_TAU, value is None and info.nominal]
        gs.append(new)
        ctx.set(score, ("sequence", sequence), gs)
        return len(gs) - 1
    i = _at(gs, t)
    st = starts(gs)
    g = gs[i]
    left = quantize(t - st[i])
    rest = st[i] + g[2] - t
    d = min(d, rest)
    new = [value if value is not None else ("" if info.nominal else g[0]),
           0.0, d, g[3], value is None and info.nominal]
    out = []
    if left >= MIN_DURATION:
        out.append([*g[:2], left, *g[3:]])
    out.append(new)
    if rest - d >= MIN_DURATION:
        out.append([*g[:2], rest - d, *g[3:]])
    else:
        new[2] = rest
    gs[i:i + 1] = out
    ctx.set(score, ("sequence", sequence), gs)
    return i + (1 if left >= MIN_DURATION else 0)

