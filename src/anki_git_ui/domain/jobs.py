"""Job outcome union — the discriminated result of a single async deck operation.

See [docs/adr/0001-deck-job-and-workflow.md](../../../docs/adr/0001-deck-job-and-workflow.md)
for the design rationale.

The variants are intentionally flat and closed:

- :class:`Completed` (``Completed[T]``) — success; ``value`` is operation-specific
  (e.g. an :class:`anki_interop.ImportReport`, a :class:`git_ops.CloneSucceeded`).
- :class:`AnkiLocked` — the local Anki app is holding ``collection.anki2``. Only
  emitted by jobs that touch Anki.
- :class:`NetworkFailed` — git remote unreachable, DNS, timeout. Only emitted by
  jobs that touch the network.
- :class:`Failed` — anything else; carries the exception for the activity log
  and an optional ``kind`` tag for operation-specific user-facing flows
  (``"card_override"``, ``"collection_missing"``, ``"non_anki_gitify"`` …).

Pure data — no Textual imports. The screen-side machinery for running jobs and
routing outcomes lives in :mod:`anki_git_ui.jobs`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class Completed(Generic[T]):
    """Success — ``value`` is operation-specific (often a report dataclass)."""

    value: T


@dataclass(frozen=True)
class AnkiLocked:
    """The local Anki app is holding ``collection.anki2`` — close Anki and retry."""


@dataclass(frozen=True)
class NetworkFailed:
    """Git remote unreachable, DNS failure, timeout. ``message`` is user-facing."""

    message: str


@dataclass(frozen=True)
class Failed:
    """Anything else — carries the exception for the log and an optional kind tag.

    ``kind`` is a free-form discriminator for operation-specific failure modes
    that need their own user flow:

    - ``"card_override"`` — the deck has a ``cards.csv`` and the build needs
      explicit user consent to ignore it.
    - ``"collection_missing"`` — couldn't resolve the user's Anki collection.
    - ``"non_anki_gitify"`` — the remote URL doesn't point at a gitified deck.
    - ``None`` — generic failure; render the message in an error modal.
    """

    exc: BaseException
    message: str
    kind: str | None = None


JobOutcome = Completed[T] | AnkiLocked | NetworkFailed | Failed


__all__ = [
    "AnkiLocked",
    "Completed",
    "Failed",
    "JobOutcome",
    "NetworkFailed",
]
