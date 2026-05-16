"""High-level orchestration for "download a deck for the first time".

Wraps :func:`anki_git_ui.domain.git_ops.clone_deck` with the bookkeeping the
dashboard cares about: stamping the resulting HEAD sha, branch, and pulled-at
timestamp onto the :class:`DeckEntry`. Pure function — no Textual imports —
so it can be tested without spinning up the app.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from ..domain.git_ops import (
    CloneFailed,
    CloneOutcome,
    CloneProgress,
    CloneSucceeded,
    GitFailureKind,
    clone_deck,
)
from ..domain.jobs import Completed, Failed, JobOutcome, NetworkFailed
from ..domain.models import DeckEntry
from ..jobs import Job


def download_deck(
    deck: DeckEntry,
    *,
    on_log: Callable[[str], None] | None = None,
    on_progress: Callable[[CloneProgress], None] | None = None,
) -> CloneOutcome:
    """Clone ``deck.url`` into ``deck.local_path`` and stamp HEAD onto ``deck``.

    Mutates the passed ``deck`` in place on success — fills in ``branch``,
    ``last_pulled_commit``, and ``last_pulled_at``. On failure the deck is
    left untouched and the caller can read ``CloneFailed.message`` to render
    a modal.
    """
    outcome = clone_deck(
        deck.url, deck.local_path, on_log=on_log, on_progress=on_progress
    )
    if isinstance(outcome, CloneSucceeded):
        deck.branch = outcome.branch or deck.branch
        deck.last_pulled_commit = outcome.commit
        deck.last_pulled_at = outcome.pulled_at
    return outcome


def download_deck_job(
    deck: DeckEntry,
    *,
    on_log: Callable[[str], None] | None = None,
    on_progress: Callable[[CloneProgress], None] | None = None,
) -> Job[CloneSucceeded]:
    """Build a :class:`Job` that clones ``deck`` and translates the result to a
    :class:`JobOutcome`.

    Network failures (DNS, timeout, host unreachable) surface as
    :class:`NetworkFailed`; everything else (auth, repo not found, unsupported
    URL, unknown) as :class:`Failed` carrying the ``GitFailureKind`` as
    ``kind`` so callers can branch on it (e.g. the add-deck flow's
    ``"non_anki_gitify"`` handling).
    """

    def _work() -> JobOutcome[CloneSucceeded]:
        outcome = download_deck(deck, on_log=on_log, on_progress=on_progress)
        if isinstance(outcome, CloneSucceeded):
            return Completed(outcome)
        return _git_failed_to_job_outcome(outcome)

    return Job(name="download", work=_work)


def _git_failed_to_job_outcome(failed: CloneFailed) -> JobOutcome:
    if failed.kind is GitFailureKind.NETWORK:
        return NetworkFailed(message=failed.message)
    return Failed(
        exc=RuntimeError(failed.message),
        message=failed.message,
        kind=failed.kind.value,
    )


def _url_basename(url: str) -> str:
    """Last URL path segment with any trailing slash and ``.git`` suffix stripped.

    Pure string operation — does not validate that ``url`` is well-formed.
    Empty / slash-only inputs return ``""``; callers supply their own default.
    """
    name = url.rstrip("/").split("/")[-1]
    if name.endswith(".git"):
        name = name[:-4]
    return name


def deck_local_path(default_save_folder: Path, url: str) -> Path:
    """Default ``local_path`` for a freshly added deck — basename of the URL."""
    return default_save_folder / (_url_basename(url) or "deck")


def deck_nickname(url: str) -> str:
    """Default nickname inferred from the URL basename."""
    return _url_basename(url).replace("-", " ").replace("_", " ").strip().title() or "Deck"
