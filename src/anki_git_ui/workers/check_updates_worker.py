"""Fetch from remote and return a recent-commit list for the updates panel."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from ..domain.git_ops import CommitsFailed, CommitsListed, GitFailureKind, list_recent_commits
from ..domain.jobs import Completed, Failed, JobOutcome, NetworkFailed
from ..domain.models import DeckEntry
from ..jobs import Job


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
    failure: CommitsFailed | None = None


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
    """
    outcome = list_recent_commits(
        deck.local_path, fetch_first=True, limit=limit, on_log=on_log
    )
    if isinstance(outcome, CommitsFailed):
        if on_log is not None:
            on_log(f"Fetch failed: {outcome.message}")
        return CheckUpdatesResult(failure=outcome)

    assert isinstance(outcome, CommitsListed)
    last_pulled = deck.last_pulled_commit
    commits: list[CommitLine] = []
    seen_local = False
    for c in outcome.commits:
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
    return CheckUpdatesResult(commits=commits, branch=outcome.branch or deck.branch)


def check_for_updates_job(
    deck: DeckEntry,
    *,
    limit: int = 20,
    on_log: Callable[[str], None] | None = None,
) -> Job[CheckUpdatesResult]:
    """Build a :class:`Job` that fetches the remote and lists recent commits.

    A successful listing — even one that reveals no new commits — returns
    :class:`Completed`. A network failure during the fetch step is reported as
    :class:`NetworkFailed`; everything else falls through to :class:`Failed`.
    """

    def _work() -> JobOutcome[CheckUpdatesResult]:
        result = check_for_updates(deck, limit=limit, on_log=on_log)
        if result.failure is None:
            return Completed(result)
        if result.failure.kind is GitFailureKind.NETWORK:
            return NetworkFailed(message=result.failure.message)
        return Failed(
            exc=RuntimeError(result.failure.message),
            message=result.failure.message,
            kind=result.failure.kind.value,
        )

    return Job(name="check", work=_work)
