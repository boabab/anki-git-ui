"""Tests for the Anki interop facade and deck_metadata helper.

The lock-detection table replaces the previous test in
``tests/test_filtered_decks_worker.py``: it's the single most brittle line
in the app and gets its own focused test surface here, where the facade
lives.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from anki_git_ui.domain import anki_interop, deck_metadata
from anki_git_ui.domain.anki_interop import (
    CardOverrideRequired,
    CollectionMissing,
    Completed,
    Failed,
    ImportReport,
    Locked,
    _is_locked_error,
)
from anki_git_ui.domain.models import AnkiProfileChoice


# ---------- _is_locked_error ---------- #


@pytest.mark.parametrize(
    "exc, expected",
    [
        (RuntimeError("Cannot open: file is locked. Close Anki."), True),
        (RuntimeError("LOCKED"), True),
        (RuntimeError("Anki already open"), True),
        (RuntimeError("currently syncing"), True),
        (RuntimeError("database is locked"), True),
        # Deliberate: anki.errors.DBError is a sibling of RuntimeError, not a
        # subclass, so the check is intentionally message-based, not type-based.
        (ValueError("locked but wrong type"), True),
        (RuntimeError("some other failure"), False),
        (ValueError("permission denied"), False),
        (RuntimeError(""), False),
    ],
)
def test_is_locked_error_message_table(exc: BaseException, expected: bool) -> None:
    assert _is_locked_error(exc) is expected


# ---------- resolve_collection ---------- #


def test_resolve_collection_returns_missing_when_profile_lookup_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_resolve(*, profile, collection_override):
        raise FileNotFoundError("no anki here")

    monkeypatch.setattr(
        "anki_git_ui.domain.anki_interop.api.resolve_profile_paths", fake_resolve
    )
    outcome = anki_interop.resolve_collection(AnkiProfileChoice(profile="ghost"))
    assert isinstance(outcome, CollectionMissing)
    assert "no anki here" in outcome.message


def test_resolve_collection_returns_missing_on_value_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_resolve(*, profile, collection_override):
        raise ValueError("no profiles found")

    monkeypatch.setattr(
        "anki_git_ui.domain.anki_interop.api.resolve_profile_paths", fake_resolve
    )
    outcome = anki_interop.resolve_collection(AnkiProfileChoice())
    assert isinstance(outcome, CollectionMissing)
    assert "no profiles found" in outcome.message


# ---------- apply_filtered / rebuild_filtered: outcome translation ---------- #


def test_apply_filtered_returns_locked_on_lock_exception(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "anki_git_ui.domain.anki_interop.api.resolve_profile_paths",
        lambda *, profile, collection_override: _FakePaths(tmp_path / "col.anki2"),
    )

    def boom(*args, **kwargs):
        raise RuntimeError("Anki already open — close it first")

    monkeypatch.setattr("anki_git_ui.domain.anki_interop.api.apply_filtered", boom)

    outcome = anki_interop.apply_filtered(
        tmp_path, AnkiProfileChoice(profile="x"), dry_run=False
    )
    assert isinstance(outcome, Locked)


def test_apply_filtered_returns_failed_on_unrelated_exception(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "anki_git_ui.domain.anki_interop.api.resolve_profile_paths",
        lambda *, profile, collection_override: _FakePaths(tmp_path / "col.anki2"),
    )

    def boom(*args, **kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr("anki_git_ui.domain.anki_interop.api.apply_filtered", boom)

    outcome = anki_interop.apply_filtered(
        tmp_path, AnkiProfileChoice(profile="x"), dry_run=False
    )
    assert isinstance(outcome, Failed)
    assert "disk full" in outcome.message
    assert isinstance(outcome.exc, RuntimeError)


def test_apply_filtered_returns_collection_missing_on_resolve_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "anki_git_ui.domain.anki_interop.api.resolve_profile_paths",
        _raise_filenotfound,
    )
    outcome = anki_interop.apply_filtered(
        tmp_path, AnkiProfileChoice(profile="ghost")
    )
    assert isinstance(outcome, CollectionMissing)


def test_rebuild_filtered_short_circuits_on_empty_entries(tmp_path: Path) -> None:
    outcome = anki_interop.rebuild_filtered(
        tmp_path, AnkiProfileChoice(), entries=[]
    )
    assert isinstance(outcome, Completed)
    assert outcome.value.total == 0


# ---------- import_deck: outcome translation ---------- #


def test_import_deck_returns_failed_when_verify_rejects(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class _Report:
        ok = False
        errors = ["missing gitify.yml"]
        notes = 0
        notetypes = 0
        media = 0

    monkeypatch.setattr(
        "anki_git_ui.domain.anki_interop.api.verify", lambda _p: _Report()
    )
    outcome = anki_interop.import_deck(
        tmp_path, tmp_path / "out.apkg", ignore_card_overrides=False
    )
    assert isinstance(outcome, Failed)
    assert "missing gitify.yml" in outcome.message


def test_import_deck_returns_card_override_required(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from anki_gitify.api import CardOverrideError

    class _Report:
        ok = True
        errors: list[str] = []
        notes = 0
        notetypes = 0
        media = 0

    monkeypatch.setattr(
        "anki_git_ui.domain.anki_interop.api.verify", lambda _p: _Report()
    )

    def fake_import(_path, _out, *, ignore_card_overrides):
        raise CardOverrideError("cards.csv present")

    monkeypatch.setattr("anki_git_ui.domain.anki_interop.api.import_", fake_import)
    outcome = anki_interop.import_deck(
        tmp_path, tmp_path / "out.apkg", ignore_card_overrides=False
    )
    assert isinstance(outcome, CardOverrideRequired)


def test_import_deck_returns_completed_with_report(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class _VerifyReport:
        ok = True
        errors: list[str] = []
        notes = 3
        notetypes = 1
        media = 0

    class _ImportReport:
        notes = 3
        media_files = 0
        filtered_decks = 0

    monkeypatch.setattr(
        "anki_git_ui.domain.anki_interop.api.verify", lambda _p: _VerifyReport()
    )
    monkeypatch.setattr(
        "anki_git_ui.domain.anki_interop.api.import_",
        lambda _path, _out, *, ignore_card_overrides: (_ImportReport(), None),
    )
    out_path = tmp_path / ".builds" / "deck.apkg"
    outcome = anki_interop.import_deck(tmp_path, out_path, ignore_card_overrides=False)
    assert isinstance(outcome, Completed)
    report: ImportReport = outcome.value
    assert report.apkg_path == out_path
    assert report.notes == 3
    assert out_path.parent.is_dir()


# ---------- deck_metadata ---------- #


def test_list_filtered_deck_names_returns_empty_when_missing(tmp_path: Path) -> None:
    assert deck_metadata.list_filtered_deck_names(tmp_path) == []


def test_list_filtered_deck_names_parses_valid_yaml(tmp_path: Path) -> None:
    (tmp_path / "filtered_decks.yml").write_text(
        "filtered_decks:\n  - name: Top::Cram::Recent\n  - name: Top::Cram::Hard\n",
        encoding="utf-8",
    )
    assert deck_metadata.list_filtered_deck_names(tmp_path) == [
        "Top::Cram::Recent",
        "Top::Cram::Hard",
    ]


def test_list_filtered_deck_names_skips_non_string_names(tmp_path: Path) -> None:
    (tmp_path / "filtered_decks.yml").write_text(
        "filtered_decks:\n  - name: ok\n  - name: 42\n  - {}\n",
        encoding="utf-8",
    )
    assert deck_metadata.list_filtered_deck_names(tmp_path) == ["ok"]


def test_list_filtered_deck_names_handles_malformed_yaml(tmp_path: Path) -> None:
    (tmp_path / "filtered_decks.yml").write_text(
        "filtered_decks: [unclosed", encoding="utf-8"
    )
    assert deck_metadata.list_filtered_deck_names(tmp_path) == []


def test_has_filtered_decks_reflects_list(tmp_path: Path) -> None:
    assert deck_metadata.has_filtered_decks(tmp_path) is False
    (tmp_path / "filtered_decks.yml").write_text(
        "filtered_decks:\n  - name: x\n", encoding="utf-8"
    )
    assert deck_metadata.has_filtered_decks(tmp_path) is True


# ---------- helpers ---------- #


class _FakePaths:
    def __init__(self, collection: Path) -> None:
        self.collection = collection


def _raise_filenotfound(**_kwargs):
    raise FileNotFoundError("nope")
