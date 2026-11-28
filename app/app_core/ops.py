"""Operations, undo and change notifications.

Every edit goes through an *operation*: a registered Python function that
changes values only through `Context.set`. Each `set` is recorded as a
`Change` (speaker, address, old value, new value), which is all undo and
redo need. The screen and scripts call the same operations:

    project.ops.tract.set_param(speaker="kanon", shape="a", param="TCX", value=0.3)
    project.call("tract.set_param", {"speaker": "kanon", ...})       # from the server

What becomes one undo step:

- one operation call (a typed number, a button);
- all calls of one drag: `call(..., drag=key)` until `end_drag(key)`;
- all calls inside `with project.group(label):` (a bulk edit, a script).

Changing the view (zoom, selection, workspace) and caches of sound are not
operations and never enter the history.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable

Address = tuple


@dataclass
class Change:
    speaker: str  # the document: a speaker id or a score id
    address: Address
    old: Any
    new: Any

    def to_json(self, value: Any) -> dict:
        return {"speaker": self.speaker, "address": list(self.address), "value": value}


@dataclass
class Step:
    """One entry of the undo history."""

    label: str
    calls: list[dict] = field(default_factory=list)  # [{"op": name, "args": {...}}]
    changes: list[Change] = field(default_factory=list)
    key: Any = None  # drag key or group token while the step is open
    time: float = field(default_factory=time.time)

    def add(self, change: Change) -> None:
        """Add a change, folding it into an earlier change of the same value."""
        for i, c in enumerate(self.changes):
            if c.speaker == change.speaker and c.address == change.address:
                c.new = change.new
                if c.new == c.old:
                    del self.changes[i]
                return
        if change.new != change.old:
            self.changes.append(change)

    @property
    def speakers(self) -> list[str]:
        return sorted({c.speaker for c in self.changes})


# ---------------------------------------------------------------------------
# Registry


@dataclass
class Operator:
    name: str  # "area.verb", e.g. "tract.set_param"
    label: str
    fn: Callable[..., Any]
    doc: str


OPERATORS: dict[str, Operator] = {}


def operator(name: str, label: str | None = None):
    """Register `fn(ctx, **args)` as the operation `name`."""

    def wrap(fn):
        OPERATORS[name] = Operator(name, label or name, fn, (fn.__doc__ or "").strip())
        return fn

    return wrap


class Context:
    """What an operation sees: the project, and `set` that records changes."""

    def __init__(self, project, record: Callable[[Change], None]):
        self.project = project
        self._record = record

    def speaker(self, speaker_id: str):
        return self.project.speakers[speaker_id]

    def score(self, score_id: str):
        return self.project.scores[score_id]

    def get(self, doc_id: str, address: Address) -> Any:
        return self.project.doc(doc_id).get(tuple(address))

    def set(self, doc_id: str, address: Address, value: Any) -> Any:
        """Set a value of a document (a speaker or a score) and record the change."""
        speaker_id = doc_id
        sp = self.project.doc(doc_id)
        address = sp.canonical(address)
        old = sp.get(address)
        new = sp.set(address, value)
        self._record(Change(speaker_id, address, old, new))
        return new


class OpsNamespace:
    """`project.ops.tract.set_param(...)`: operations as attributes, like bpy.ops."""

    def __init__(self, project, prefix: str = ""):
        self._project = project
        self._prefix = prefix

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)
        full = f"{self._prefix}.{name}" if self._prefix else name
        if full in OPERATORS:
            return lambda **args: self._project.call(full, args)
        if any(k.startswith(full + ".") for k in OPERATORS):
            return OpsNamespace(self._project, full)
        raise AttributeError(f"no operation {full!r}")

    def __dir__(self):
        n = len(self._prefix) + 1 if self._prefix else 0
        return sorted({k[n:].split(".")[0] for k in OPERATORS if k.startswith(self._prefix)})


# ---------------------------------------------------------------------------
# History


class History:
    """One undo history per project."""

    def __init__(self):
        self.done: list[Step] = []
        self.undone: list[Step] = []
        self.open: Step | None = None

    def state(self) -> dict:
        return {
            "can_undo": bool(self.done) or bool(self.open and self.open.changes),
            "can_redo": bool(self.undone),
            "undo_label": (self.open.label if self.open and self.open.changes
                           else self.done[-1].label if self.done else None),
            "redo_label": self.undone[-1].label if self.undone else None,
            "open": self.open.label if self.open else None,
        }
