"""Small string helpers shared between widgets."""

from __future__ import annotations

from pathlib import Path


def format_path(p: Path) -> str:
    """Render a path for the UI in the user's native OS style.

    Windows users see backslashes, POSIX users see forward slashes. Snapshot
    tests monkeypatch this to return POSIX form so SVGs are stable across
    runners — production behavior stays native.
    """
    return str(p)


def truncate(text: str, width: int, *, ellipsis: str = "…") -> str:
    """Truncate ``text`` to fit in ``width`` cells, using ``ellipsis`` for the tail.

    Returns the original string if it already fits, an empty string for
    non-positive widths, and ``<prefix><ellipsis>`` otherwise.
    """
    if width <= 0:
        return ""
    if len(text) <= width:
        return text
    return text[: max(0, width - len(ellipsis))] + ellipsis
