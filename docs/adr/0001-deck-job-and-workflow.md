# ADR 0001 — Deck Job and Workflow

**Status:** Proposed
**Date:** 2026-05-16

## Context

Every deck-action screen reimplements the same orchestration:

1. Set a `_busy` flag and stash `_current_op` as a string.
2. Spawn a worker via `run_worker(..., exclusive=True, name=...)`.
3. In `on_worker_state_changed`, check `event.state in (SUCCESS, ERROR)` and dispatch on `_current_op`.
4. In a giant `_on_worker_success(op, result)`, route by op string and isinstance-check the result type.
5. In a giant `_on_worker_error(op, err)`, isinstance-check the exception (`GitError`, `CardOverrideError`, `FileNotFoundError`) and check `is_locked_error(err)` to decide modal behaviour.

This pattern is duplicated across screens (`deck_detail`, `add_deck`, `dashboard`). The screen ends up owning ~200 lines of routing logic that has nothing to do with the deck-detail view itself.

Workers themselves are shallow: their interface — "call `f(deck, ...)`, get back a result dataclass whose `.error` field carries a `GitError`-or-None, optionally a `.locked: bool`, optionally a `.no_changes: bool`" — leaks every concrete outcome variant into the calling screen.

## Decision

Introduce two new concepts to the operational layer (see [CONTEXT.md](../../CONTEXT.md)):

**Job** — a single async operation against a deck. A Job knows:
- its name (for Textual worker identification and logging),
- its work function (which runs on the worker thread),
- its completion type — a discriminated `JobOutcome` union.

`JobOutcome` variants (the union closed for the foreseeable future):
- `Completed(value)` — the operation succeeded; `value` is operation-specific.
- `AnkiLocked` — the local Anki app is holding `collection.anki2`. Only emitted by jobs that touch Anki.
- `NetworkFailed(message)` — git remote unreachable, DNS, timeout. Only emitted by jobs that touch the network.
- `Failed(exc, kind?)` — everything else; carries the exception for the activity log.

Each job is responsible for *translating* raw exceptions into outcome variants. Screens never see raw `GitError` / `RuntimeError` / `FileNotFoundError`.

**Workflow** — an ordered sequence of jobs with transition rules. Examples currently in code that become workflows:
- *DownloadWorkflow*: `clone → build`
- *UpdateWorkflow*: `update → build (only if commit changed)`
- *ApplyFilteredWorkflow*: `apply-filtered → (offer rebuild)`
- *AnkiLockedRetryWorkflow*: `<wrapped job> → (on AnkiLocked, show modal, retry)`

A workflow is small and stateless from the screen's perspective: the screen calls `workflow.start(on_done=...)`, the workflow drives its jobs to completion, and reports a single terminal outcome back.

The mechanism (Textual worker plumbing, message routing) lives once, in a small framework module. The screen registers a job with a typed `on_done(outcome)` handler at the call site and never touches `_busy` / `_current_op` / `on_worker_state_changed` directly.

## Consequences

**Locality** — the "what should happen after a worker resolves" decision concentrates at the job/workflow call site, not in two giant if/elif chains in the screen. Adding a new deck operation does not require teaching a new screen the dance.

**Leverage** — every screen that runs deck operations (`deck_detail`, `add_deck`, future "Update all" on dashboard) reuses the same Job/Workflow framework. One adapter for the Textual worker layer, used everywhere.

**Tests** — Jobs and Workflows are testable without a TUI:
- Workflow transitions become unit tests against fake jobs that return canned outcomes.
- Lock-retry behaviour becomes a unit test, not a snapshot test.
- "What happens if the user clicks Download twice quickly" becomes a unit test against the job framework.

**Cost** — there are three real deck operations today and a 4th-5th implied. The Workflow concept is justified by 4+ chains (Download, Update, ApplyFiltered, AnkiLockedRetry). With only one chain, this would be premature; with four, it's earning its keep.

## Open questions deferred to implementation

- Whether `AnkiLockedRetryWorkflow` is a workflow or a job decorator. Pick whichever falls out cleaner once two jobs need it.
- Whether `JobOutcome` is a sealed class hierarchy or a tagged union via `match`. Python doesn't have sum types natively; pick whatever the existing dataclass conventions favour.
- Whether `Workflow` is its own class or just a top-level function that composes jobs. Start with functions; promote to a class only when a second workflow needs the same scaffolding.

## Alternatives considered

- **Keep the current pattern, extract helpers.** Pulls a 60-line `_on_worker_error` helper into a free function; doesn't address the underlying shallowness — the screen still owns the state machine. Rejected.
- **A single mega-class `DeckController` that owns every operation.** Concentrates the right code in one place but reintroduces the giant if/elif. Rejected in favour of one Job per operation.
- **Workflows as coroutines.** Tempting (`await clone_job; await build_job`), but Textual's worker model is message-based, and intermixing two concurrency models is its own footgun. Rejected for now.
