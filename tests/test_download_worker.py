"""Tests for the download_deck_worker."""

from __future__ import annotations

from pathlib import Path

import pytest

from anki_git_ui.domain.models import DeckEntry, DeckStatus
from anki_git_ui.workers.download_deck_worker import (
    _url_basename,
    deck_local_path,
    deck_nickname,
    download_deck,
)


@pytest.mark.parametrize(
    "url, expected",
    [
        # Plain GitHub URL — base case
        ("https://github.com/owner/repo", "repo"),
        # Trailing slash is stripped
        ("https://github.com/owner/repo/", "repo"),
        # `.git` suffix is stripped
        ("https://github.com/owner/repo.git", "repo"),
        ("https://github.com/owner/repo.git/", "repo"),
        # SSH-style URLs aren't a supported format, but the current behavior
        # is "split on /, take last segment, strip .git" — pin it.
        ("git@github.com:owner/repo.git", "repo"),
        # Query strings are *not* stripped; current behavior is naive split.
        ("https://github.com/owner/repo?ref=main", "repo?ref=main"),
        # Degenerate inputs return empty — callers supply their own default.
        ("", ""),
        ("/", ""),
    ],
)
def test_url_basename_pinned_behavior(url: str, expected: str) -> None:
    assert _url_basename(url) == expected


def test_deck_local_path_uses_url_basename(tmp_path: Path) -> None:
    p = deck_local_path(tmp_path, "https://github.com/x/jlpt-n5-deck")
    assert p == tmp_path / "jlpt-n5-deck"


def test_deck_local_path_strips_dot_git_suffix(tmp_path: Path) -> None:
    p = deck_local_path(tmp_path, "https://github.com/x/medical-anatomy.git")
    assert p == tmp_path / "medical-anatomy"


def test_deck_local_path_handles_trailing_slash(tmp_path: Path) -> None:
    p = deck_local_path(tmp_path, "https://github.com/x/chinese-hsk-1/")
    assert p == tmp_path / "chinese-hsk-1"


def test_deck_nickname_titlecases_and_replaces_separators() -> None:
    assert deck_nickname("https://github.com/x/jlpt-n5-deck") == "Jlpt N5 Deck"
    assert deck_nickname("https://github.com/x/some_other.git") == "Some Other"


def test_download_deck_populates_deck_fields(tmp_path: Path, local_git_remote: Path) -> None:
    deck = DeckEntry(
        nickname="Test",
        url=str(local_git_remote),
        local_path=tmp_path / "test-deck",
        status=DeckStatus.NOT_DOWNLOADED,
    )
    log_lines: list[str] = []
    result = download_deck(deck, on_log=log_lines.append)

    assert result.head_commit is not None and len(result.head_commit) == 40
    assert result.head_branch == "main"
    assert deck.last_pulled_commit == result.head_commit
    assert deck.branch == "main"
    assert deck.last_pulled_at is not None
    assert (deck.local_path / ".git").is_dir()
    assert any("git clone" in line for line in log_lines)
    assert any("Done" in line for line in log_lines)
