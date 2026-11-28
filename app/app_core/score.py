"""A VTL gestural score (`.ges`) as a tree.

Like the speaker, the file stays the master copy: a sequence that was not
changed is written back byte for byte, and a changed sequence is written the
way VTL writes it (one `<gesture .../>` per line, numbers with "%f").

A score has eight gesture sequences, one per articulator or source (VTL's
order is `SEQUENCES`). Each is a list of gestures one after another; a gesture
starts where the one before it ends, so only durations are stored.

Values are addressed by tuples, like the speaker's:

    ("sequence", type)        the whole sequence: a tuple of gestures

A gesture is the tuple (value, slope, duration_s, time_constant_s, neutral):
`value` is the shape name (str) for the nominal sequences and a number
written as text ("0.040000") for the others; `neutral` is 0 or 1 (a neutral
gesture has no target: the articulator goes back to rest). Every operation
on a score sets whole sequences, so undoing a split or a deletion is the same
as undoing a changed duration.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import xmltree
from .xmltree import Element

Address = tuple
Gesture = tuple  # (value: str, slope: float, duration_s: float, time_constant_s: float, neutral: int)

MIN_DURATION = 0.001  # s, VTL's MIN_GESTURE_DURATION_MS
DEFAULT_TAU = 0.012  # s, GesturalScore::DEFAULT_TIME_CONSTANT_S


@dataclass(frozen=True)
class SequenceInfo:
    """What VTL accepts in a sequence (GesturalScore::GesturalScore); out of range is clamped."""

    type: str
    unit: str
    nominal: bool  # values are shape names
    min: float
    max: float
    min_slope: float
    max_slope: float
    min_tau: float
    max_tau: float

    def to_json(self) -> dict:
        return dict(self.__dict__)


SEQUENCES = (
    SequenceInfo("vowel-gestures", "", True, 0, 0, 0, 0, 0.008, 0.020),
    SequenceInfo("lip-gestures", "", True, 0, 0, 0, 0, 0.005, 0.04),
    SequenceInfo("tongue-tip-gestures", "", True, 0, 0, 0, 0, 0.005, 0.04),
    SequenceInfo("tongue-body-gestures", "", True, 0, 0, 0, 0, 0.005, 0.04),
    SequenceInfo("velic-gestures", "cm^2", False, -0.1, 1.5, 0, 0, 0.005, 0.04),
    SequenceInfo("glottal-shape-gestures", "", True, 0, 0, 0, 0, 0.005, 0.04),
    SequenceInfo("f0-gestures", "st", False, 48.0, 108.0, -200.0, 200.0, 0.005, 0.04),
    SequenceInfo("lung-pressure-gestures", "dPa", False, 0.0, 16000.0, 0, 0, 0.005, 0.04),
)
SEQUENCE = {s.type: s for s in SEQUENCES}


def _f(x: float) -> str:
    return f"{float(x):f}"


def quantize(x: float) -> float:
    """The value VTL reads back from "%f" (six decimals)."""
    return float(_f(x))


def _clamp(v: float, lo: float, hi: float) -> float:
    return min(max(float(v), lo), hi)


def make_gesture(info: SequenceInfo, value: Any, slope: float, duration: float, tau: float,
                 neutral: Any) -> Gesture:
    """A gesture with VTL's ranges and number format applied."""
    if info.nominal:
        v = str(value)
        if any(c in v for c in '<>&"\n\r\t'):
            raise ValueError(f"not a shape name: {v!r}")
    else:
        x = float(value)
        if not math.isfinite(x):
            raise ValueError(f"not a number: {value!r}")
        v = _f(_clamp(x, info.min, info.max))
    d = float(duration)
    if not math.isfinite(d):
        raise ValueError(f"not a duration: {duration!r}")
    return (v,
            quantize(_clamp(slope, info.min_slope, info.max_slope)),
            quantize(max(d, MIN_DURATION)),
            quantize(_clamp(tau, info.min_tau, info.max_tau)),
            1 if neutral else 0)


def gesture_xml(g: Gesture) -> str:
    return (f'<gesture value="{xmltree.escape(g[0])}" slope="{_f(g[1])}" duration_s="{_f(g[2])}" '
            f'time_constant_s="{_f(g[3])}" neutral="{int(g[4])}" />')


def starts(gestures) -> list[float]:
    """Start time of each gesture."""
    out, t = [], 0.0
    for g in gestures:
        out.append(t)
        t += g[2]
    return out


class Score:
    def __init__(self, doc: xmltree.Document, path: Path | None = None):
        self.doc = doc
        self.path = Path(path) if path else None
        self.elements: dict[str, Element] = {}
        self.sequences: dict[str, tuple] = {}
        self._loaded: dict[str, tuple] = {}  # as read: such a sequence is written as it was
        self._loaded_children: dict[str, list] = {}
        root = doc.root
        if root.tag != "gestural_score":
            raise ValueError(f"not a gestural score: <{root.tag}>")
        for e in root.elements("gesture_sequence"):
            t = e.get("type")
            if t not in SEQUENCE:
                continue  # kept in the file, not shown
            info = SEQUENCE[t]
            gs = []
            for g in e.elements("gesture"):
                gs.append(make_gesture(info, g.get("value", ""), float(g.get("slope", "0") or 0),
                                       float(g.get("duration_s", "0") or 0),
                                       float(g.get("time_constant_s", str(DEFAULT_TAU)) or DEFAULT_TAU),
                                       int(float(g.get("neutral", "0") or 0)) > 0))
            self.elements[t] = e
            self.sequences[t] = self._loaded[t] = tuple(gs)
            self._loaded_children[t] = list(e.children)
        missing = [s.type for s in SEQUENCES if s.type not in self.sequences]
        if missing:
            raise ValueError(f"the score has no sequence {missing[0]!r}")

    # -- files ----------------------------------------------------------------

    @classmethod
    def load(cls, path: str | Path) -> "Score":
        with open(path, encoding="utf-8", newline="") as f:
            text = f.read()
        return cls(xmltree.parse(text), Path(path))

    def text(self) -> str:
        return self.doc.text()

    def save(self, path: str | Path | None = None) -> Path:
        p = Path(path) if path else self.path
        if p is None:
            raise ValueError("no path to save to")
        with open(p, "w", encoding="utf-8", newline="") as f:
            f.write(self.text())
        self.path = p
        return p

    # -- values ----------------------------------------------------------------

    def canonical(self, address: Address) -> Address:
        return tuple(address)

    def get(self, address: Address) -> Any:
        kind, *rest = address
        if kind == "sequence":
            return self.sequences[rest[0]]
        raise KeyError(f"no such address: {address!r}")

    def set(self, address: Address, value: Any) -> Any:
        kind, *rest = address
        if kind != "sequence" or rest[0] not in SEQUENCE:
            raise KeyError(f"no such address: {address!r}")
        t = rest[0]
        info = SEQUENCE[t]
        gs = tuple(make_gesture(info, *g) for g in value)  # empty in some files; operations keep one
        self.sequences[t] = gs
        e = self.elements[t]
        if gs == self._loaded[t]:
            e.children = list(self._loaded_children[t])
        else:
            e.children = self._layout(t, gs)
        e.self_closing = False
        return gs

    def _layout(self, t: str, gs: tuple) -> list:
        """Children of a changed sequence: the indentation of the file, one gesture per line."""
        old = self._loaded_children[t]
        texts = [c for c in old if isinstance(c, str)]
        first_el = next((i for i, c in enumerate(old) if not isinstance(c, str)), None)
        if first_el is not None:
            lead = "".join(c for c in old[:first_el] if isinstance(c, str))
            tail = old[-1] if isinstance(old[-1], str) else ""
        else:
            lead = texts[0] if texts else "\n    "
            tail = "\n  "
        nl = "\r\n" if "\r\n" in lead else "\n"
        indent = lead.rsplit("\n", 1)[-1] if "\n" in lead else "    "
        out: list = [lead]
        for i, g in enumerate(gs):
            if i:
                out.append(nl + indent)
            out.append(_raw_element(gesture_xml(g)))
        out.append(tail)
        return out

    # -- views -------------------------------------------------------------------

    def duration(self) -> float:
        return max(sum(g[2] for g in gs) for gs in self.sequences.values())

    def to_json(self) -> dict:
        return {
            "path": str(self.path) if self.path else None,
            "duration": self.duration(),
            "sequences": [{"type": s.type, "gestures": [list(g) for g in self.sequences[s.type]]}
                          for s in SEQUENCES],
            "info": [s.to_json() for s in SEQUENCES],
        }


def _raw_element(text: str) -> Element:
    """An element parsed from its text (so it writes back exactly that text)."""
    return xmltree.parse(text).root
