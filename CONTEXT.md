# Context

Domain vocabulary for `anki-git-ui`. This file is the **glossary**: what the words in the codebase mean. For where things *live*, see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). For *why* things are shaped a certain way, see [docs/adr/](docs/adr/).

When a term in the codebase isn't here, either it's incidental or this file is stale — promote it.

## Domain concepts

**Deck** — a tracked anki-gitify repo. Identity is the pair `(url, local_path)`. A deck has *persisted* metadata (branch, last pulled commit, last built `.apkg`) and *runtime* status (downloaded / up-to-date / updates-available). See **Subscription** for the persisted half.

**Subscription** — the user's persisted intent to track a deck. Stored as one `[[decks]]` table in `config.toml`. Fields: `nickname`, `url`, `local_path`, `branch`, `last_pulled_commit`, `last_pulled_at`, `last_built_commit`, `last_built_apkg`, `last_built_at`.

**Deck status** — the live, session-only runtime state of a deck: `NOT_DOWNLOADED`, `UP_TO_DATE`, `UPDATES_AVAILABLE`, `LOCALLY_MODIFIED`, `DIVERGED`, `UNKNOWN`. Derived from persisted metadata plus on-demand checks; never written to disk.

**Build output** — the `.apkg` file produced from a deck at a specific commit. Stored at `<save folder>/.builds/<deck-basename>-<short-sha>.apkg`. The path is keyed on commit sha so "already built this exact version" is unambiguous.

**Anki interop** — the small surface for talking to the user's local Anki: resolving the collection path from a profile, applying filtered-deck definitions, rebuilding filtered decks. All goes through `anki-gitify`'s SDK.

**Anki desktop lock** — the exclusive hold the local Anki app keeps on `collection.anki2` while it's open. Any interop call against the same collection fails with a "locked" / "already open" / "currently syncing" error until Anki is closed.

## Operational concepts

**Job** — a single async operation against a deck: clone, update, build, check-for-updates, apply-filtered, rebuild-filtered. A job runs on a background worker thread, may stream log lines, and resolves to a *typed outcome*. See [ADR-0001](docs/adr/0001-deck-job-and-workflow.md).

**Workflow** — an ordered sequence of jobs with transition rules. Examples: "after download, build the `.apkg`"; "after update, build only if the commit changed"; "after apply-filtered, offer rebuild." Workflows are how screens compose multi-step user intents without owning per-step state machines.

**Job outcome** — the discriminated result of a job: `Completed(value)`, `AnkiLocked`, `NetworkFailed`, `Failed(exc)`. Replaces ad-hoc "`result.error` + isinstance chain" patterns.

**Activity log** — the streaming, per-screen log surface (rendered by `LogPanel`). Workers write to it via `on_log` callbacks supplied at job start.

## Layers

```
screens     UI + workflows                     uses jobs, never workers directly
workers     job implementations                 uses domain, never the SDK directly past anki_interop
domain      pure logic + thin interop facades   no Textual imports
```

The thin layer-skipping rule: a screen never imports `subprocess` or `anki_gitify.api`. A worker never imports `textual`. A domain module never imports either UI or SDK internals beyond its own facade.

## Names this codebase deliberately avoids

- *Service / component / API / boundary* — see [docs/adr/0001](docs/adr/0001-deck-job-and-workflow.md) for the architectural vocabulary used in design discussions.
- *Action / task* (as nouns for jobs) — too generic; collides with Textual's `Action` and Python's `asyncio.Task`. Use **Job**.
