"""Dashboard — list of tracked decks. Mouse-first."""

from __future__ import annotations

import shutil

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Footer, Static

from ..domain.models import DeckEntry
from ..widgets.deck_card import DeckCard
from .modals import RemoveDeckModal, RemoveDeckResult


class DashboardScreen(Screen):
    DEFAULT_CSS = """
    DashboardScreen {
        layout: vertical;
    }
    #app-bar {
        height: 3;
        padding: 0 2;
        background: $primary 10%;
    }
    #app-bar .title {
        width: 1fr;
        content-align: left middle;
        text-style: bold;
        color: $primary;
    }
    #app-bar Button {
        margin: 0 0 0 1;
        min-width: 12;
    }
    #dashboard-body {
        padding: 1 2;
    }
    #dashboard-body .section-title {
        text-style: bold;
        padding-bottom: 1;
    }
    #empty-hint {
        color: $text-muted;
        padding: 2 0;
    }
    #add-deck-row {
        height: 5;
        align-horizontal: center;
        padding-top: 1;
    }
    #add-deck-row Button {
        min-width: 30;
    }
    """

    BINDINGS = [
        Binding("a", "add_deck", "Add deck", show=False),
        Binding("question_mark", "show_help", "Help", show=False),
    ]

    def compose(self) -> ComposeResult:
        with Horizontal(id="app-bar"):
            yield Static("Anki Deck Sync", classes="title")
            yield Button("Help", id="help")
            yield Button("Settings", id="settings")
        with VerticalScroll(id="dashboard-body"):
            yield Static("Your decks", classes="section-title")
            decks = self.app.app_state.decks
            if not decks:
                yield Static(
                    "You haven't added any decks yet. Click \"+ Add a new deck\" "
                    "below to subscribe to a deck shared on GitHub.",
                    id="empty-hint",
                )
            for deck in decks:
                yield DeckCard(deck)
            with Vertical(id="add-deck-row"):
                yield Button("+ Add a new deck", id="add-deck", variant="primary")
        yield Footer()

    def on_screen_resume(self) -> None:
        """Re-render whenever this screen comes back into focus.

        Adding a deck, downloading one, removing one, or finishing a build
        all happen on other screens; without this, popping back to the
        dashboard would show the snapshot from the last time it was mounted.
        """
        self.refresh(recompose=True)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "help":
            self.app.push_screen("help")
        elif bid == "settings":
            self.app.push_screen("settings")
        elif bid == "add-deck":
            self.app.push_screen("add-deck")

    def on_deck_card_open(self, event: DeckCard.Open) -> None:
        deck = self._deck_by_nickname(event.nickname)
        if deck is None:
            return
        from .deck_detail import DeckDetailScreen

        self.app.push_screen(DeckDetailScreen(deck=deck))

    def on_deck_card_remove(self, event: DeckCard.Remove) -> None:
        deck = self._deck_by_nickname(event.nickname)
        if deck is None:
            return

        def _on_choice(result: RemoveDeckResult | None) -> None:
            if result is None:
                return
            self._remove_deck(deck, delete_files=result.delete_files)

        self.app.push_screen(
            RemoveDeckModal(nickname=deck.nickname, local_path=deck.local_path),
            _on_choice,
        )

    def _deck_by_nickname(self, nickname: str) -> DeckEntry | None:
        for deck in self.app.app_state.decks:
            if deck.nickname == nickname:
                return deck
        return None

    def _remove_deck(self, deck: DeckEntry, *, delete_files: bool) -> None:
        if deck in self.app.app_state.decks:
            self.app.app_state.decks.remove(deck)
        if deck in self.app.config.decks:
            self.app.config.decks.remove(deck)
        self.app.config.save()

        if delete_files and self._safe_to_delete(deck.local_path):
            shutil.rmtree(deck.local_path, ignore_errors=True)

        self.app.notify(
            f'"{deck.nickname}" removed' + (" and deleted from disk." if delete_files else "."),
            title="Removed",
        )
        self.refresh(recompose=True)

    def _safe_to_delete(self, path) -> bool:
        """Refuse to recursively delete dangerous targets."""
        try:
            resolved = path.resolve()
        except Exception:
            return False
        from pathlib import Path

        if resolved == Path("/") or resolved == Path.home() or resolved == resolved.parent:
            return False
        save_root = self.app.config.default_save_folder.expanduser().resolve()
        try:
            resolved.relative_to(save_root)
            return True
        except ValueError:
            # Outside the configured save folder — refuse to delete.
            return False

    def action_add_deck(self) -> None:
        self.query_one("#add-deck", Button).press()

    def action_show_help(self) -> None:
        self.app.push_screen("help")
