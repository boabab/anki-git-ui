"""In-memory app state — selected deck, settings, runtime flags.

Distinct from :mod:`anki_git_ui.config`, which is on-disk persistence. M3
wires the two together so the dashboard reads decks from `config.toml` at
startup.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .domain.models import AnkiProfileChoice, DeckEntry, DeckStatus


@dataclass
class AppState:
    """Mutable state held on the running ``App`` instance."""

    decks: list[DeckEntry] = field(default_factory=list)
    anki: AnkiProfileChoice = field(default_factory=AnkiProfileChoice)
    default_save_folder: Path = field(default_factory=lambda: Path.home() / "AnkiDecks")
    theme: str = "system"
    is_first_run: bool = True


def make_mock_state() -> AppState:
    """Pre-canned state used by the M2 skeleton until M3 wires real config."""

    state = AppState(is_first_run=False)
    state.decks = [
        DeckEntry(
            nickname="JLPT N5",
            url="https://github.com/example-user/jlpt-n5-deck",
            local_path=state.default_save_folder / "jlpt-n5-deck",
            branch="main",
            last_pulled_at=datetime(2026, 5, 8, 14, 22, 1),
            last_built_at=datetime(2026, 5, 8, 14, 30, 0),
            status=DeckStatus.UPDATES_AVAILABLE,
            updates_available=3,
        ),
        DeckEntry(
            nickname="Medical Anatomy",
            url="https://github.com/example-user/medical-anatomy",
            local_path=state.default_save_folder / "medical-anatomy",
            branch="main",
            last_pulled_at=datetime(2026, 5, 10, 9, 0, 0),
            last_built_at=datetime(2026, 5, 10, 9, 5, 0),
            status=DeckStatus.UP_TO_DATE,
        ),
        DeckEntry(
            nickname="Chinese HSK 1",
            url="https://github.com/example-user/chinese-hsk-1",
            local_path=state.default_save_folder / "chinese-hsk-1",
            branch="main",
            status=DeckStatus.NOT_DOWNLOADED,
        ),
    ]
    return state
