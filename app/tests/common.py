from __future__ import annotations

import unittest
from pathlib import Path

from app_core.vtl import library_path

REPO = Path(__file__).resolve().parents[2]
SPEAKERS = REPO / "speakers"
KANON = SPEAKERS / "fulkhisa-kanon" / "fulkhisa-kanon-v1-4-1.speaker"
JD2 = SPEAKERS / "JD2.speaker"

needs_vtl = unittest.skipUnless(library_path().exists(), f"{library_path()} is not built")


def read_text(path: Path) -> str:
    with open(path, encoding="utf-8", newline="") as f:
        return f.read()
