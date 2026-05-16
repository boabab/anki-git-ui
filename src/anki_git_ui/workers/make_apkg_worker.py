"""Build the ``.apkg`` from a downloaded deck folder.

Thin translation layer over :func:`anki_interop.import_deck`: figures out
the output path, calls the facade, and stamps the resulting build onto the
:class:`DeckEntry` on success.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from ..domain import anki_interop
from ..domain.anki_interop import (
    CardOverrideRequired,
    Completed,
    Failed,
    ImportReport,
)
from ..domain.apkg_paths import apkg_output_path
from ..domain.models import DeckEntry


def make_apkg(
    deck: DeckEntry,
    default_save_folder: Path,
    *,
    on_log: Callable[[str], None] | None = None,
    ignore_card_overrides: bool = False,
):
    """Build the ``.apkg`` for ``deck`` under ``default_save_folder/.builds/``.

    Returns one of the :mod:`anki_interop` outcome variants:

    - :class:`Completed` ``[ImportReport]`` — build succeeded; ``deck``'s
      ``last_built_*`` fields are stamped in place.
    - :class:`CardOverrideRequired` — the deck ships a ``cards.csv``; caller
      should confirm with the user and re-invoke with
      ``ignore_card_overrides=True``.
    - :class:`Failed` — anything else; carries the original exception.
    """
    out = apkg_output_path(default_save_folder, deck.local_path, deck.last_pulled_commit)
    outcome = anki_interop.import_deck(
        deck.local_path,
        out,
        ignore_card_overrides=ignore_card_overrides,
        on_log=on_log,
    )
    if isinstance(outcome, Completed):
        deck.last_built_apkg = outcome.value.apkg_path
        deck.last_built_commit = deck.last_pulled_commit
        deck.last_built_at = outcome.value.built_at
    return outcome


__all__ = [
    "CardOverrideRequired",
    "Completed",
    "Failed",
    "ImportReport",
    "make_apkg",
]
