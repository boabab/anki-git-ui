"""Tests for the update flow — worker wrapper and the underlying git_ops outcome."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from anki_git_ui.domain import git_ops
from anki_git_ui.domain.git_ops import (
    UpdateFailed,
    UpdateSucceeded,
)
from anki_git_ui.domain.models import DeckEntry, DeckStatus
from anki_git_ui.workers.download_deck_worker import download_deck
from anki_git_ui.workers.update_deck_worker import update_deck


def _git(*args: str, cwd: Path | None = None) -> None:
    subprocess.run(
        ["git", *args],
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        check=True,
    )


@pytest.fixture
def remote_with_one_commit(tmp_path: Path) -> Path:
    """A bare git repo we can clone, plus a working clone where we can add new
    commits to simulate "the upstream got updates"."""
    if shutil.which("git") is None:
        pytest.skip("git not available")
    work = tmp_path / "src-work"
    bare = tmp_path / "remote.git"
    work.mkdir()
    _git("init", "--initial-branch=main", cwd=work)
    _git("config", "user.email", "tests@example.com", cwd=work)
    _git("config", "user.name", "tests", cwd=work)
    (work / "gitify.yml").write_text("schema_version: 1\nroot_deck: Top\n", encoding="utf-8")
    _git("add", "-A", cwd=work)
    _git("commit", "-m", "initial", cwd=work)
    _git("clone", "--bare", str(work), str(bare))
    return bare


def test_update_deck_no_changes(tmp_path: Path, remote_with_one_commit: Path) -> None:
    deck = DeckEntry(
        nickname="Test",
        url=str(remote_with_one_commit),
        local_path=tmp_path / "deck",
        status=DeckStatus.NOT_DOWNLOADED,
    )
    download_deck(deck)
    pre = deck.last_pulled_commit
    log: list[str] = []
    outcome = update_deck(deck, on_log=log.append)
    assert isinstance(outcome, UpdateSucceeded)
    assert outcome.advanced is False
    assert deck.last_pulled_commit == pre
    assert any("Already up to date" in line for line in log)


def test_update_deck_pulls_new_commit(tmp_path: Path, remote_with_one_commit: Path) -> None:
    deck = DeckEntry(
        nickname="Test",
        url=str(remote_with_one_commit),
        local_path=tmp_path / "deck",
        status=DeckStatus.NOT_DOWNLOADED,
    )
    download_deck(deck)
    pre = deck.last_pulled_commit

    # Push a new commit to the bare remote: clone, commit, push.
    upstream_work = tmp_path / "upstream-work"
    _git("clone", str(remote_with_one_commit), str(upstream_work))
    _git("config", "user.email", "tests@example.com", cwd=upstream_work)
    _git("config", "user.name", "tests", cwd=upstream_work)
    (upstream_work / "newfile.txt").write_text("new\n", encoding="utf-8")
    _git("add", "-A", cwd=upstream_work)
    _git("commit", "-m", "second commit", cwd=upstream_work)
    _git("push", cwd=upstream_work)

    outcome = update_deck(deck)
    assert isinstance(outcome, UpdateSucceeded)
    assert outcome.advanced is True
    assert deck.last_pulled_commit != pre
    assert (deck.local_path / "newfile.txt").is_file()


def test_update_deck_returns_failed_on_diverged(
    tmp_path: Path, remote_with_one_commit: Path
) -> None:
    deck_path = tmp_path / "deck"
    _git("clone", str(remote_with_one_commit), str(deck_path))
    _git("config", "user.email", "tests@example.com", cwd=deck_path)
    _git("config", "user.name", "tests", cwd=deck_path)

    # Make a divergent local commit.
    (deck_path / "local.txt").write_text("l\n", encoding="utf-8")
    _git("add", "-A", cwd=deck_path)
    _git("commit", "-m", "local-only", cwd=deck_path)

    # Make a divergent upstream commit too.
    other = tmp_path / "other"
    _git("clone", str(remote_with_one_commit), str(other))
    _git("config", "user.email", "tests@example.com", cwd=other)
    _git("config", "user.name", "tests", cwd=other)
    (other / "remote.txt").write_text("r\n", encoding="utf-8")
    _git("add", "-A", cwd=other)
    _git("commit", "-m", "remote-only", cwd=other)
    _git("push", cwd=other)

    outcome = git_ops.update_deck(deck_path)
    assert isinstance(outcome, UpdateFailed)
    assert "Local changes" in outcome.message
