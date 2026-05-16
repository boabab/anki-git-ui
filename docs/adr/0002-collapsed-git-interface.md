# ADR 0002 — Collapse the git_ops interface

**Status:** Proposed
**Date:** 2026-05-16

## Context

`domain/git_ops.py` is 602 lines and exposes nine top-level operations: `detect_git`, `verify_remote`, `verify_gitify_repo`, `clone`, `fetch`, `pull_ff_only`, `head_commit`, `head_branch`, `recent_commits`, plus a hierarchy of seven `GitError` subclasses and a `_classify_clone_error` mapper.

Callers compose these primitives:
- `download_deck_worker` calls `clone → head_commit → head_branch` and constructs a `DownloadResult`.
- `update_deck_worker` calls `fetch → pull_ff_only → head_commit → head_branch` and constructs an `UpdateResult`.
- `check_updates_worker` calls `fetch → head_branch → recent_commits` and constructs a `CheckUpdatesResult`.

Each composition repeats the same try/except over `GitError`, the same "if no error, then capture HEAD" sequence, and the same `pulled_at = datetime.now(timezone.utc)` bookkeeping. The shared interface — "primitives + the rule about composing them" — is the test surface that gets re-tested every time we touch a worker.

The error hierarchy (seven `GitError` subclasses) is granular, but screens still re-check by isinstance and by message substring (the `"locked"` matcher), so the granularity isn't earning its keep at the seam where it matters.

## Decision

Collapse `git_ops`'s interface from a primitive kit to a small set of *high-level outcomes*:

**`clone_deck(url, dest, *, on_log, on_progress) → CloneOutcome`** where `CloneOutcome` is:
- `CloneSucceeded(commit, branch, pulled_at)`
- `CloneFailed(kind, message)` with `kind ∈ {auth, network, repo_not_found, not_anki_gitify, unsupported_url, unknown}`

**`update_deck(repo, *, on_log) → UpdateOutcome`** where `UpdateOutcome` is:
- `UpdateSucceeded(commit, branch, pulled_at, advanced)` (`advanced: bool` replaces `no_changes`)
- `UpdateFailed(kind, message)` with the same `kind` enum

**`list_recent_commits(repo, ref, *, limit) → CommitsOutcome`** — pure read of an existing repo.

**`verify_anki_gitify_remote(url) → RemoteOutcome`** — the lightweight pre-clone probe.

The internal primitives (subprocess plumbing, progress parsing, error classification) become private to `git_ops` and are not part of its public interface. The seven-class `GitError` hierarchy is replaced by a single `kind` enum on the outcome — string messages live in the outcome itself, ready to render.

## Consequences

**Locality** — "after a clone, capture HEAD and timestamp" lives in `clone_deck` once, not in three workers. Lock-string matching for non-Anki errors disappears from the screen.

**Leverage** — workers shrink to "call `clone_deck`, translate `CloneOutcome` to a `JobOutcome` (ADR-0001)". The git_ops interface a worker has to learn is four functions, not nine plus the rules for composing them.

**Tests** — git_ops becomes testable with a single test per outcome variant: assert that `CloneFailed(kind="auth", ...)` is produced for an auth-error stderr. Workers test against fake `*Outcome` values, not mocked `subprocess.run`.

**Cost** — `verify_remote`, `head_commit`, `head_branch`, `recent_commits` as standalone primitives go away. Any future operation that genuinely needs raw HEAD reading (e.g. a "show diff" feature) re-introduces a primitive at that point; today there are zero callers outside the workers we control.

## Relationship to ADR-0001

ADR-0001's `JobOutcome` and this ADR's `CloneOutcome` / `UpdateOutcome` overlap intentionally. The mapping is:

| git_ops outcome variant | JobOutcome variant |
|---|---|
| `CloneSucceeded` | `Completed(value)` |
| `CloneFailed(kind=network)` | `NetworkFailed(message)` |
| `CloneFailed(kind=auth \| repo_not_found \| ...)` | `Failed(exc=..., kind=...)` |

`git_ops` does not know about `JobOutcome` — that's the worker's translation step. This keeps `domain/` free of operational-layer concepts.

## Alternatives considered

- **Move subprocess plumbing to `workers/` or a new `infra/`.** Solves "domain isn't pure" but doesn't shrink the interface. Worth doing if tests benefit, but it's not the load-bearing change. Defer.
- **Keep primitives, add high-level convenience wrappers alongside.** Doesn't actually collapse anything — the surface grows. Rejected.
- **Keep the `GitError` hierarchy, just route via subclass at the seam.** Doesn't help callers: they still need to match every subclass. The `kind`-enum approach is friendlier and easier to render. Rejected.
