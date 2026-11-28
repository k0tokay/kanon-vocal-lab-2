"""The project: the data the server holds, its one undo history, and listeners.

Stage 1 holds speakers only. Tracks, clips and works come later; they will
be edited through operations the same way.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any, Callable

from . import operators  # noqa: F401  (registers the operations)
from .names import APP_ID
from .ops import OPERATORS, Change, Context, History, OpsNamespace, Step
from .speaker import Speaker

Listener = Callable[[dict], None]


def meta_path(speaker_path: Path) -> Path:
    """`foo.speaker` -> `foo.meta.json` (version notes and the operation log)."""
    return speaker_path.with_name(speaker_path.stem + ".meta.json")


# Files the server never overwrites: the user's hand-made speakers and those
# derived from recordings. They are saved under another name instead.
PROTECTED = re.compile(r"manual-edit|intuition|(^|[-_.])rec([-_.]|$)|recording", re.IGNORECASE)
# A released version of a speaker (`speakers/.../*-vX-Y-Z.speaker`) is not
# overwritten either: a change becomes a new version (save as).
VERSIONED = re.compile(r"-v\d+-\d+-\d+\.speaker$")


class SaveRefused(Exception):
    """A save the server will not do. `reason`: "protected" | "versioned" | "exists"."""

    def __init__(self, reason: str, path: Path):
        super().__init__(f"{reason}: {path}")
        self.reason = reason
        self.path = path


def save_refusal(target: Path, current: Path | None, overwrite: bool) -> str | None:
    """Why writing `target` is refused, or None. `current` is the speaker's own file."""
    target = target.resolve()
    if not target.exists():
        return None
    if PROTECTED.search(target.stem):
        return "protected"
    if VERSIONED.search(target.name) and "speakers" in target.parts:
        return "versioned"
    same = current is not None and current.resolve() == target
    if not same and not overwrite:
        return "exists"
    return None


class Project:
    def __init__(self):
        self.speakers: dict[str, Speaker] = {}
        self.history = History()
        self.ops = OpsNamespace(self)
        self._listeners: list[Listener] = []
        self._unsaved_log: dict[str, list[dict]] = {}
        # Per speaker: address -> value at the last save (or open), for every
        # address changed since. An address is "edited" while its value differs.
        self._saved: dict[str, dict[tuple, Any]] = {}

    # -- speakers -----------------------------------------------------------

    def open_speaker(self, path: str | Path, speaker_id: str | None = None) -> str:
        """Load a `.speaker` file. Opening is not an undoable operation."""
        sp = Speaker.load(path)
        sid = speaker_id or Path(path).stem
        if sid in self.speakers:
            raise KeyError(f"speaker id {sid!r} is already in use")
        self.speakers[sid] = sp
        self._unsaved_log[sid] = []
        self._saved[sid] = {}
        self._emit({"type": "speaker_opened", "speaker": sid})
        return sid

    def is_modified(self, speaker_id: str) -> bool:
        return bool(self._unsaved_log[speaker_id])

    def save_speaker(self, speaker_id: str, path: str | Path | None = None, *,
                     overwrite: bool = False) -> Path:
        """Write the `.speaker` and add this save, with the operations since the
        last save, to the `.meta.json` next to it. Saving is not an undo step.

        Without `path` the speaker's own file is written. Raises `SaveRefused`
        for protected and versioned files, and for another existing file
        unless `overwrite`."""
        sp = self.speakers[speaker_id]
        target = self.resolve_path(speaker_id, path)
        why = save_refusal(target, sp.path, overwrite)
        if why:
            raise SaveRefused(why, target)
        self._commit_open()
        out = sp.save(target)
        mp = meta_path(out)
        meta: dict = {}
        if mp.exists():
            meta = json.loads(mp.read_text(encoding="utf-8"))
        meta.setdefault("app", APP_ID)
        meta.setdefault("saves", []).append({
            "time": _iso(time.time()),
            "file": out.name,
            "sha256": hashlib.sha256(out.read_bytes()).hexdigest(),
            "operations": self._unsaved_log[speaker_id],
        })
        mp.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self._unsaved_log[speaker_id] = []
        self._saved[speaker_id] = {}
        self._emit({"type": "speaker_saved", "speaker": speaker_id, "path": str(out)})
        return out

    def resolve_path(self, speaker_id: str, path: str | Path | None) -> Path:
        """The file a save writes: relative paths are taken from the speaker's
        folder, `~` is expanded and `.speaker` is added when missing."""
        sp = self.speakers[speaker_id]
        if path is None or str(path).strip() == "":
            if sp.path is None:
                raise ValueError("no path to save to")
            return Path(sp.path)
        p = Path(str(path).strip()).expanduser()
        if not p.is_absolute():
            p = (Path(sp.path).parent if sp.path else Path.cwd()) / p
        if p.suffix != ".speaker":
            p = p.with_name(p.name + ".speaker")
        return p

    # -- listeners ------------------------------------------------------------

    def subscribe(self, fn: Listener) -> Callable[[], None]:
        """Call `fn(event)` after every change. Returns a function that unsubscribes."""
        self._listeners.append(fn)
        return lambda: self._listeners.remove(fn)

    def _emit(self, event: dict) -> None:
        event["history"] = self.history.state()
        for fn in list(self._listeners):
            fn(event)

    def edited(self, speaker_id: str) -> dict[tuple, Any]:
        """Addresses whose value differs from the last save -> the saved value."""
        sp = self.speakers[speaker_id]
        return {a: v for a, v in self._saved[speaker_id].items() if sp.get(a) != v}

    def _changes_json(self, changes: list[Change], use_old: bool = False) -> list[dict]:
        out = []
        for c in changes:
            saved = self._saved[c.speaker].setdefault(c.address, c.new if use_old else c.old)
            value = c.old if use_old else c.new
            d = c.to_json(value)
            d["edited"] = value != saved
            d["saved"] = saved
            out.append(d)
        return out

    # -- operations -----------------------------------------------------------

    def call(self, name: str, args: dict | None = None, *, drag: Any = None) -> Any:
        """Run an operation. With `drag`, consecutive calls with the same key are
        one undo step until `end_drag(key)`."""
        op = OPERATORS[name]
        args = dict(args or {})
        h = self.history
        if h.open is not None and h.open.key is not None and isinstance(h.open.key, _Group):
            step = h.open  # inside a group: everything joins it
        elif drag is not None and h.open is not None and h.open.key == ("drag", drag):
            step = h.open
        else:
            self._commit_open()
            step = Step(op.label, key=("drag", drag) if drag is not None else None)
            h.open = step

        mine: list[Change] = []
        ctx = Context(self, mine.append)
        try:
            result = op.fn(ctx, **args)
        except Exception:
            for c in reversed(mine):  # leave the data as it was
                self.speakers[c.speaker].set(c.address, c.old)
            if not step.changes and not step.calls:
                h.open = None
            raise
        for c in mine:
            step.add(Change(c.speaker, c.address, c.old, c.new))
        step.calls.append({"op": name, "args": args})
        if step.key is None:
            self._commit_open()
        if mine:
            self._emit({"type": "changed", "source": "do", "op": name,
                        "changes": self._changes_json(mine)})
        return result

    def end_drag(self, drag: Any) -> None:
        h = self.history
        if h.open is not None and h.open.key == ("drag", drag):
            self._commit_open()
            self._emit({"type": "history"})

    @contextlib.contextmanager
    def group(self, label: str):
        """Everything inside is one undo step (bulk edits, scripts)."""
        h = self.history
        if h.open is not None and isinstance(h.open.key, _Group):
            yield  # nested groups join the outer one
            return
        self._commit_open()
        token = _Group()
        h.open = Step(label, key=token)
        try:
            yield
        finally:
            if h.open is not None and h.open.key is token:
                self._commit_open()
                self._emit({"type": "history"})

    def _commit_open(self) -> None:
        h = self.history
        step, h.open = h.open, None
        if step is None or not step.changes:
            return
        step.key = None
        h.done.append(step)
        h.undone.clear()
        self._log(step, "do")

    def _log(self, step: Step, action: str) -> None:
        entry = {"time": _iso(time.time()), "action": action, "label": step.label}
        if action == "do":
            entry["calls"] = step.calls
        for sid in step.speakers:
            self._unsaved_log[sid].append(entry)

    # -- undo -------------------------------------------------------------------

    def undo(self) -> bool:
        self._commit_open()
        h = self.history
        if not h.done:
            return False
        step = h.done.pop()
        for c in reversed(step.changes):
            self.speakers[c.speaker].set(c.address, c.old)
        h.undone.append(step)
        self._log(step, "undo")
        self._emit({"type": "changed", "source": "undo", "label": step.label,
                    "changes": self._changes_json(list(reversed(step.changes)), use_old=True)})
        return True

    def redo(self) -> bool:
        self._commit_open()
        h = self.history
        if not h.undone:
            return False
        step = h.undone.pop()
        for c in step.changes:
            self.speakers[c.speaker].set(c.address, c.new)
        h.done.append(step)
        self._log(step, "redo")
        self._emit({"type": "changed", "source": "redo", "label": step.label,
                    "changes": self._changes_json(step.changes)})
        return True

    # -- for the screen -----------------------------------------------------------

    def to_json(self) -> dict:
        return {
            "speakers": {sid: sp.to_json() | {
                "modified": self.is_modified(sid),
                "edited": [{"address": list(a), "saved": v} for a, v in self.edited(sid).items()],
            } for sid, sp in self.speakers.items()},
            "history": self.history.state(),
            "operations": {n: {"label": o.label, "doc": o.doc} for n, o in OPERATORS.items()},
        }


class _Group:
    """Identity token of an open `Project.group`."""


def _iso(t: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(t))
