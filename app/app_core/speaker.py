"""A VTL speaker (`.speaker`) as a tree.

The `.speaker` file stays the master copy: the tree is a view over the
parsed XML (see `xmltree`), so saving writes back exactly what was read
except for the values that were changed.

Values are addressed by tuples (they become JSON arrays on the wire):

    ("tract_shape", shape, param)              e.g. ("tract_shape", "a", "TCX")
    ("tract_param", param, field)              field: min, max, neutral, ...
    ("glottis_selected",)                      the selected model's type
    ("glottis_static", model, abbr)            e.g. (..., "Triangular body-cover glottis", "rest_f0")
    ("glottis_shape", model, shape, abbr)      e.g. (..., "modal", "f0"); abbr may be the index
    ("anatomy", tag, ..., attribute)           e.g. ("anatomy", "palate", "p3", "x")

`get` returns a float for numbers and a str otherwise. `set` writes a number
with as many decimals as the file used for that value, so the value in the
tree is always the value VTL will read back (`quantize` gives it in advance).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import xmltree
from .xmltree import Element

Address = tuple

GLOTTIS_MODELS = (
    "Geometric glottis 2025",
    "Geometric glottis 2019",
    "Triangular glottis",
    "Triangular body-cover glottis",
)


# ---------------------------------------------------------------------------
# Number formatting


def _decimals(raw: str) -> int | None:
    """Decimals of a fixed-point number as written; None if not fixed-point."""
    s = raw.strip()
    if "e" in s.lower():
        return None
    if "." in s:
        return len(s) - s.index(".") - 1
    return 0


def format_like(raw: str, value: float) -> str:
    """Format `value` the way `raw` was written (same number of decimals)."""
    d = _decimals(raw)
    if d is None:
        return repr(float(value))
    if d == 0 and float(value) != int(value):
        return f"{value:f}"
    return f"{value:.{d}f}"


def quantize_like(raw: str, value: float) -> float:
    return float(format_like(raw, value))


def _number(text: str) -> float | str:
    try:
        return float(text)
    except ValueError:
        return text


# ---------------------------------------------------------------------------
# Views


@dataclass
class ParamInfo:
    index: int
    name: str
    min: float
    max: float
    neutral: float
    element: Element

    def to_json(self) -> dict:
        d = {"index": self.index, "name": self.name, "min": self.min, "max": self.max,
             "neutral": self.neutral}
        for a in self.element.attrs:
            if a.name not in ("index", "name", "min", "max", "neutral"):
                d[a.name] = _number(a.value)
        return d


@dataclass
class GlottisParam:
    index: int
    name: str
    abbr: str
    unit: str
    min: float
    max: float
    default: float
    element: Element

    @property
    def value(self) -> float:
        return float(self.element.get("value"))

    def to_json(self, with_value: bool) -> dict:
        d = {"index": self.index, "name": self.name, "abbr": self.abbr, "unit": self.unit,
             "min": self.min, "max": self.max, "default": self.default}
        if with_value:
            d["value"] = self.value
        return d


class GlottisModel:
    def __init__(self, element: Element):
        self.element = element
        self.type = element.get("type")
        self.static = [self._param(p) for p in element.child("static_params").elements("param")]
        self.control = [self._param(p) for p in element.child("control_params").elements("param")]
        self.shapes: dict[str, dict[int, Element]] = {}
        for s in element.child("shapes").elements("shape"):
            self.shapes[s.get("name")] = {int(c.get("index")): c for c in s.elements("control_param")}

    @staticmethod
    def _param(p: Element) -> GlottisParam:
        return GlottisParam(int(p.get("index")), p.get("name"), p.get("abbr"), p.get("unit", ""),
                            float(p.get("min")), float(p.get("max")), float(p.get("default")), p)

    @property
    def selected(self) -> bool:
        return self.element.get("selected") == "1"

    def control_index(self, key: int | str) -> int:
        if isinstance(key, int):
            return key
        for p in self.control:
            if key in (p.abbr, p.name):
                return p.index
        raise KeyError(f"{self.type}: no control parameter {key!r}")

    def static_param(self, key: int | str) -> GlottisParam:
        for p in self.static:
            if key in (p.index, p.abbr, p.name):
                return p
        raise KeyError(f"{self.type}: no static parameter {key!r}")

    def shape_values(self, name: str) -> list[float]:
        s = self.shapes[name]
        return [float(s[i].get("value")) for i in sorted(s)]

    def to_json(self) -> dict:
        return {
            "type": self.type,
            "selected": self.selected,
            "static": [p.to_json(True) for p in self.static],
            "control": [p.to_json(False) for p in self.control],
            "shapes": {n: self.shape_values(n) for n in self.shapes},
        }


class Speaker:
    """A parsed `.speaker` file."""

    def __init__(self, text: str, path: Path | None = None):
        self.path = path
        self.doc = xmltree.parse(text)
        root = self.doc.root
        if root.tag != "speaker":
            raise xmltree.ParseError(f"root element is <{root.tag}>, not <speaker>")
        vt = root.child("vocal_tract_model")
        self.anatomy = vt.child("anatomy")
        self.tract_params = [
            ParamInfo(int(p.get("index")), p.get("name"), float(p.get("min")), float(p.get("max")),
                      float(p.get("neutral")), p)
            for p in self.anatomy.elements("param")
        ]
        self.tract_shapes: dict[str, dict[str, Element]] = {}
        for s in vt.child("shapes").elements("shape"):
            self.tract_shapes[s.get("name")] = {p.get("name"): p for p in s.elements("param")}
        self.glottis_models = {m.get("type"): GlottisModel(m)
                               for m in root.child("glottis_models").elements("glottis_model")}

    # -- files ------------------------------------------------------------

    @classmethod
    def load(cls, path: str | Path) -> "Speaker":
        path = Path(path)
        with open(path, encoding="utf-8", newline="") as f:
            return cls(f.read(), path)

    def text(self) -> str:
        return self.doc.text()

    def save(self, path: str | Path | None = None) -> Path:
        path = Path(path) if path is not None else self.path
        if path is None:
            raise ValueError("no path to save to")
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(self.text())
        self.path = path
        return path

    # -- convenience ------------------------------------------------------

    @property
    def tract_param_names(self) -> list[str]:
        return [p.name for p in self.tract_params]

    def tract_shape(self, name: str) -> list[float]:
        """The shape's parameters in the order of the anatomy's <param> list."""
        s = self.tract_shapes[name]
        return [float(s[p.name].get("value")) for p in self.tract_params]

    @property
    def selected_glottis(self) -> GlottisModel:
        for m in self.glottis_models.values():
            if m.selected:
                return m
        return self.glottis_models[GLOTTIS_MODELS[0]]

    # -- addressed values ---------------------------------------------------

    def _locate(self, addr: Address) -> tuple[Element, str]:
        kind = addr[0]
        if kind == "tract_shape":
            _, shape, param = addr
            return self.tract_shapes[shape][param], "value"
        if kind == "tract_param":
            _, param, fld = addr
            for p in self.tract_params:
                if p.name == param:
                    return p.element, fld
            raise KeyError(f"no tract parameter {param!r}")
        if kind == "glottis_static":
            _, model, key = addr
            return self.glottis_models[model].static_param(key).element, "value"
        if kind == "glottis_shape":
            _, model, shape, key = addr
            m = self.glottis_models[model]
            return m.shapes[shape][m.control_index(key)], "value"
        if kind == "anatomy":
            e = self.anatomy
            for tag in addr[1:-1]:
                e = e.child(tag)
            return e, addr[-1]
        raise KeyError(f"unknown address kind {kind!r}")

    def canonical(self, addr: Address) -> Address:
        """The address with names in their stored form (glottis abbreviations as indices)."""
        addr = tuple(addr)
        if addr[0] == "glottis_shape":
            m = self.glottis_models[addr[1]]
            return addr[:3] + (m.control_index(addr[3]),)
        if addr[0] == "glottis_static":
            return addr[:2] + (self.glottis_models[addr[1]].static_param(addr[2]).abbr,)
        return addr

    def get(self, addr: Address) -> Any:
        addr = tuple(addr)
        if addr[0] == "glottis_selected":
            return self.selected_glottis.type
        e, name = self._locate(addr)
        v = e.get(name)
        if v is None:
            raise KeyError(f"{addr}: no attribute {name!r}")
        return _number(v)

    def quantize(self, addr: Address, value: Any) -> Any:
        """The value as it will be stored (numbers rounded to the file's decimals)."""
        addr = tuple(addr)
        if addr[0] == "glottis_selected" or isinstance(value, str):
            return value
        e, name = self._locate(addr)
        value = float(value)
        if not math.isfinite(value):
            raise ValueError(f"{addr}: {value} is not a finite number")
        return quantize_like(e.attr(name).raw, value)

    def set(self, addr: Address, value: Any) -> Any:
        """Store a value; returns it as stored."""
        addr = tuple(addr)
        if addr[0] == "glottis_selected":
            if value not in self.glottis_models:
                raise KeyError(f"no glottis model {value!r}")
            for t, m in self.glottis_models.items():
                m.element.set("selected", "1" if t == value else "0")
            return value
        e, name = self._locate(addr)
        if isinstance(value, str):
            e.set(name, value)
            return value
        a = e.attr(name)
        text = format_like(a.raw, float(value))
        a.raw = text
        return float(text)

    # -- JSON for the screen ------------------------------------------------

    def anatomy_json(self) -> dict:
        def node(e: Element) -> dict:
            d: dict = {"tag": e.tag, "attrs": {a.name: _number(a.value) for a in e.attrs}}
            kids = [node(c) for c in e.elements() if c.tag != "param"]
            if kids:
                d["children"] = kids
            return d
        return node(self.anatomy)

    def to_json(self) -> dict:
        return {
            "path": str(self.path) if self.path else None,
            "anatomy": self.anatomy_json(),
            "tract": {
                "params": [p.to_json() for p in self.tract_params],
                "shapes": {n: self.tract_shape(n) for n in self.tract_shapes},
            },
            "glottis": {
                "selected": self.selected_glottis.type,
                "models": [m.to_json() for m in self.glottis_models.values()],
            },
        }
