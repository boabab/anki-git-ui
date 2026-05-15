"""Small string helpers shared between widgets."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path


def humanize_age(
    dt: datetime | None,
    *,
    fallback: str = "never",
    now: datetime | None = None,
) -> str:
    """Render the age of ``dt`` as a short English phrase.

    Returns ``fallback`` when ``dt`` is None. Otherwise rounds the delta down
    to the nearest unit and renders as "just now", "N minute(s) ago",
    "N hour(s) ago", or "N day(s) ago". Plurality follows the dashboard's
    original logic: minutes/hours plural at >= 2 of that unit, days plural
    when the count is not exactly 1.

    The ``now`` kwarg exists for deterministic tests; production callers
    omit it and the function reads the wall clock via :func:`datetime.now`.
    """
    if dt is None:
        return fallback
    reference = now if now is not None else datetime.now(timezone.utc)
    dt_utc = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    secs = int((reference - dt_utc).total_seconds())
    if secs < 60:
        return "just now"
    if secs < 3600:
        return f"{secs // 60} minute{'s' if secs >= 120 else ''} ago"
    if secs < 86400:
        return f"{secs // 3600} hour{'s' if secs >= 7200 else ''} ago"
    days = secs // 86400
    return f"{days} day{'s' if days != 1 else ''} ago"


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
