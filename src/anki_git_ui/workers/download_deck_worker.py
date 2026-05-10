"""High-level orchestration for "download a deck for the first time".

Wraps :func:`anki_git_ui.domain.git_ops.clone` with the bookkeeping the
dashboard cares about: capturing the resulting HEAD sha and branch name so
the deck card can show "up to date — already prepared" precisely. Pure
function — no Textual imports — so it can be tested without spinning up
the app.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from ..domain.git_ops import (
    CloneProgress,
    clone,
    head_branch,
    head_commit,
)
from ..domain.models import DeckEntry


@dataclass
class DownloadResult:
    head_commit: str | None
    head_branch: str | None
    pulled_at: datetime


def download_deck(
    deck: DeckEntry,
    *,
    on_log: Callable[[str], None] | None = None,
    on_progress: Callable[[CloneProgress], None] | None = None,
) -> DownloadResult:
    """Clone ``deck.url`` into ``deck.local_path`` and resolve HEAD.

    Mutates the passed ``deck`` in place — fills in ``branch``,
    ``last_pulled_commit``, and ``last_pulled_at`` on success. Raises
    :class:`anki_git_ui.domain.git_ops.GitError` (or a subclass) on failure;
    the caller surfaces it as a friendly modal.
    """
    if on_log is not None:
        on_log(f"git clone --progress {deck.url} {deck.local_path}")

    clone(
        deck.url,
        deck.local_path,
        on_line=on_log,
        on_progress=on_progress,
    )

    sha = head_commit(deck.local_path)
    branch = head_branch(deck.local_path)
    pulled_at = datetime.now(timezone.utc)

    deck.branch = branch or deck.branch
    deck.last_pulled_commit = sha
    deck.last_pulled_at = pulled_at

    if on_log is not None:
        on_log(f"Done — at branch {branch or '?'}, commit {sha[:7] if sha else '?'}.")

    return DownloadResult(head_commit=sha, head_branch=branch, pulled_at=pulled_at)


def deck_local_path(default_save_folder: Path, url: str) -> Path:
    """Default ``local_path`` for a freshly added deck — basename of the URL."""
    name = url.rstrip("/").split("/")[-1]
    if name.endswith(".git"):
        name = name[:-4]
    name = name or "deck"
    return default_save_folder / name


def deck_nickname(url: str) -> str:
    """Default nickname inferred from the URL basename."""
    name = url.rstrip("/").split("/")[-1]
    if name.endswith(".git"):
        name = name[:-4]
    return name.replace("-", " ").replace("_", " ").strip().title() or "Deck"
