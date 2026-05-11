"""Apply filtered-deck definitions from a downloaded deck into a live Anki collection.

Wraps :func:`anki_gitify.api.apply_filtered`. The caller (deck-detail
screen) catches ``RuntimeError`` whose message contains ``"locked"`` and
shows the friendly :class:`AnkiLockedModal`.
"""

from __future__ import annotations

import shutil
import subprocess
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
    locked: bool = False

    @property
    def total(self) -> int:
        return len(self.created) + len(self.skipped) + len(self.conflicts)


def is_anki_desktop_running() -> bool:
    """Best-effort check for whether the Anki desktop app is running locally.

    The SDK's per-collection lock only fires when both processes touch the
    *same* ``collection.anki2``. Writes to a *different* profile while Anki
    desktop is open are unsafe too (media sync can race, the desktop may
    overwrite on close), so we want a louder, profile-independent signal.

    Uses ``pgrep`` to look for the Anki ``.app`` bundle or the bundled
    ``aqt.run`` Python launcher. Returns False if pgrep is unavailable or
    fails — the SDK lock check remains the authoritative backstop.
    """
    pgrep = shutil.which("pgrep")
    if pgrep is None:
        return False
    try:
        result = subprocess.run(
            [pgrep, "-f", r"Anki\.app/Contents/MacOS|aqt\.run"],
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0 and bool(result.stdout.strip())


def is_locked_error(err: BaseException) -> bool:
    """Detect 'Anki is open / collection locked / mid-sync' errors.

    Matches multiple phrasings the Anki SDK (and anki-gitify's wrapper) use:
    - ``"Anki already open"`` / ``"currently syncing"`` — the Rust backend's
      top-level message when Anki desktop holds the collection. The exception
      is ``anki.errors.DBError`` (a sibling of ``RuntimeError``, not a
      subclass), so we deliberately don't ``isinstance``-check the type.
    - ``"locked"`` / ``"database is locked"`` — anki-gitify's wrapped
      ``RuntimeError`` and the raw SQLite-level error.
    """
    msg = str(err).lower()
    return (
        "locked" in msg
        or "already open" in msg
        or "currently syncing" in msg
    )


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

    try:
        report = api.apply_filtered(
            deck.local_path,
            paths.collection,
            dry_run=dry_run,
        )
    except Exception as exc:
        if is_locked_error(exc):
            if on_log is not None:
                on_log("Anki is open — close it and try again.")
            return FilteredDecksResult(
                created=[], skipped=[], conflicts=[], dry_run=dry_run, locked=True,
            )
        raise

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
    locked: bool = False

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
    try:
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
    except Exception as exc:
        if is_locked_error(exc):
            if on_log is not None:
                on_log("Anki is open — close it and try again.")
            return RebuildFilteredDecksResult(locked=True)
        raise

    if on_log is not None:
        on_log(
            f"Done — rebuilt={len(result.rebuilt)}, missing={len(result.missing)}, "
            f"conflicts={len(result.conflicts)}."
        )
    return result
