"""The operations themselves. Importing this module registers them.

- `tract.set_param`: one parameter of a vocal tract shape;
- `glottis.set_param`: one control parameter of a glottis shape;
- `glottis.set_static`: one static parameter of a glottis model;
- `glottis.select_model`: which glottis model VTL uses.

Values are clamped to the parameter's range in the speaker file, as VTL does.
"""

from __future__ import annotations

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
