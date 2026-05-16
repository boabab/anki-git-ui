"""Tests for the git_ops domain module — outcome-based public surface."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from anki_git_ui.domain.git_ops import (
    CloneFailed,
    CloneSucceeded,
    GitFailureKind,
    RemoteFailed,
    RemoteOk,
    clone_deck,
    detect_git,
    verify_anki_gitify_remote,
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


# ---------- clone_deck ---------- #


def test_clone_deck_succeeds_against_local_bare_repo(
    tmp_path: Path, local_git_remote: Path
) -> None:
    dest = tmp_path / "cloned"
    lines: list[str] = []
    outcome = clone_deck(str(local_git_remote), dest, on_log=lines.append)
    assert isinstance(outcome, CloneSucceeded)
    assert len(outcome.commit) == 40
    assert outcome.branch == "main"
    assert (dest / ".git").is_dir()
    assert (dest / "gitify.yml").is_file()
    assert any("git clone" in line for line in lines)


def test_clone_deck_refuses_existing_destination(
    tmp_path: Path, local_git_remote: Path
) -> None:
    dest = tmp_path / "exists"
    dest.mkdir()
    outcome = clone_deck(str(local_git_remote), dest)
    assert isinstance(outcome, CloneFailed)
    assert "already exists" in outcome.message


def test_clone_deck_classifies_repo_not_found(tmp_path: Path) -> None:
    dest = tmp_path / "nope"
    bogus = tmp_path / "definitely-not-a-repo"
    bogus.mkdir()
    outcome = clone_deck(str(bogus), dest)
    assert isinstance(outcome, CloneFailed)


def test_clone_deck_handles_missing_git(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("anki_git_ui.domain.git_ops.shutil.which", lambda _: None)
    outcome = clone_deck("https://example.com/x.git", tmp_path / "dest")
    assert isinstance(outcome, CloneFailed)
    assert outcome.kind is GitFailureKind.UNKNOWN
    assert "not installed" in outcome.message


def test_clone_deck_cleans_up_on_failure(tmp_path: Path) -> None:
    dest = tmp_path / "partial"
    bogus = tmp_path / "definitely-not-a-repo"
    bogus.mkdir()
    outcome = clone_deck(str(bogus), dest)
    assert isinstance(outcome, CloneFailed)
    assert not dest.exists(), "partial clone should be cleaned up on failure"


# ---------- verify_anki_gitify_remote ---------- #


def _git(*args: str, cwd: Path) -> None:
    subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True, check=True
    )


def _make_bare_remote(tmp_path: Path, *, with_gitify: bool) -> Path:
    """Build a tiny bare git repo. With or without a top-level gitify.yml."""
    work = tmp_path / "work"
    bare = tmp_path / "deck.git"
    work.mkdir()
    _git("init", "--initial-branch=main", cwd=work)
    _git("config", "user.email", "tests@example.com", cwd=work)
    _git("config", "user.name", "tests", cwd=work)
    if with_gitify:
        (work / "gitify.yml").write_text(
            "schema_version: 1\nroot_deck: Top\n", encoding="utf-8"
        )
    (work / "README.md").write_text("# tiny test deck\n", encoding="utf-8")
    _git("add", "-A", cwd=work)
    _git("commit", "-m", "initial", cwd=work)
    subprocess.run(
        ["git", "clone", "--bare", str(work), str(bare)],
        capture_output=True,
        text=True,
        check=True,
    )
    return bare


@pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH")
def test_verify_anki_gitify_remote_succeeds_on_gitify_deck(
    local_git_remote: Path,
) -> None:
    assert isinstance(verify_anki_gitify_remote(str(local_git_remote)), RemoteOk)


@pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH")
def test_verify_anki_gitify_remote_rejects_repo_without_gitify_yml(
    tmp_path: Path,
) -> None:
    bare = _make_bare_remote(tmp_path, with_gitify=False)
    outcome = verify_anki_gitify_remote(str(bare))
    assert isinstance(outcome, RemoteFailed)
    assert outcome.kind is GitFailureKind.NOT_ANKI_GITIFY
    assert "gitify.yml" in outcome.message


@pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH")
def test_verify_anki_gitify_remote_propagates_connectivity_error(
    tmp_path: Path,
) -> None:
    bogus = tmp_path / "definitely-not-a-repo"
    bogus.mkdir()
    outcome = verify_anki_gitify_remote(str(bogus))
    assert isinstance(outcome, RemoteFailed)
    assert outcome.kind is not GitFailureKind.NOT_ANKI_GITIFY


def test_verify_anki_gitify_remote_handles_missing_git(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("anki_git_ui.domain.git_ops.shutil.which", lambda _: None)
    outcome = verify_anki_gitify_remote("https://example.com/x.git")
    assert isinstance(outcome, RemoteFailed)
    assert outcome.kind is GitFailureKind.UNKNOWN
    assert "not installed" in outcome.message
