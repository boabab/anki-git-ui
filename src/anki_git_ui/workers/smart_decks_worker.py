"""Apply filtered-deck definitions from a downloaded deck into a live Anki collection.

Wraps :func:`anki_gitify.api.apply_filtered`. The caller (deck-detail
screen) catches ``RuntimeError`` whose message contains ``"locked"`` and
shows the friendly :class:`AnkiLockedModal`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from anki_gitify import api

from ..domain.models import AnkiProfileChoice, DeckEntry


@dataclass
class SmartDecksResult:
    created: list[str]
    skipped: list[str]
    conflicts: list[str]
    dry_run: bool

    @property
    def total(self) -> int:
        return len(self.created) + len(self.skipped) + len(self.conflicts)


def is_locked_error(err: BaseException) -> bool:
    """Detect the 'Anki is open / collection locked' RuntimeError pattern.

    Matches the substring ``"locked"`` in the message, which is what
    ``anki_gitify.collection_io.open_collection`` surfaces. Future versions
    of anki-gitify may use a more specific subclass; the substring contract
    is what the API doc promises is forward-compatible.
    """
    return isinstance(err, RuntimeError) and "locked" in str(err).lower()


def apply_smart_decks(
    deck: DeckEntry,
    anki: AnkiProfileChoice,
    *,
    dry_run: bool = False,
    on_log: Callable[[str], None] | None = None,
) -> SmartDecksResult:
    """Resolve the user's collection path and apply filtered-deck definitions.

    Raises:
        FileNotFoundError: the deck has no ``filtered_decks.yml`` (caller
            shouldn't have offered the action), or the configured Anki
            collection couldn't be located.
        ValueError: profile resolution failed (e.g. no profiles found).
        RuntimeError: includes the ``"locked"`` substring when Anki is open;
            otherwise generic.
    """
    spec_path: Path = deck.local_path / "filtered_decks.yml"
    if not spec_path.is_file():
        raise FileNotFoundError(
            f"This deck doesn't include any smart-deck definitions ({spec_path} is missing)."
        )

    if on_log is not None:
        on_log(
            f"Resolving Anki collection (profile={anki.profile or 'auto'}, "
            f"override={anki.collection_override or '-'})…"
        )
    paths = api.resolve_profile_paths(
        profile=anki.profile,
        collection_override=anki.collection_override,
    )
    if on_log is not None:
        on_log(f"Using collection at {paths.collection}")
        on_log(
            "Applying smart decks (dry run)…" if dry_run else "Applying smart decks…"
        )

    report = api.apply_filtered(
        deck.local_path,
        paths.collection,
        dry_run=dry_run,
    )

    if on_log is not None:
        on_log(
            f"Done — created={len(report.created)}, skipped={len(report.skipped)}, "
            f"conflicts={len(report.conflicts)}."
        )

    return SmartDecksResult(
        created=list(report.created),
        skipped=list(report.skipped),
        conflicts=list(report.conflicts),
        dry_run=dry_run,
    )
