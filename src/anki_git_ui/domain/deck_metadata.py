"""Deck-shape knowledge that lives in the on-disk gitified directory.

Today: reading ``filtered_decks.yml`` to discover which filtered decks the
deck ships with. The Anki interop facade consumes the return value but
does not own the YAML parsing — that's deck-shape, not Anki interop.
"""

from __future__ import annotations

from pathlib import Path

from yaml import YAMLError, safe_load


def list_filtered_deck_names(deck_path: Path) -> list[str]:
    """Return the deck names declared in ``deck_path/filtered_decks.yml``.

    Returns an empty list if the file is missing, malformed, or contains no
    ``filtered_decks`` entries. Non-string ``name`` values are skipped.
    """
    spec_path = deck_path / "filtered_decks.yml"
    if not spec_path.is_file():
        return []
    try:
        data = safe_load(spec_path.read_text(encoding="utf-8")) or {}
    except (OSError, YAMLError):
        return []
    if not isinstance(data, dict):
        return []
    entries = data.get("filtered_decks") or []
    if not isinstance(entries, list):
        return []
    names: list[str] = []
    for entry in entries:
        if isinstance(entry, dict):
            name = entry.get("name")
            if isinstance(name, str):
                names.append(name)
    return names


def has_filtered_decks(deck_path: Path) -> bool:
    """Convenience: True iff the deck ships at least one filtered-deck entry."""
    return bool(list_filtered_deck_names(deck_path))
