"""Update an already-downloaded deck: fetch + ff-only pull.

Mutates the passed ``DeckEntry`` to reflect the new HEAD on success.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from ..domain.git_ops import GitError, fetch, head_branch, head_commit, pull_ff_only
from ..domain.models import DeckEntry


@dataclass
class UpdateResult:
    head_commit: str | None
    head_branch: str | None
    pulled_at: datetime
    no_changes: bool
    error: GitError | None = None


def update_deck(
    deck: DeckEntry,
    *,
    on_log: Callable[[str], None] | None = None,
) -> UpdateResult:
    """Fetch and fast-forward-pull ``deck.local_path``.

    Friendly :class:`anki_git_ui.domain.git_ops.GitError` failures are
    caught and returned via ``UpdateResult.error`` (so Textual doesn't
    print a traceback). Caller checks ``result.error`` and shows a modal.
    """
    repo: Path = deck.local_path
    previous = deck.last_pulled_commit
    try:
        if on_log is not None:
            on_log(f"git -C {repo} fetch --prune")
        fetch(repo, on_line=on_log)

        if on_log is not None:
            on_log(f"git -C {repo} pull --ff-only")
        pull_ff_only(repo, on_line=on_log)
    except GitError as exc:
        if on_log is not None:
            on_log(f"Update failed: {exc}")
        return UpdateResult(
            head_commit=None,
            head_branch=None,
            pulled_at=datetime.now(timezone.utc),
            no_changes=False,
            error=exc,
        )

    sha = head_commit(repo)
    branch = head_branch(repo)
    pulled_at = datetime.now(timezone.utc)

    deck.branch = branch or deck.branch
    deck.last_pulled_commit = sha
    deck.last_pulled_at = pulled_at

    no_changes = sha == previous

    if on_log is not None:
        if no_changes:
            on_log("Already up to date.")
        else:
            short = sha[:7] if sha else "?"
            on_log(f"Updated to {short}.")

    return UpdateResult(
        head_commit=sha,
        head_branch=branch,
        pulled_at=pulled_at,
        no_changes=no_changes,
    )
