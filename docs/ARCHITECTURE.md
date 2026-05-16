# Architecture

This document is a **navigation aid**: where the code lives. Sibling docs do related but distinct jobs:

- [**CONTEXT.md**](../CONTEXT.md) — the **glossary**: what the words in the codebase mean (Deck, Subscription, Job, Workflow, Anki interop…).
- [**docs/adr/**](adr/) — **architectural decision records**: why things are shaped a certain way, what was rejected, and the open questions.
- [**CLAUDE.md**](../CLAUDE.md) — project conventions and gotchas for contributors.

The code is the source of truth; this file describes the **shape** so a fresh reader (or agent) knows where to start.

## Three layers

```
┌─────────────────────────────────────────────────┐
│ screens/   user flows, layout, key bindings     │  UI
│ widgets/   reusable components inside screens   │
├─────────────────────────────────────────────────┤
│ workers/   async I/O: git pull, build .apkg…    │  glue
├─────────────────────────────────────────────────┤
│ domain/    pure logic — models, git_ops, etc.   │  pure
└─────────────────────────────────────────────────┘
```

UI never blocks: anything that touches disk, the network, or `anki-gitify` runs in a `workers/` task and reports back to the screen via Textual's worker messages. `domain/` stays import-clean of Textual so it can be unit-tested without a TUI harness.

## Modules

### Top-level (`src/anki_git_ui/`)

- **`app.py`** — `AnkiGitUIApp`. Registers screens, owns global CSS and key bindings, holds the `AppState` instance.
- **`__main__.py`** — Entry point for both `python -m anki_git_ui` and the `anki-git-ui` console script. Also implements `ANKI_GIT_UI_SMOKE=1`, a non-interactive smoke used by the packaging pipeline.
- **`config.py`** — On-disk persistence. Writes/reads a TOML file under the OS-appropriate config dir (via `platformdirs`). Stores subscribed decks and user settings.
- **`state.py`** — In-memory `AppState` dataclass. The running app holds one instance; screens read/mutate it. Distinct from `config.py`: this is session state, not persistence.
- **`jobs.py`** — Job/Workflow framework: `Job`, `run_job`, `dispatch_job_event`, `run_with_anki_locked_retry`. Wraps Textual's worker layer so screens don't own per-op state machines ([ADR-0001](adr/0001-deck-job-and-workflow.md)).

### `screens/` — user flows

One screen per top-level user goal. Each owns its layout, local bindings, and the orchestration of any workers it spawns.

| Screen | Purpose |
|---|---|
| `welcome.py` | First-run onboarding (pick Anki profile) |
| `dashboard.py` | Main view: list of subscribed decks, actions |
| `add_deck.py` | Two-step wizard: paste GitHub URL → name + folder → save & download |
| `deck_detail.py` | Per-deck status, logs, update/rebuild actions |
| `settings.py` | Theme, default save folder, Anki profile |
| `help.py` | Key bindings, troubleshooting |
| `modals.py` | Shared modal dialogs (confirm, error) |

### `workers/` — job implementations

Each module owns one deck operation and exposes a `*_job(...) -> Job[...]` factory that the framework in `jobs.py` runs on a worker thread. The legacy plain functions (`download_deck`, `make_apkg`, …) stay alongside the factories — they remain useful for unit tests that want the concrete return type — but screens consume the `*_job` factories ([ADR-0001](adr/0001-deck-job-and-workflow.md)).

| Worker | Job factory | Job |
|---|---|---|
| `download_deck_worker` | `download_deck_job` | `git clone` a deck repo to the local save folder |
| `update_deck_worker` | `update_deck_job` | `git pull` an existing deck |
| `make_apkg_worker` | `make_apkg_job` | Build a `.apkg` from a deck repo (delegates to `anki_interop.import_deck`) |
| `check_updates_worker` | `check_for_updates_job` | Periodic / on-demand check for remote changes across all decks |
| `filtered_decks_worker` | `apply_filtered_decks_job` / `rebuild_filtered_decks_job` | Apply / rebuild filtered decks against the user's collection (delegates to `anki_interop`) |

Since [ADR-0004](adr/0004-anki-interop-facade.md), every worker that touches Anki is a thin translation layer: it constructs the call arguments and returns an outcome from `domain/anki_interop.py`. Since [ADR-0001](adr/0001-deck-job-and-workflow.md), the `*_job` factory translates that concrete outcome into a `JobOutcome` from `domain/jobs.py` — `Locked` → `AnkiLocked`, network-kind git failures → `NetworkFailed`, etc. Workers never catch `Exception` or string-match error messages.

### `widgets/` — reusable UI

- `deck_card.py` — the card row used by the dashboard
- `log_panel.py` — scrolling log view used by deck_detail and add_deck
- `updates_panel.py` — "updates available" summary widget

### `domain/` — pure logic (no Textual)

- `models.py` — `DeckEntry`, `DeckStatus`, `AnkiProfileChoice` dataclasses
- `jobs.py` — `JobOutcome` union (`Completed[T]`, `AnkiLocked`, `NetworkFailed`, `Failed`) shared by every job ([ADR-0001](adr/0001-deck-job-and-workflow.md))
- `git_ops.py` — outcome-returning git operations: `clone_deck`, `update_deck`, `list_recent_commits`, `verify_anki_gitify_remote` ([ADR-0002](adr/0002-collapsed-git-interface.md))
- `anki_interop.py` — the **only** module that imports `anki_gitify.api`. Outcome-returning facade: `apply_filtered`, `rebuild_filtered`, `import_deck`, `resolve_collection`, `detect_profiles`, `desktop_is_running` ([ADR-0004](adr/0004-anki-interop-facade.md))
- `deck_ops.py` — deck-level operations (compose git_ops + apkg_paths)
- `deck_metadata.py` — deck-shape knowledge read from the gitified directory (today: `filtered_decks.yml`)
- `apkg_paths.py` — where the built `.apkg` lives on disk
- `theme.py` — light/dark/system theme resolution via `darkdetect`
- `text_utils.py` — string helpers (nickname slugs, etc.)

## Data flow: add a deck

Happy path for the most common flow:

1. User opens `AddDeckScreen`, pastes a GitHub URL.
2. Screen calls `domain.git_ops.verify_anki_gitify_remote()` (in a worker — does a blobless probe-clone) — bad URLs and non-anki-gitify repos surface here.
3. User confirms name + folder. Screen persists the new `DeckEntry` via `config.save()` and pushes the deck to `AppState.decks`.
4. Screen spawns `download_deck_worker` → `git clone` to the chosen folder.
5. On completion, screen spawns `make_apkg_worker` → `anki-gitify` builds the `.apkg`.
6. User pops back to the dashboard, which re-reads `AppState.decks` and renders the new card.

## Where state lives

- **On disk (survives restart):** `config.py` → TOML at the platform config dir. Subscribed decks, default save folder, theme, Anki profile choice.
- **In memory (session only):** `state.py` → `AppState`. Current deck list (mirrors disk + worker-side mutations), runtime flags like `is_first_run`, derived caches.
- **Filesystem artifacts:** cloned deck repos under the user's save folder (default `~/AnkiDecks/`). Built `.apkg` files live alongside (see `apkg_paths.py`).

## Testing

`pytest` with `pytest-textual-snapshot`. Tests mirror the source layout (`test_config.py`, `test_git_ops.py`, `test_add_deck_flow.py`, etc.). Snapshot images live in `tests/__snapshots__/`; intentional UI changes need `pytest --snapshot-update` and a review of `snapshot_report.html`.
