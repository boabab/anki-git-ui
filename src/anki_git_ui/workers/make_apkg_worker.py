"""Build the ``.apkg`` from a downloaded deck folder via ``anki_gitify.api``."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from anki_gitify import api

from ..domain.apkg_paths import apkg_output_path
from ..domain.models import DeckEntry, MakeAnkiFileResult


@dataclass
class _NoOp:
    """Sentinel for the no-callback case so type checkers stay happy."""


def make_apkg(
    deck: DeckEntry,
    default_save_folder: Path,
    *,
    on_log: Callable[[str], None] | None = None,
    ignore_card_overrides: bool = False,
) -> MakeAnkiFileResult:
    """Run ``api.import_(deck.local_path, out_apkg)`` and update bookkeeping.

    Raises :class:`anki_gitify.api.CardOverrideError` if ``cards.csv`` is
    present and ``ignore_card_overrides`` is False — caller surfaces as a
    friendly "the deck has per-card placement, want to proceed?" modal.

    Other failures bubble up as ``ValueError`` / ``FileNotFoundError`` from
    the loader.
    """
    out = apkg_output_path(default_save_folder, deck.local_path, deck.last_pulled_commit)

    if on_log is not None:
        on_log(f"Validating deck files in {deck.local_path}…")
        # api.verify is read-only; running it first surfaces structural
        # problems with a clean error before genanki gets confused.
        report = api.verify(deck.local_path)
        if not report.ok:
            for err in report.errors:
                on_log(f"  ! {err}")
            raise ValueError(
                "The deck files don't look right. " + (report.errors[0] if report.errors else "")
            )
        on_log(f"  notes={report.notes}, notetypes={report.notetypes}, media={report.media}")
        on_log(f"Building Anki file at {out}…")

    out.parent.mkdir(parents=True, exist_ok=True)
    import_report, _ = api.import_(
        deck.local_path,
        out,
        ignore_card_overrides=ignore_card_overrides,
    )

    deck.last_built_apkg = out
    deck.last_built_commit = deck.last_pulled_commit
    deck.last_built_at = datetime.now(timezone.utc)

    if on_log is not None:
        on_log(f"Done — {out.name} ({import_report.notes} notes, {import_report.media_files} media files).")

    return MakeAnkiFileResult(
        apkg_path=out,
        notes=import_report.notes,
        media_files=import_report.media_files,
        filtered_decks=import_report.filtered_decks,
    )
