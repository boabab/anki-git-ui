"""Tests for the git_ops domain module."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from anki_git_ui.domain.git_ops import (
    GitError,
    GitNotFoundError,
    clone,
    detect_git,
    head_branch,
    head_commit,
)


@pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH")
def test_detect_git_finds_real_git() -> None:
    result = detect_git()
    assert result.found is True
    assert result.error is None
    assert result.version is not None
    assert "git" in result.version.lower()


def test_detect_git_handles_missing_git(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("anki_git_ui.domain.git_ops.shutil.which", lambda _: None)
    result = detect_git()
    assert result.found is False
    assert result.error is not None
    assert "not found" in result.error.lower()


# ---------- clone ---------- #


def test_clone_succeeds_against_local_bare_repo(tmp_path: Path, local_git_remote: Path) -> None:
    dest = tmp_path / "cloned"
    lines: list[str] = []
    clone(str(local_git_remote), dest, on_line=lines.append)
    assert (dest / ".git").is_dir()
    assert (dest / "gitify.yml").is_file()
    assert any("clone" in line.lower() or "receiving" in line.lower() or "done" in line.lower()
               for line in lines), f"expected progress in {lines}"


def test_clone_refuses_existing_destination(tmp_path: Path, local_git_remote: Path) -> None:
    dest = tmp_path / "exists"
    dest.mkdir()
    with pytest.raises(GitError, match="already exists"):
        clone(str(local_git_remote), dest)


def test_clone_classifies_repo_not_found(tmp_path: Path) -> None:
    dest = tmp_path / "nope"
    bogus = tmp_path / "definitely-not-a-repo"
    bogus.mkdir()
    with pytest.raises(GitError):
        clone(str(bogus), dest)


def test_clone_raises_when_git_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("anki_git_ui.domain.git_ops.shutil.which", lambda _: None)
    with pytest.raises(GitNotFoundError):
        clone("https://example.com/x.git", tmp_path / "dest")


def test_clone_cleans_up_on_failure(tmp_path: Path) -> None:
    dest = tmp_path / "partial"
    bogus = tmp_path / "definitely-not-a-repo"
    bogus.mkdir()
    with pytest.raises(GitError):
        clone(str(bogus), dest)
    assert not dest.exists(), "partial clone should be cleaned up on failure"


# ---------- head helpers ---------- #


def test_head_commit_and_branch_after_clone(tmp_path: Path, local_git_remote: Path) -> None:
    dest = tmp_path / "cloned"
    clone(str(local_git_remote), dest)
    sha = head_commit(dest)
    branch = head_branch(dest)
    assert sha is not None and len(sha) == 40
    assert branch == "main"
