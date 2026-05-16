"""Update an already-downloaded deck: fetch + ff-only pull.

Mutates the passed ``DeckEntry`` to reflect the new HEAD on success.
"""

from __future__ import annotations

from collections.abc import Callable

from ..domain.git_ops import UpdateOutcome, UpdateSucceeded, update_deck as _update_repo
from ..domain.models import DeckEntry


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
