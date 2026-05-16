"""Update an already-downloaded deck: fetch + ff-only pull.

Mutates the passed ``DeckEntry`` to reflect the new HEAD on success.
"""

from __future__ import annotations

from collections.abc import Callable

from ..domain.git_ops import (
    GitFailureKind,
    UpdateFailed,
    UpdateOutcome,
    UpdateSucceeded,
    update_deck as _update_repo,
)
from ..domain.jobs import Completed, Failed, JobOutcome, NetworkFailed
from ..domain.models import DeckEntry
from ..jobs import Job


def update_deck(
    deck: DeckEntry,
    *,
    on_log: Callable[[str], None] | None = None,
) -> UpdateOutcome:
    """Fetch and fast-forward-pull ``deck.local_path``.

    Mutates ``deck`` in place on success. The caller reads
    :class:`anki_git_ui.domain.git_ops.UpdateSucceeded.advanced` to know
    whether HEAD moved, and :class:`UpdateFailed.message` for failure modals.
    """
    outcome = _update_repo(deck.local_path, on_log=on_log)
    if isinstance(outcome, UpdateSucceeded):
        deck.branch = outcome.branch or deck.branch
        deck.last_pulled_commit = outcome.commit
        deck.last_pulled_at = outcome.pulled_at
    return outcome


def update_deck_job(
    deck: DeckEntry,
    *,
    on_log: Callable[[str], None] | None = None,
) -> Job[UpdateSucceeded]:
    """Build a :class:`Job` that updates ``deck`` and translates the result
    to a :class:`JobOutcome`.

    Network failures surface as :class:`NetworkFailed`; everything else as
    :class:`Failed` with the ``GitFailureKind`` as ``kind``.
    """

    def _work() -> JobOutcome[UpdateSucceeded]:
        outcome = update_deck(deck, on_log=on_log)
        if isinstance(outcome, UpdateSucceeded):
            return Completed(outcome)
        return _update_failed_to_job_outcome(outcome)

    return Job(name="update", work=_work)


def _update_failed_to_job_outcome(failed: UpdateFailed) -> JobOutcome:
    if failed.kind is GitFailureKind.NETWORK:
        return NetworkFailed(message=failed.message)
    return Failed(
        exc=RuntimeError(failed.message),
        message=failed.message,
        kind=failed.kind.value,
    )
