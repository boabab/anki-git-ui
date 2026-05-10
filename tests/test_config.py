"""Config persistence tests: TOML round-trip + migration policy."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from anki_git_ui.config import CURRENT_VERSION, Config, _migrate
from anki_git_ui.domain.models import AnkiProfileChoice, DeckEntry


def _sample_config(tmp_path: Path) -> Config:
    return Config(
        config_version=CURRENT_VERSION,
        default_save_folder=tmp_path / "AnkiDecks",
        theme="dark",
        anki=AnkiProfileChoice(profile="User 1", collection_override=None),
        decks=[
            DeckEntry(
                nickname="JLPT N5",
                url="https://github.com/example/jlpt-n5",
                local_path=tmp_path / "AnkiDecks" / "jlpt-n5",
                branch="main",
                last_pulled_commit="a1b2c3d",
                last_pulled_at=datetime(2026, 5, 8, 14, 22, 1, tzinfo=timezone.utc),
                last_built_commit="a1b2c3d",
                last_built_apkg=tmp_path / "AnkiDecks" / ".builds" / "jlpt-n5-a1b2c3d.apkg",
                last_built_at=datetime(2026, 5, 10, 9, 14, 22, tzinfo=timezone.utc),
            ),
        ],
    )


def test_default_config_is_loadable_from_missing_file(tmp_path: Path) -> None:
    cfg = Config.load(tmp_path / "missing.toml")
    assert cfg.config_version == CURRENT_VERSION
    assert cfg.theme == "system"
    assert cfg.decks == []


def test_round_trip_preserves_all_fields(tmp_path: Path) -> None:
    src = _sample_config(tmp_path)
    path = tmp_path / "cfg.toml"
    src.save(path)

    loaded = Config.load(path)
    assert loaded.config_version == src.config_version
    # default_save_folder may have been re-expanded; compare resolved.
    assert loaded.default_save_folder.resolve() == src.default_save_folder.resolve()
    assert loaded.theme == src.theme
    assert loaded.anki.profile == src.anki.profile
    assert loaded.anki.collection_override == src.anki.collection_override
    assert len(loaded.decks) == 1

    a, b = loaded.decks[0], src.decks[0]
    assert a.nickname == b.nickname
    assert a.url == b.url
    assert a.branch == b.branch
    assert a.last_pulled_commit == b.last_pulled_commit
    assert a.last_pulled_at == b.last_pulled_at
    assert a.last_built_commit == b.last_built_commit
    assert a.last_built_at == b.last_built_at


def test_round_trip_persists_branch_and_commit_fields(tmp_path: Path) -> None:
    """The whole point of branch/commit being first-class — make sure they survive."""
    src = _sample_config(tmp_path)
    path = tmp_path / "cfg.toml"
    src.save(path)

    text = path.read_text(encoding="utf-8")
    assert 'branch = "main"' in text
    assert "last_pulled_commit" in text
    assert "last_built_commit" in text


def test_save_uses_tilde_for_home_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Paths under ``~`` are written as ``~/...`` so configs are portable
    across machines with different usernames."""
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    cfg = Config(
        default_save_folder=tmp_path / "AnkiDecks",
        decks=[
            DeckEntry(
                nickname="d",
                url="https://github.com/x/y",
                local_path=tmp_path / "AnkiDecks" / "y",
            )
        ],
    )
    out = tmp_path / "cfg.toml"
    cfg.save(out)
    text = out.read_text(encoding="utf-8")
    assert 'default_save_folder = "~/AnkiDecks"' in text
    assert 'local_path = "~/AnkiDecks/y"' in text


def test_load_refuses_newer_config_version(tmp_path: Path) -> None:
    path = tmp_path / "cfg.toml"
    path.write_text(f"config_version = {CURRENT_VERSION + 1}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="newer version"):
        Config.load(path)


def test_migrate_is_idempotent_at_current_version() -> None:
    data = {"config_version": CURRENT_VERSION}
    out = _migrate(dict(data))
    assert out["config_version"] == CURRENT_VERSION


def test_migrate_upgrades_missing_version() -> None:
    data: dict = {}  # no config_version → treat as 0, upgrade silently
    out = _migrate(dict(data))
    assert out["config_version"] == CURRENT_VERSION
