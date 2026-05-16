# ADR 0003 — Separate Subscription (persisted) from DeckRuntime (session)

**Status:** Proposed
**Date:** 2026-05-16

## Context

Today `DeckEntry` is a single dataclass with both persisted fields (url, branch, last_pulled_commit, last_pulled_at, last_built_*) and runtime fields (`status`, `updates_available`). The same instance lives in `config.Config.decks` (persisted) and `state.AppState.decks` (in-memory). When a worker mutates the instance — e.g. `download_deck` sets `last_pulled_commit` and `last_pulled_at` — the screen has to remember to call `app.config.save()`.

Looking at `deck_detail.on_worker_success`:

- The `download` branch calls `self.app.config.save()` after mutating `_deck.status`.
- The `update` branch calls `self.app.config.save()` after mutating `_deck.status` and `_deck.updates_available`.
- The `build` branch calls `self.app.config.save()` after the worker mutated `last_built_*`.
- The `check` branch does *not* call `save()` — but it also doesn't mutate persisted fields, so it's accidentally correct.

The rule "if you mutate a persisted field, call save()" is not enforced anywhere. The current code is correct by attention; it will silently drift the next time a new persisted field is added without an explicit save.

## Decision

Split `DeckEntry` into two dataclasses with different lifetimes:

**`Subscription`** — persisted. Holds `nickname`, `url`, `local_path`, `branch`, `last_pulled_commit`, `last_pulled_at`, `last_built_commit`, `last_built_apkg`, `last_built_at`. Treated as immutable from screens; mutations go through a single seam.

**`DeckRuntime`** — session-only. Holds `status`, `updates_available`. Lives in `AppState`; freely mutable.

Mutations to `Subscription` go through a single object — call it `SubscriptionRegistry` — whose interface is:

- `list() → list[Subscription]`
- `add(subscription)` — persists immediately.
- `update(subscription_id, **changes) → Subscription` — applies changes, persists immediately, returns the new value.
- `remove(subscription_id)` — persists immediately.

The registry holds the in-memory list and the on-disk file in lock-step. Every mutating method writes through to TOML. There is no "save later" path — saving is inseparable from mutating.

Workers that today mutate `DeckEntry` in place instead return their persisted changes as part of their `JobOutcome` value (e.g. `CloneSucceeded(commit, branch, pulled_at)`). The screen / workflow applies those changes via `registry.update(...)`.

## Consequences

**Locality** — "this changed, persist it" lives in one method, not in every screen branch. Adding a new persisted field requires touching one place (`Subscription`) and trusting `registry.update` to write it.

**Leverage** — workers stop mutating callers' inputs in-place. They become honest pure-ish functions: take a `Subscription` snapshot, return a result describing what changed. Workers become easier to test (no shared-mutable-state setup) and easier to compose into workflows (ADR-0001).

**Tests** — a single "mutating any field through `registry.update` ends up on disk" test replaces a per-branch audit of `config.save()` call sites. Workers test against snapshot inputs without needing a fixture for the global state singleton.

**Cost** — call sites that currently read `deck.status` and `deck.last_pulled_commit` interchangeably now read two different objects. Pairing them up (e.g. a `DeckView` namedtuple for UI rendering) is a small one-time chore.

## Open questions deferred to implementation

- Subscription identity. Today it's the `(url, local_path)` pair implicitly. Could be a synthetic `id: str` (a UUID), or `url` alone. The registry's `update` and `remove` need a stable identifier; pick one in implementation.
- Whether `DeckRuntime` is a separate map keyed by subscription id, or embedded in a `SubscriptionView` wrapper. Pick whichever the UI rendering prefers.

## Alternatives considered

- **Keep `DeckEntry`, add a `mutate(deck, **changes)` helper that writes back.** Cheaper, but doesn't make persistence non-optional — call sites can still skip the helper. Rejected because the goal is to make "forgot to save" impossible, not merely easier to remember.
- **Mark persisted fields via metadata and have a `__setattr__` hook on `DeckEntry`.** Too magical; reads like a foot-gun in code review. Rejected.
- **Status quo + a lint rule.** Defers the problem to tooling that doesn't exist. Rejected.
