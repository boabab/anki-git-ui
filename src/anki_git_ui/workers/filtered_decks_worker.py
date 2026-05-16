"""Apply / rebuild filtered-deck definitions for a downloaded deck.

Thin translation layer over :mod:`anki_git_ui.domain.anki_interop`: takes a
:class:`DeckEntry`, locates ``filtered_decks.yml`` on disk, and delegates
the SDK call to the facade. The facade owns lock detection and error
classification; this module never catches :class:`Exception`.
"""

from __future__ import annotations

from collections.abc import Callable

from ..domain import anki_interop, deck_metadata
from ..domain.anki_interop import (
    ApplyReport,
    Completed,
    Failed,
    Locked,
    RebuildReport,
)
from ..domain.models import AnkiProfileChoice, DeckEntry


def apply_filtered_decks(
    deck: DeckEntry,
    anki: AnkiProfileChoice,
    *,
    dry_run: bool = False,
    on_log: Callable[[str], None] | None = None,
):
    """Apply this deck's ``filtered_decks.yml`` to the user's Anki collection.

    Returns one of the :mod:`anki_interop` outcome variants:
    ``Completed[ApplyReport]``, :class:`Locked`, :class:`CollectionMissing`,
    or :class:`Failed`. A missing ``filtered_decks.yml`` surfaces as
    :class:`Failed` carrying :class:`FileNotFoundError` — the caller
    shouldn't have offered the action in the first place.
    """
    spec_path = deck.local_path / "filtered_decks.yml"
    if not spec_path.is_file():
        message = (
            f"This deck doesn't include any filtered-deck definitions "
            f"({spec_path} is missing)."
        )
        return Failed(exc=FileNotFoundError(message), message=message)

    return anki_interop.apply_filtered(
        deck.local_path,
        anki,
        dry_run=dry_run,
        on_log=on_log,
    )


def rebuild_filtered_decks(
    deck: DeckEntry,
    anki: AnkiProfileChoice,
    *,
    on_log: Callable[[str], None] | None = None,
):
    """Re-run the filters of every filtered deck this deck declares.

    Equivalent to right-clicking each filtered deck in Anki and choosing
    Rebuild. Returns the same outcome variants as :func:`apply_filtered_decks`.
    """
    spec_path = deck.local_path / "filtered_decks.yml"
    if not spec_path.is_file():
        message = (
            f"This deck doesn't include any filtered-deck definitions "
            f"({spec_path} is missing)."
        )
        return Failed(exc=FileNotFoundError(message), message=message)

    entries = deck_metadata.list_filtered_deck_names(deck.local_path)
    return anki_interop.rebuild_filtered(
        deck.local_path,
        anki,
        entries=entries,
        on_log=on_log,
    )


__all__ = [
    "ApplyReport",
    "Completed",
    "Failed",
    "Locked",
    "RebuildReport",
    "apply_filtered_decks",
    "rebuild_filtered_decks",
]
