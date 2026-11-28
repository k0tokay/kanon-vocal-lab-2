"""The operations themselves. Importing this module registers them.

- `tract.set_param`: one parameter of a vocal tract shape;
- `glottis.set_param`: one control parameter of a glottis shape;
- `glottis.set_static`: one static parameter of a glottis model;
- `glottis.select_model`: which glottis model VTL uses;
- `tract.add_shape`, `.duplicate_shape`, `.rename_shape`, `.delete_shape`, and the
  same for `glottis.`: whole shapes;
- `status.set`: the status mark of a shape or glottis model.

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
