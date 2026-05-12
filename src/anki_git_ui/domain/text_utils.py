"""Small string helpers shared between widgets."""

from __future__ import annotations


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
