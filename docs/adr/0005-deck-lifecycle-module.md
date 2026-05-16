# ADR 0005 — Grow deck_ops into a deck-lifecycle module (or inline it)

**Status:** Accepted — Path A (inline and delete)
**Date:** 2026-05-16

## Context

`domain/deck_ops.py` is 31 lines: one function `delete_deck_files(path) → DeleteOutcome` with safety guards (refuses `/`, `~`, and unresolvable paths). It is called from one site (`deck_detail._finalize_remove_deck`).

Apply the deletion test: if we deleted `deck_ops.py`, the 20-line safety check moves into `deck_detail.py`. Complexity is *displaced*, not *amplified*. One caller can't justify a domain module.

But there is a pattern here that other candidates make visible:

- The deck folder on disk has its own lifecycle: created by a clone, mutated by a pull, removed on user request, possibly recreated.
- The `.builds/<deck>-<sha>.apkg` output has a related lifecycle: created by a build, possibly never; cleaned up alongside the deck.
- Path resolution for both lives in `apkg_paths.py` and inline string manipulation in workers.

This is *deck-lifecycle on disk* — a real concept that today is scattered: a sliver in `deck_ops`, a sliver in `apkg_paths`, a sliver in each worker. ADR-0003 (Subscription Registry) handles the persisted *metadata* lifecycle; this ADR is about the *filesystem* lifecycle.

## Decision

**Two paths; pick one. Both are valid; default is to grow if/when ADR-0003 lands.**

### Path A: Inline and delete (do this if ADR-0003 is deferred)

Move `delete_deck_files` into `deck_detail._finalize_remove_deck`. Delete `domain/deck_ops.py`. Accept that the safety guards live next to their only caller. Total churn: ~25 lines moved.

### Path B: Grow into `deck_lifecycle` (do this once ADR-0003 lands)

Rename `domain/deck_ops.py` to `domain/deck_lifecycle.py`. Absorb:
- The current `delete_deck_files` (rename to `remove_deck_folder`)
- Path-naming logic from `apkg_paths.apkg_output_path` and the `_url_basename` helper from `download_deck_worker`
- A new `prepare_deck_folder(subscription)` (assert local_path is safe to clone into, mkdir parents)
- A new `remove_build_outputs(subscription)` companion to remove the `.apkg` alongside the deck folder

The module's job becomes: "manage all on-disk side-effects against a deck and its build outputs, safely." It is consumed by jobs (ADR-0001), which compose `deck_lifecycle` + `git_ops` + `anki_interop` calls.

## Consequences

**Locality (Path B)** — "what does it mean to delete/move a deck on disk" lives in one module. Path-naming conventions stop drifting between `apkg_paths.py` and worker-internal helpers.

**Leverage (Path B)** — composes cleanly with the Job layer. Jobs become "call this on `deck_lifecycle`, then this on `git_ops`, then this on `anki_interop`, translate outcomes."

**Cost (Path B)** — one more module to navigate. Earns its keep only if Path-A's "inline and delete" is unsatisfying *because* you keep needing the same logic elsewhere.

**Path A** has no leverage gain — it's just removing a pass-through. That's still a net positive if Path B never materialises.

## Recommendation

Sequence with ADR-0003: do **Path A** now (cheap cleanup), then revisit at ADR-0003 implementation time. If `prepare_deck_folder` and `remove_build_outputs` end up wanting to exist anyway, **Path B** materialises naturally.

## Outcome

**Path A** taken. `domain/deck_ops.py` deleted; the `delete_deck_files` helper (renamed to `_delete_deck_files` and the `DeleteOutcome` alias to `_DeleteOutcome`) now lives as a private module helper in [src/anki_git_ui/screens/deck_detail.py](../../src/anki_git_ui/screens/deck_detail.py), alongside its sole caller `_finalize_remove_deck`. Revisit Path B if/when ADR-0003 lands and `prepare_deck_folder` / `remove_build_outputs` start wanting to exist.

## Alternatives considered

- **Leave deck_ops.py as-is.** It fails the deletion test today; leaving it indefinitely codifies a pass-through. Rejected.
