"""The single seam between this app and Anki / ``anki-gitify``.

This is the only module in the project that imports :mod:`anki_gitify.api`
or :mod:`anki_gitify.collection_io`. Every call into the SDK returns a
*structured outcome*; callers never see ``RuntimeError``-with-magic-string
or raw ``anki.errors.DBError``. See
[docs/adr/0004-anki-interop-facade.md](../../../docs/adr/0004-anki-interop-facade.md)
for the rationale.

Public surface:

- :func:`detect_profiles` — list profiles under the default Anki base.
- :func:`resolve_collection` — turn an :class:`AnkiProfileChoice` into a
  ``collection.anki2`` path (or :class:`CollectionMissing`).
- :func:`apply_filtered` — apply filtered-deck definitions to a collection.
- :func:`rebuild_filtered` — re-run the filters of existing filtered decks.
- :func:`import_deck` — build a ``.apkg`` from a gitified deck folder.
- :func:`desktop_is_running` — best-effort "is Anki.app open right now?".

Outcome variants:

- :class:`Completed` (``Completed[T]``) — success; ``.value`` carries the
  operation-specific report.
- :class:`Locked` — the local Anki app is holding ``collection.anki2``.
- :class:`CollectionMissing` — profile / path resolution failed.
- :class:`CardOverrideRequired` — the deck has a ``cards.csv`` and the
  caller didn't ask to ignore card overrides. Specific to :func:`import_deck`.
- :class:`Failed` — anything else; carries the original exception so the
  caller can render it.

The variants are intentionally flat: the only fact about ``Locked`` that
matters is *that* the collection is locked, so it has no payload.
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Generic, TypeVar

from anki_gitify import api
from anki_gitify.api import CardOverrideError
from anki_gitify.collection_io import open_collection

from .models import AnkiProfileChoice

T = TypeVar("T")


# ---------- Outcome variants ---------- #


@dataclass(frozen=True)
class Completed(Generic[T]):
    """Success — ``value`` is operation-specific."""

    value: T


@dataclass(frozen=True)
class Locked:
    """The collection is held by Anki desktop. Close Anki and retry."""


@dataclass(frozen=True)
class CollectionMissing:
    """Profile resolution failed — couldn't locate ``collection.anki2``."""

    message: str


@dataclass(frozen=True)
class CardOverrideRequired:
    """The deck has a ``cards.csv``; caller must re-invoke with the override flag.

    Specific to :func:`import_deck`. Surfaced as a separate variant rather
    than rolled into ``Failed`` because the user-facing flow is "ask, then
    retry," not "show an error."
    """


@dataclass(frozen=True)
class Failed:
    """Anything else. ``exc`` is preserved for the activity log."""

    exc: BaseException
    message: str


# ---------- Report payloads (carried by Completed) ---------- #


@dataclass(frozen=True)
class ApplyReport:
    created: list[str]
    skipped: list[str]
    conflicts: list[str]
    dry_run: bool

    @property
    def total(self) -> int:
        return len(self.created) + len(self.skipped) + len(self.conflicts)


@dataclass
class RebuildReport:
    rebuilt: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.rebuilt) + len(self.missing) + len(self.conflicts)


@dataclass(frozen=True)
class ImportReport:
    apkg_path: Path
    notes: int
    media_files: int
    filtered_decks: int
    built_at: datetime


# ---------- Profile resolution ---------- #


def detect_profiles() -> tuple[Path, list[str]]:
    """Return the default Anki base directory and the profile names found there."""
    base = api.default_anki_base()
    if not base.is_dir():
        return base, []
    return base, api.list_profiles(base)


def resolve_collection(anki: AnkiProfileChoice) -> Path | CollectionMissing:
    """Turn a profile choice into a concrete ``collection.anki2`` path."""
    try:
        paths = api.resolve_profile_paths(
            profile=anki.profile,
            collection_override=anki.collection_override,
        )
    except (FileNotFoundError, ValueError) as exc:
        return CollectionMissing(message=str(exc) or "Couldn't locate your Anki collection.")
    return paths.collection


# ---------- Filtered-deck operations ---------- #


def apply_filtered(
    deck_path: Path,
    anki: AnkiProfileChoice,
    *,
    dry_run: bool = False,
    on_log: Callable[[str], None] | None = None,
) -> Completed[ApplyReport] | Locked | CollectionMissing | Failed:
    """Apply ``filtered_decks.yml`` from ``deck_path`` to the user's collection."""
    collection = resolve_collection(anki)
    if isinstance(collection, CollectionMissing):
        return collection

    if on_log is not None:
        on_log(
            f"Resolving Anki collection (profile={anki.profile or 'auto'}, "
            f"override={anki.collection_override or '-'})…"
        )
        on_log(f"Using collection at {collection}")
        on_log(
            "Applying filtered decks (dry run)…" if dry_run else "Applying filtered decks…"
        )

    try:
        report = api.apply_filtered(deck_path, collection, dry_run=dry_run)
    except Exception as exc:
        if _is_locked_error(exc):
            if on_log is not None:
                on_log("Anki is open — close it and try again.")
            return Locked()
        return Failed(exc=exc, message=str(exc) or type(exc).__name__)

    if on_log is not None:
        on_log(
            f"Done — created={len(report.created)}, skipped={len(report.skipped)}, "
            f"conflicts={len(report.conflicts)}."
        )
    return Completed(
        ApplyReport(
            created=list(report.created),
            skipped=list(report.skipped),
            conflicts=list(report.conflicts),
            dry_run=dry_run,
        )
    )


def rebuild_filtered(
    deck_path: Path,
    anki: AnkiProfileChoice,
    *,
    entries: list[str],
    on_log: Callable[[str], None] | None = None,
) -> Completed[RebuildReport] | Locked | CollectionMissing | Failed:
    """Rebuild filtered decks named in ``entries`` against the user's collection.

    The caller is expected to have already read ``filtered_decks.yml`` via
    :mod:`anki_git_ui.domain.deck_metadata` — keeping YAML knowledge out of
    this module.
    """
    if not entries:
        return Completed(RebuildReport())

    collection = resolve_collection(anki)
    if isinstance(collection, CollectionMissing):
        return collection

    if on_log is not None:
        on_log(
            f"Resolving Anki collection (profile={anki.profile or 'auto'}, "
            f"override={anki.collection_override or '-'})…"
        )
        on_log(f"Using collection at {collection}")
        on_log(f"Rebuilding {len(entries)} filtered deck(s)…")

    report = RebuildReport()
    try:
        with open_collection(collection) as col:
            for name in entries:
                did = col.decks.id_for_name(name)
                if did is None:
                    report.missing.append(name)
                    if on_log is not None:
                        on_log(f"  ? {name} (not in your Anki yet)")
                    continue
                deck_obj = col.decks.get(did)
                if int(deck_obj.get("dyn", 0)) != 1:
                    report.conflicts.append(name)
                    if on_log is not None:
                        on_log(f"  ! {name} (a normal deck with this name — skipped)")
                    continue
                col.sched.rebuild_filtered_deck(did)
                report.rebuilt.append(name)
                if on_log is not None:
                    on_log(f"  ✓ {name} (rebuilt)")
    except Exception as exc:
        if _is_locked_error(exc):
            if on_log is not None:
                on_log("Anki is open — close it and try again.")
            return Locked()
        return Failed(exc=exc, message=str(exc) or type(exc).__name__)

    if on_log is not None:
        on_log(
            f"Done — rebuilt={len(report.rebuilt)}, missing={len(report.missing)}, "
            f"conflicts={len(report.conflicts)}."
        )
    return Completed(report)


# ---------- .apkg build ---------- #


def import_deck(
    deck_path: Path,
    out_apkg: Path,
    *,
    ignore_card_overrides: bool = False,
    on_log: Callable[[str], None] | None = None,
) -> (
    Completed[ImportReport]
    | CardOverrideRequired
    | Failed
):
    """Verify the gitified ``deck_path`` and build ``out_apkg`` from it.

    Returns :class:`CardOverrideRequired` when the deck has a ``cards.csv``
    and ``ignore_card_overrides`` is False — the caller surfaces a friendly
    "the deck has per-card placement, want to proceed?" modal and re-invokes
    with the flag set.
    """
    if on_log is not None:
        on_log(f"Validating deck files in {deck_path}…")

    try:
        report = api.verify(deck_path)
    except Exception as exc:
        return Failed(exc=exc, message=str(exc) or type(exc).__name__)

    if not report.ok:
        if on_log is not None:
            for err in report.errors:
                on_log(f"  ! {err}")
        message = (
            "The deck files don't look right. "
            + (report.errors[0] if report.errors else "")
        )
        return Failed(exc=ValueError(message), message=message)

    if on_log is not None:
        on_log(f"  notes={report.notes}, notetypes={report.notetypes}, media={report.media}")
        on_log(f"Building Anki file at {out_apkg}…")

    out_apkg.parent.mkdir(parents=True, exist_ok=True)

    try:
        import_report, _ = api.import_(
            deck_path,
            out_apkg,
            ignore_card_overrides=ignore_card_overrides,
        )
    except CardOverrideError:
        return CardOverrideRequired()
    except Exception as exc:
        return Failed(exc=exc, message=str(exc) or type(exc).__name__)

    built_at = datetime.now(timezone.utc)
    if on_log is not None:
        on_log(
            f"Done — {out_apkg.name} ({import_report.notes} notes, "
            f"{import_report.media_files} media files)."
        )
    return Completed(
        ImportReport(
            apkg_path=out_apkg,
            notes=import_report.notes,
            media_files=import_report.media_files,
            filtered_decks=import_report.filtered_decks,
            built_at=built_at,
        )
    )


# ---------- Desktop process probe ---------- #


def desktop_is_running() -> bool:
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


# ---------- Internal: lock-string matching ---------- #


def _is_locked_error(err: BaseException) -> bool:
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
