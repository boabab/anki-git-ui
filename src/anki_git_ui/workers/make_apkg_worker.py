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
    Completed as InteropCompleted,
    Failed as InteropFailed,
    ImportReport,
)
from ..domain.apkg_paths import apkg_output_path
from ..domain.jobs import Completed, Failed, JobOutcome
from ..domain.models import DeckEntry
from ..jobs import Job


def make_apkg(
    deck: DeckEntry,
    default_save_folder: Path,
    *,
    on_log: Callable[[str], None] | None = None,
    ignore_card_overrides: bool = False,
):
    """Build the ``.apkg`` for ``deck`` under ``default_save_folder/.builds/``.

    Returns one of the :mod:`anki_interop` outcome variants:

    - :class:`anki_interop.Completed` ``[ImportReport]`` — build succeeded;
      ``deck``'s ``last_built_*`` fields are stamped in place.
    - :class:`CardOverrideRequired` — the deck ships a ``cards.csv``; caller
      should confirm with the user and re-invoke with
      ``ignore_card_overrides=True``.
    - :class:`anki_interop.Failed` — anything else; carries the original
      exception.
    """
    out = apkg_output_path(default_save_folder, deck.local_path, deck.last_pulled_commit)
    outcome = anki_interop.import_deck(
        deck.local_path,
        out,
        ignore_card_overrides=ignore_card_overrides,
        on_log=on_log,
    )
    if isinstance(outcome, InteropCompleted):
        deck.last_built_apkg = outcome.value.apkg_path
        deck.last_built_commit = deck.last_pulled_commit
        deck.last_built_at = outcome.value.built_at
    return outcome


def make_apkg_job(
    deck: DeckEntry,
    default_save_folder: Path,
    *,
    on_log: Callable[[str], None] | None = None,
    ignore_card_overrides: bool = False,
) -> Job[ImportReport]:
    """Build a :class:`Job` that produces ``deck``'s ``.apkg`` and translates
    the result to a :class:`JobOutcome`.

    :class:`CardOverrideRequired` becomes :class:`Failed` with
    ``kind="card_override"`` — the screen branches on the kind to show its
    retry-with-flag modal instead of a generic error.
    """

    def _work() -> JobOutcome[ImportReport]:
        outcome = make_apkg(
            deck,
            default_save_folder,
            on_log=on_log,
            ignore_card_overrides=ignore_card_overrides,
        )
        if isinstance(outcome, InteropCompleted):
            return Completed(outcome.value)
        if isinstance(outcome, CardOverrideRequired):
            message = (
                "This deck assigns some cards to a different deck than their "
                "note. Confirm to build anyway."
            )
            return Failed(
                exc=RuntimeError(message),
                message=message,
                kind="card_override",
            )
        assert isinstance(outcome, InteropFailed)
        return Failed(exc=outcome.exc, message=outcome.message)

    return Job(name="build", work=_work)


__all__ = [
    "CardOverrideRequired",
    "ImportReport",
    "make_apkg",
    "make_apkg_job",
]
