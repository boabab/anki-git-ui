"""Tests for the filtered_decks_worker."""

from __future__ import annotations

from pathlib import Path

import pytest

from anki_git_ui.domain.models import AnkiProfileChoice, DeckEntry, DeckStatus
from anki_git_ui.workers.filtered_decks_worker import (
    apply_filtered_decks,
    is_locked_error,
)


def test_is_locked_error_matches_by_message_not_type() -> None:
    assert is_locked_error(RuntimeError("Cannot open: file is locked. Close Anki."))
    assert is_locked_error(RuntimeError("LOCKED"))
    assert is_locked_error(RuntimeError("Anki already open"))
    assert is_locked_error(RuntimeError("currently syncing"))
    assert not is_locked_error(RuntimeError("some other failure"))
    # Deliberate: anki.errors.DBError is a sibling of RuntimeError, not a
    # subclass, so the check is intentionally message-based, not type-based.
    assert is_locked_error(ValueError("locked but wrong type"))


def test_apply_filtered_decks_raises_when_no_filtered_yml(tmp_path: Path) -> None:
    deck_dir = tmp_path / "deck"
    deck_dir.mkdir()
    deck = DeckEntry(
        nickname="x",
        url="https://example.com/x",
        local_path=deck_dir,
        status=DeckStatus.UP_TO_DATE,
    )
    with pytest.raises(FileNotFoundError, match="filtered-deck"):
        apply_filtered_decks(deck, AnkiProfileChoice())


def test_apply_filtered_decks_against_synthetic_collection(tmp_path: Path) -> None:
    """End-to-end against a real synthetic Anki collection plus a gitified
    directory that includes filtered_decks.yml.
    """
    pytest.importorskip("anki")
    from anki.collection import Collection

    # Build a synthetic Anki collection with one normal deck and one filtered deck.
    profile_dir = tmp_path / "Anki2" / "User1"
    media_dir = profile_dir / "collection.media"
    media_dir.mkdir(parents=True)
    col_path = profile_dir / "collection.anki2"

    col = Collection(str(col_path))
    try:
        m = col.models.new("Basic")
        col.models.add_field(m, col.models.new_field("Front"))
        col.models.add_field(m, col.models.new_field("Back"))
        t = col.models.new_template("F-B")
        t["qfmt"] = "{{Front}}"
        t["afmt"] = "{{Front}}<hr>{{Back}}"
        col.models.add_template(m, t)
        col.models.add(m)
        deck_id = col.decks.id("Top")
        for front, back in [("a", "1"), ("b", "2")]:
            note = col.new_note(col.models.get(m["id"]))
            note.fields[0] = front
            note.fields[1] = back
            col.add_note(note, deck_id)
        # Add a filtered deck so the source has something to test with.
        fid = col.decks.new_filtered("Top::Cram::Recent")
        d1 = col.decks.get(fid)
        d1["terms"] = [["deck:Top", 100, 0]]
        d1["resched"] = True
        col.decks.save(d1)
    finally:
        col.close()

    # Export through anki-gitify so we have a real gitified directory with
    # filtered_decks.yml.
    from anki_gitify.export.exporter import export as run_export
    from anki_gitify.profile import ProfilePaths

    gitified = tmp_path / "gitified"
    profile = ProfilePaths(
        base=tmp_path / "Anki2",
        profile="User1",
        collection=col_path,
        media_dir=media_dir,
    )
    run_export(deck_name="Top", out_dir=gitified, profile=profile)
    assert (gitified / "filtered_decks.yml").is_file()

    deck = DeckEntry(
        nickname="Test",
        url="https://example.com/test",
        local_path=gitified,
        status=DeckStatus.UP_TO_DATE,
    )

    # Build a fresh empty collection to apply against.
    target_dir = tmp_path / "target" / "User1"
    target_media = target_dir / "collection.media"
    target_media.mkdir(parents=True)
    target_col_path = target_dir / "collection.anki2"
    Collection(str(target_col_path)).close()

    result = apply_filtered_decks(
        deck,
        AnkiProfileChoice(collection_override=target_col_path),
        dry_run=True,
    )

    # Dry-run reports what would be created without writing.
    assert result.dry_run is True
    assert "Top::Cram::Recent" in result.created
    assert result.conflicts == []


def test_apply_filtered_decks_skips_existing(tmp_path: Path) -> None:
    """A second apply_filtered_decks call (no dry-run) is idempotent."""
    pytest.importorskip("anki")
    from anki.collection import Collection

    # Same setup as above — kept self-contained for test independence.
    profile_dir = tmp_path / "Anki2" / "User1"
    media_dir = profile_dir / "collection.media"
    media_dir.mkdir(parents=True)
    col_path = profile_dir / "collection.anki2"

    col = Collection(str(col_path))
    try:
        m = col.models.new("Basic")
        col.models.add_field(m, col.models.new_field("Front"))
        col.models.add_field(m, col.models.new_field("Back"))
        t = col.models.new_template("F-B")
        t["qfmt"] = "{{Front}}"
        t["afmt"] = "{{Front}}<hr>{{Back}}"
        col.models.add_template(m, t)
        col.models.add(m)
        deck_id = col.decks.id("Top")
        note = col.new_note(col.models.get(m["id"]))
        note.fields[0] = "x"
        note.fields[1] = "y"
        col.add_note(note, deck_id)
        fid = col.decks.new_filtered("Top::Cram::All")
        d1 = col.decks.get(fid)
        d1["terms"] = [["deck:Top", 50, 0]]
        col.decks.save(d1)
    finally:
        col.close()

    from anki_gitify.export.exporter import export as run_export
    from anki_gitify.profile import ProfilePaths

    gitified = tmp_path / "gitified"
    profile = ProfilePaths(
        base=tmp_path / "Anki2",
        profile="User1",
        collection=col_path,
        media_dir=media_dir,
    )
    run_export(deck_name="Top", out_dir=gitified, profile=profile)

    deck = DeckEntry(
        nickname="Test",
        url="x",
        local_path=gitified,
        status=DeckStatus.UP_TO_DATE,
    )

    target_dir = tmp_path / "target" / "User1"
    target_media = target_dir / "collection.media"
    target_media.mkdir(parents=True)
    target_col_path = target_dir / "collection.anki2"
    Collection(str(target_col_path)).close()

    # First apply: creates.
    r1 = apply_filtered_decks(
        deck, AnkiProfileChoice(collection_override=target_col_path)
    )
    assert "Top::Cram::All" in r1.created
    assert r1.skipped == []

    # Second apply: idempotent (skipped, not re-created).
    r2 = apply_filtered_decks(
        deck, AnkiProfileChoice(collection_override=target_col_path)
    )
    assert r2.created == []
    assert "Top::Cram::All" in r2.skipped
