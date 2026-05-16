# ADR 0004 — Concentrate Anki interop in a facade module

**Status:** Accepted
**Date:** 2026-05-16
**Implemented:** 2026-05-16

## Context

Three things conspire to scatter Anki-specific knowledge across the codebase:

1. **`anki_gitify.api` and `anki.errors.DBError` calls** appear in `workers/filtered_decks_worker.py`, `workers/make_apkg_worker.py`, `domain/profile_ops.py`.
2. **The "Anki desktop has the collection locked" condition** is detected by string-matching (`"locked"`, `"already open"`, `"currently syncing"`) inside `filtered_decks_worker.is_locked_error`. That function is also imported and called from `screens/deck_detail.py` to decide modal behaviour, which means error-string brittleness leaks into a screen.
3. **`is_anki_desktop_running()`** uses `pgrep` to detect the running app — a different mechanism from lock detection. It's defined in `filtered_decks_worker.py` but is conceptually unrelated to filtered decks.

The current shape forces every worker that touches the SDK to repeat the same try/except, re-implement the same lock detection, and pick its own way to surface the result.

## Decision

Introduce a `domain/anki_interop.py` module that wraps every call into `anki-gitify`'s SDK. Its public interface returns *structured outcomes*, never raw exceptions:

- `apply_filtered(deck_path, profile_choice, *, dry_run, on_log) → AnkiOutcome[ApplyReport]`
- `rebuild_filtered(deck_path, profile_choice, *, on_log) → AnkiOutcome[RebuildReport]`
- `import_deck(deck_path, out_apkg, *, ignore_card_overrides, on_log) → AnkiOutcome[ImportReport]`
- `resolve_collection(profile_choice) → Path | CollectionMissing`
- `desktop_is_running() → bool`

Where `AnkiOutcome[T]` is:
- `Completed(T)`
- `Locked` — the collection is held by Anki desktop
- `CollectionMissing(message)` — profile/path resolution failed
- `CardOverrideRequired` — specific to `import_deck`: the deck has a `cards.csv` and the caller didn't pass `ignore_card_overrides=True`. The user-facing flow is "ask, then retry," not "show an error," so it gets its own variant rather than being rolled into `Failed`.
- `Failed(exc, message)` — anything else

The string-matching that decides `Locked` lives once inside `anki_interop`'s `_is_locked_error` helper. Workers stop catching `Exception` and never see `RuntimeError`-with-magic-string. `is_locked_error` is deleted from `filtered_decks_worker` along with the screen's import of it.

## Consequences

**Locality** — lock detection (the most brittle line of code in the app) lives in one method with one test. Any future Anki-touching feature plugs into the same facade.

**Leverage** — composes with ADR-0001: a job that touches Anki returns a `JobOutcome` whose `Failed` branch is built from `anki_interop`'s outcome. The screen-level "show `AnkiLockedModal`, offer retry" lives in the workflow layer (also ADR-0001), not in `_on_worker_error`.

**Tests** — `is_locked_error` becomes a unit test against synthetic exception messages. Outcome-to-JobOutcome translation is a pure function with a small table of cases.

**Cost** — `filtered_decks_worker.py` shrinks dramatically (the YAML reading for "list filtered decks" moves into a small `domain/deck_metadata.py` helper, since it's deck-shape knowledge, not Anki interop).

## Open questions deferred to implementation

- ~~Whether `profile_ops.py` is absorbed into `anki_interop` or stays as a sibling.~~ **Resolved:** absorbed. `detect_profiles` and `resolve_collection` live in `anki_interop`; `domain/profile_ops.py` was deleted.

## Implementation notes

- The `rebuild_filtered` facade takes a pre-resolved `entries: list[str]` rather than re-reading `filtered_decks.yml` itself. The YAML reading lives in `domain/deck_metadata.py` (`list_filtered_deck_names`); both the worker and the deck-detail screen go through it.
- `CardOverrideRequired` is import-specific. It only appears in `import_deck`'s return type, not on `apply_filtered` / `rebuild_filtered`.
- The worker layer keeps minimal precondition checks (e.g. `filtered_decks.yml` exists) and surfaces those as `Failed(FileNotFoundError, message)` rather than raising — preserving the "workers never raise" rule.

## Alternatives considered

- **Leave the SDK calls in their workers, just centralise `is_locked_error`.** Half-measure. The string-match brittleness moves but the structural problem (workers do their own SDK try/except) stays. Rejected.
- **Wrap each SDK call individually as it gets touched.** Doesn't crystallise the facade; the seam never forms. Rejected.
