"""The project: the data the server holds, its one undo history, and listeners.

It holds documents of two kinds, each under an id: speakers (`.speaker`) and
one gestural score (`.ges`). Both are edited through operations, share the one
history, and are saved with the same rules. Tracks, clips and works come later.
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
from .score import Score
from .speaker import STATUS_LEVELS, Speaker

Listener = Callable[[dict], None]


def meta_path(speaker_path: Path) -> Path:
    """`foo.speaker` -> `foo.meta.json` (version notes and the operation log).
    A score `foo.ges` has `foo.ges.meta.json`, so a score and a speaker of the
    same name in one folder do not share it."""
    if speaker_path.suffix == ".ges":
        return speaker_path.with_name(speaker_path.name + ".meta.json")
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
        self.scores: dict[str, Score] = {}  # one at a time for now
        self.history = History()
        self.ops = OpsNamespace(self)
        self._listeners: list[Listener] = []
        self._unsaved_log: dict[str, list[dict]] = {}
        # Per speaker: address -> value at the last save (or open), for every
        # address changed since. An address is "edited" while its value differs.
        self._saved: dict[str, dict[tuple, Any]] = {}

    # -- documents ----------------------------------------------------------

    def doc(self, doc_id: str) -> Speaker | Score:
        """A speaker or a score by its id (ids are unique across both)."""
        if doc_id in self.speakers:
            return self.speakers[doc_id]
        if doc_id in self.scores:
            return self.scores[doc_id]
        raise KeyError(f"no speaker or score {doc_id!r}")

    def _free_id(self, base: str) -> str:
        sid, k = base, 2
        while sid in self.speakers or sid in self.scores:
            sid, k = f"{base}-{k}", k + 1
        return sid

    def open_score(self, path: str | Path, score_id: str | None = None, *, discard: bool = False) -> str:
        """Load a `.ges` file in place of the open score. Opening is not an undoable
        operation; the history steps of the score it replaces are dropped. With
        unsaved changes in that score it is refused unless `discard`."""
        sc = Score.load(path)
        for old in list(self.scores):
            if self.is_modified(old) and not discard:
                raise ValueError(f"the score {old!r} has unsaved changes")
        for old in list(self.scores):
            self._forget(old)
        sid = score_id or self._free_id(Path(path).stem)
        if sid in self.speakers or sid in self.scores:
            raise KeyError(f"id {sid!r} is already in use")
        self.scores[sid] = sc
        self._unsaved_log[sid] = []
        self._saved[sid] = {}
        self._emit({"type": "score_opened", "score": sid})
        return sid

    def _forget(self, doc_id: str) -> None:
        """Drop a document and every history step that changed it."""
        self.scores.pop(doc_id, None)
        self._unsaved_log.pop(doc_id, None)
        self._saved.pop(doc_id, None)
        h = self.history
        if h.open is not None and doc_id in h.open.speakers:
            h.open = None
        h.done = [s for s in h.done if doc_id not in s.speakers]
        h.undone = [s for s in h.undone if doc_id not in s.speakers]

    # -- speakers -----------------------------------------------------------

    def open_speaker(self, path: str | Path, speaker_id: str | None = None) -> str:
        """Load a `.speaker` file. Opening is not an undoable operation."""
        sp = Speaker.load(path)
        sp.status = read_status(Path(path))
        sid = speaker_id or Path(path).stem
        if sid in self.speakers or sid in self.scores:
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
        sp = self.doc(speaker_id)
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
        if isinstance(sp, Speaker):
            meta["status"] = sp.status_json()  # the marks as they are now (not a log)
        meta.setdefault("saves", []).append({
            "time": _iso(time.time()),
            "file": out.name,
            "sha256": hashlib.sha256(out.read_bytes()).hexdigest(),
            "operations": self._unsaved_log[speaker_id],
        })
        mp.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self._unsaved_log[speaker_id] = []
        self._saved[speaker_id] = {}
        self._emit({"type": "speaker_saved" if isinstance(sp, Speaker) else "score_saved",
                    "speaker": speaker_id, "path": str(out)})
        return out

    def save_score(self, score_id: str, path: str | Path | None = None, *, overwrite: bool = False) -> Path:
        """Write the `.ges` (same rules as `save_speaker`; the log goes to `foo.ges.meta.json`)."""
        if score_id not in self.scores:
            raise KeyError(f"no score {score_id!r}")
        return self.save_speaker(score_id, path, overwrite=overwrite)

    def resolve_path(self, speaker_id: str, path: str | Path | None) -> Path:
        """The file a save writes: relative paths are taken from the speaker's
        folder, `~` is expanded and `.speaker` (`.ges` for a score) is added when missing."""
        sp = self.doc(speaker_id)
        suffix = ".speaker" if isinstance(sp, Speaker) else ".ges"
        if path is None or str(path).strip() == "":
            if sp.path is None:
                raise ValueError("no path to save to")
            return Path(sp.path)
        p = Path(str(path).strip()).expanduser()
        if not p.is_absolute():
            p = (Path(sp.path).parent if sp.path else Path.cwd()) / p
        if p.suffix != suffix:
            p = p.with_name(p.name + suffix)
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
        sp = self.doc(speaker_id)
        out = {}
        for a, v in self._saved[speaker_id].items():
            try:
                now = sp.get(a)
            except KeyError:  # a value of a shape that is not there now: the shape counts
                continue
            if _differs(a, now, v):
                out[a] = v
        return out

    def _changes_json(self, changes: list[Change], use_old: bool = False) -> list[dict]:
        out = []
        for c in changes:
            saved = self._saved[c.speaker].setdefault(c.address, c.new if use_old else c.old)
            value = c.old if use_old else c.new
            d = c.to_json(value)
            d["edited"] = _differs(c.address, value, saved)
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
                self.doc(c.speaker).set(c.address, c.old)
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
            self.doc(c.speaker).set(c.address, c.old)
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
            self.doc(c.speaker).set(c.address, c.new)
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
            "scores": {sid: sc.to_json() | {
                "modified": self.is_modified(sid),
                "edited": [{"address": list(a), "saved": v} for a, v in self.edited(sid).items()],
            } for sid, sc in self.scores.items()},
            "history": self.history.state(),
            "operations": {n: {"label": o.label, "doc": o.doc} for n, o in OPERATORS.items()},
        }


def _differs(address: tuple, a: Any, b: Any) -> bool:
    """Whether two values of `address` differ. A whole shape counts only as being
    there or not: its values are addresses of their own, and moving (when its
    siblings are added or removed) is not a change of its own."""
    if address[0].endswith("_def"):
        return (a is None) != (b is None)
    return a != b


def read_status(speaker_path: Path) -> dict[tuple, str]:
    """The status marks kept in the speaker's `.meta.json` (none when it has none)."""
    mp = meta_path(speaker_path)
    if not mp.exists():
        return {}
    try:
        meta = json.loads(mp.read_text(encoding="utf-8"))
    except ValueError:
        return {}
    return {tuple(e["what"]): e["level"] for e in meta.get("status", [])
            if e.get("level") in STATUS_LEVELS and e.get("level") != "todo"}


class _Group:
    """Identity token of an open `Project.group`."""


def _iso(t: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(t))
