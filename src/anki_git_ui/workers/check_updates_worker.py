"""Fetch from remote and return a recent-commit list for the updates panel."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from ..domain.git_ops import GitError, fetch, head_branch, recent_commits
from ..domain.models import DeckEntry


@dataclass
class CommitLine:
    """One row in the UpdatesPanel.

    The subject is the prominent part; date and short sha are rendered as
    muted metadata. ``is_new`` flags commits above the local HEAD that the
    user hasn't pulled yet, so the panel can highlight them.
    """

    subject: str
    date: str
    short: str
    is_new: bool


@dataclass
class CheckUpdatesResult:
    commits: list[CommitLine] = field(default_factory=list)
    branch: str | None = None
    error: GitError | None = None


def check_for_updates(
    deck: DeckEntry,
    *,
    limit: int = 20,
    on_log: Callable[[str], None] | None = None,
) -> CheckUpdatesResult:
    """``git fetch`` and return the last ``limit`` commits on the remote branch.

    Each commit is flagged ``is_new=True`` if it sits ABOVE the local pulled
    commit in the history (i.e. not yet on the user's machine). Commits at or
    below the local commit are flagged ``is_new=False`` so the UI can render
    them dimmed.

    Friendly :class:`GitError` failures are returned via ``result.error`` so
    Textual treats the worker as successful and the UI can surface a notice
    instead of a traceback.
    """
    try:
        fetch(deck.local_path, on_line=on_log)
    except GitError as exc:
        if on_log is not None:
            on_log(f"Fetch failed: {exc}")
        return CheckUpdatesResult(error=exc)

    branch = head_branch(deck.local_path) or deck.branch
    raw = recent_commits(
        deck.local_path, ref=f"origin/{branch}", limit=limit
    )

    last_pulled = deck.last_pulled_commit
    commits: list[CommitLine] = []
    seen_local = False
    for c in raw:
        if seen_local:
            is_new = False
        elif last_pulled and c.sha == last_pulled:
            is_new = False
            seen_local = True
        else:
            is_new = True
        commits.append(
            CommitLine(subject=c.subject, date=c.date, short=c.short, is_new=is_new)
        )
    return CheckUpdatesResult(commits=commits, branch=branch)
