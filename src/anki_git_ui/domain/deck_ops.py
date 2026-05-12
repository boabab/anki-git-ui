"""Helpers for removing a tracked deck — used by the Deck Detail screen."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Literal

DeleteOutcome = Literal["deleted", "missing", "skipped-unsafe", "error"]


def delete_deck_files(path: Path) -> DeleteOutcome:
    """Recursively delete ``path`` if it's safe to do so.

    Refuses to touch ``/``, the user's home directory, or any path that
    won't resolve. Anything else the user explicitly opted into is fair
    game — the deletion is opt-in via the Remove modal's checkbox.
    """
    try:
        resolved = path.resolve()
    except Exception:
        return "skipped-unsafe"
    if not resolved.exists():
        return "missing"
    if resolved == Path("/") or resolved == Path.home() or resolved == resolved.parent:
        return "skipped-unsafe"
    try:
        shutil.rmtree(resolved)
    except Exception:
        return "error"
    return "deleted"
