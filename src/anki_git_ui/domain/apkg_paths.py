"""Where to write built ``.apkg`` files, and how to reveal one in the OS file manager."""

from __future__ import annotations

import platform
import subprocess
from pathlib import Path


def apkg_output_path(default_save_folder: Path, local_path: Path, commit: str | None) -> Path:
    """Return ``<save>/.builds/<basename>-<short-sha>.apkg``.

    Keying on the commit sha (not a date) lets the dashboard distinguish
    "already prepared this exact version" from "prepared a different version
    on the same day". Falls back to ``unknown`` if no commit is known.
    """
    short = (commit or "unknown")[:7]
    name = local_path.name or "deck"
    return default_save_folder / ".builds" / f"{name}-{short}.apkg"


def reveal_in_file_manager(path: Path) -> bool:
    """Open the OS file manager focused on ``path``. Best-effort; never raises."""
    if not path.exists():
        return False
    system = platform.system()
    try:
        if system == "Darwin":
            subprocess.run(["open", "-R", str(path)], check=False)
        elif system == "Windows":
            subprocess.run(["explorer", "/select,", str(path)], check=False)
        else:
            # Linux and other Unix: open the parent dir.
            target = path if path.is_dir() else path.parent
            subprocess.run(["xdg-open", str(target)], check=False)
        return True
    except (OSError, FileNotFoundError):
        return False


def open_with_default_app(path: Path) -> bool:
    """Open ``path`` with the OS-default app — typically Anki for .apkg."""
    if not path.exists():
        return False
    system = platform.system()
    try:
        if system == "Darwin":
            subprocess.run(["open", str(path)], check=False)
        elif system == "Windows":
            subprocess.run(["start", "", str(path)], shell=True, check=False)
        else:
            subprocess.run(["xdg-open", str(path)], check=False)
        return True
    except (OSError, FileNotFoundError):
        return False
