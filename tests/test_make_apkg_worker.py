"""Test the make_apkg_worker against a real synthetic deck.

Uses anki-gitify's existing fixture pattern: build a synthetic Anki
collection in a temp dir, export it via anki_gitify.export, then exercise
our make_apkg() against the resulting gitified directory.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from anki_git_ui.domain.apkg_paths import apkg_output_path
from anki_git_ui.domain.models import DeckEntry, DeckStatus
from anki_git_ui.workers.make_apkg_worker import make_apkg


def test_apkg_output_path_uses_short_sha(tmp_path: Path) -> None:
    out = apkg_output_path(tmp_path, tmp_path / "my-deck", "abcdef1234567890")
    assert out == tmp_path / ".builds" / "my-deck-abcdef1.apkg"


def test_apkg_output_path_handles_missing_commit(tmp_path: Path) -> None:
    out = apkg_output_path(tmp_path, tmp_path / "my-deck", None)
    assert out.name.startswith("my-deck-unknown")


def test_make_apkg_against_synthetic_deck(tmp_path: Path) -> None:
    """Build a synthetic Anki collection → export to gitified → make apkg."""
    pytest.importorskip("anki")
    from anki.collection import Collection

    # Synthetic collection
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
        m["css"] = ".card { font-family: arial; }"
        col.models.add(m)

        deck_id = col.decks.id("Top")
        for front, back in [("a", "1"), ("b", "2"), ("c", "3")]:
            note = col.new_note(col.models.get(m["id"]))
            note.fields[0] = front
            note.fields[1] = back
            col.add_note(note, deck_id)
    finally:
        col.close()

    # Export through anki-gitify so we have a real gitified directory.
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
        url="https://example.com/test",
        local_path=gitified,
        status=DeckStatus.UP_TO_DATE,
        last_pulled_commit="a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
    )

    save_folder = tmp_path / "AnkiDecks"
    log_lines: list[str] = []
    result = make_apkg(deck, save_folder, on_log=log_lines.append)

    assert result.apkg_path.is_file()
    assert result.apkg_path.stat().st_size > 0
    assert result.notes >= 3
    assert deck.last_built_apkg == result.apkg_path
    assert deck.last_built_commit == deck.last_pulled_commit
    assert deck.last_built_at is not None
    assert any("Building Anki file" in line for line in log_lines)
    assert any("Done" in line for line in log_lines)
