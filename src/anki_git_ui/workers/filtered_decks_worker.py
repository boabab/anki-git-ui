"""Apply filtered-deck definitions from a downloaded deck into a live Anki collection.

Wraps :func:`anki_gitify.api.apply_filtered`. The caller (deck-detail
screen) catches ``RuntimeError`` whose message contains ``"locked"`` and
shows the friendly :class:`AnkiLockedModal`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from anki_gitify import api
from anki_gitify.collection_io import open_collection
from yaml import YAMLError, safe_load

from ..domain.models import AnkiProfileChoice, DeckEntry


@dataclass
class FilteredDecksResult:
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


def apply_filtered_decks(
    deck: DeckEntry,
    anki: AnkiProfileChoice,
    *,
    dry_run: bool = False,
    on_log: Callable[[str], None] | None = None,
) -> FilteredDecksResult:
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
            f"This deck doesn't include any filtered-deck definitions ({spec_path} is missing)."
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
            "Applying filtered decks (dry run)…" if dry_run else "Applying filtered decks…"
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

    return FilteredDecksResult(
        created=list(report.created),
        skipped=list(report.skipped),
        conflicts=list(report.conflicts),
        dry_run=dry_run,
    )


@dataclass
class RebuildFilteredDecksResult:
    rebuilt: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.rebuilt) + len(self.missing) + len(self.conflicts)


def rebuild_filtered_decks(
    deck: DeckEntry,
    anki: AnkiProfileChoice,
    *,
    on_log: Callable[[str], None] | None = None,
) -> RebuildFilteredDecksResult:
    """Rebuild every filtered deck defined in the deck's ``filtered_decks.yml``.

    Equivalent to right-clicking each filtered deck in Anki and choosing
    Rebuild — empties the deck and re-runs its search. Filtered decks listed
    in the spec but not present in the collection are reported as ``missing``
    (the user hasn't run "Set up filtered decks" yet). Names that exist as
    normal (non-filtered) decks are reported as ``conflicts``.

    Raises the same exceptions as :func:`apply_filtered_decks` for the same
    reasons.
    """
    spec_path: Path = deck.local_path / "filtered_decks.yml"
    if not spec_path.is_file():
        raise FileNotFoundError(
            f"This deck doesn't include any filtered-deck definitions ({spec_path} is missing)."
        )

    try:
        data = safe_load(spec_path.read_text(encoding="utf-8")) or {}
    except (OSError, YAMLError) as exc:
        raise ValueError(f"Could not read {spec_path}: {exc}") from exc
    entries = data.get("filtered_decks") if isinstance(data, dict) else None
    if not isinstance(entries, list) or not entries:
        return RebuildFilteredDecksResult()

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
        on_log(f"Rebuilding {len(entries)} filtered deck(s)…")

    result = RebuildFilteredDecksResult()
    with open_collection(paths.collection) as col:
        for entry in entries:
            name = entry.get("name") if isinstance(entry, dict) else None
            if not isinstance(name, str):
                continue
            did = col.decks.id_for_name(name)
            if did is None:
                result.missing.append(name)
                if on_log is not None:
                    on_log(f"  ? {name} (not in your Anki yet)")
                continue
            deck_obj = col.decks.get(did)
            if int(deck_obj.get("dyn", 0)) != 1:
                result.conflicts.append(name)
                if on_log is not None:
                    on_log(f"  ! {name} (a normal deck with this name — skipped)")
                continue
            col.sched.rebuild_filtered_deck(did)
            result.rebuilt.append(name)
            if on_log is not None:
                on_log(f"  ✓ {name} (rebuilt)")

    if on_log is not None:
        on_log(
            f"Done — rebuilt={len(result.rebuilt)}, missing={len(result.missing)}, "
            f"conflicts={len(result.conflicts)}."
        )
    return result
