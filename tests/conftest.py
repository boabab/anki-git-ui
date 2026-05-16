"""Shared fixtures for anki-git-ui tests."""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest
from pytest_textual_snapshot import SVGImageExtension

from anki_git_ui.app import AnkiGitUIApp
from anki_git_ui.config import Config
from anki_git_ui.state import AppState, make_mock_state

# pytest-textual-snapshot 1.0.0 sets `_file_extension = "svg"` (underscore-prefixed),
# but current syrupy reads `file_extension` (no underscore) — so the SVG override is
# silently ignored and snapshots fall back to syrupy's `.raw` default. Force the
# right attribute here so snapshots land at *.svg as the test fixtures expect.
SVGImageExtension.file_extension = "svg"


TEST_SAVE_FOLDER = Path("/tmp/anki-git-ui-test/AnkiDecks")


@pytest.fixture
def empty_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Config:
    """Return a fresh Config that points its config_path() at tmp_path."""
    cfg_path = tmp_path / "config.toml"
    monkeypatch.setattr("anki_git_ui.config.config_path", lambda: cfg_path)
    monkeypatch.setattr("anki_git_ui.app.config_exists", lambda: cfg_path.is_file())
    monkeypatch.setattr("anki_git_ui.config.config_exists", lambda: cfg_path.is_file())
    return Config(default_save_folder=TEST_SAVE_FOLDER)


@pytest.fixture
def make_app(
    empty_config: Config,
) -> Callable[..., AnkiGitUIApp]:
    """Factory that builds an AnkiGitUIApp with explicit config / state.

    Defaults: empty config, mock state with three decks (so the dashboard has
    something to render). Pass ``state=AppState(...)`` to override.
    """

    def _make(*, state: AppState | None = None, config: Config | None = None) -> AnkiGitUIApp:
        cfg = config or empty_config
        return AnkiGitUIApp(
            config=cfg,
            app_state=state or make_mock_state(default_save_folder=cfg.default_save_folder),
        )

    return _make


def _git(*args: str, cwd: Path | None = None) -> None:
    subprocess.run(
        ["git", *args],
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        check=True,
    )


@pytest.fixture
def local_git_remote(tmp_path: Path) -> Path:
    """A tiny populated bare git repo we can clone from. No network required."""
    if shutil.which("git") is None:
        pytest.skip("git not available")

    work = tmp_path / "src-work"
    bare = tmp_path / "deck.git"

    work.mkdir()
    _git("init", "--initial-branch=main", cwd=work)
    _git("config", "user.email", "tests@example.com", cwd=work)
    _git("config", "user.name", "tests", cwd=work)
    (work / "gitify.yml").write_text("schema_version: 1\nroot_deck: Top\n", encoding="utf-8")
    (work / "README.md").write_text("# tiny test deck\n", encoding="utf-8")
    _git("add", "-A", cwd=work)
    _git("commit", "-m", "initial", cwd=work)

    _git("clone", "--bare", str(work), str(bare))
    return bare
