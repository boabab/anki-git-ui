"""Tests for the update_deck_worker."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from anki_git_ui.domain.git_ops import GitError, fetch, pull_ff_only, update_status
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
    result = update_deck(deck, on_log=log.append)
    assert result.no_changes is True
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

    result = update_deck(deck)
    assert result.no_changes is False
    assert deck.last_pulled_commit != pre
    assert (deck.local_path / "newfile.txt").is_file()


def test_update_status_reports_behind(tmp_path: Path, remote_with_one_commit: Path) -> None:
    deck_path = tmp_path / "deck"
    _git("clone", str(remote_with_one_commit), str(deck_path))

    # Add a commit upstream WITHOUT touching deck_path.
    other = tmp_path / "other"
    _git("clone", str(remote_with_one_commit), str(other))
    _git("config", "user.email", "tests@example.com", cwd=other)
    _git("config", "user.name", "tests", cwd=other)
    (other / "x.txt").write_text("x\n", encoding="utf-8")
    _git("add", "-A", cwd=other)
    _git("commit", "-m", "ahead", cwd=other)
    _git("push", cwd=other)

    fetch(deck_path)
    status = update_status(deck_path)
    assert status.upstream_known is True
    assert status.behind == 1
    assert status.ahead == 0
    assert status.dirty is False


def test_pull_ff_only_refuses_diverged(tmp_path: Path, remote_with_one_commit: Path) -> None:
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

    with pytest.raises(GitError, match="Local changes"):
        fetch(deck_path)
        pull_ff_only(deck_path)
