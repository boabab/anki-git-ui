"""Dashboard — list of tracked decks. Mouse-first."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Footer, Static

from ..domain.models import DeckEntry
from ..widgets.deck_card import DeckCard


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
            yield Static("Anki Community Deck Sync", classes="title")
            yield Button("Help", id="help")
            yield Button("Settings", id="settings")
        with VerticalScroll(id="dashboard-body"):
            yield Static("Your community decks", classes="section-title")
            decks = self.app.app_state.decks
            if not decks:
                yield Static(
                    "You haven't added any community decks yet. Click "
                    "\"+ Add a new community deck\" below to subscribe to a "
                    "deck shared on GitHub.",
                    id="empty-hint",
                )
            for deck in decks:
                yield DeckCard(deck)
            with Vertical(id="add-deck-row"):
                yield Button("+ Add a new community deck", id="add-deck", variant="primary")
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

    def _deck_by_nickname(self, nickname: str) -> DeckEntry | None:
        for deck in self.app.app_state.decks:
            if deck.nickname == nickname:
                return deck
        return None

    def action_add_deck(self) -> None:
        self.query_one("#add-deck", Button).press()

    def action_show_help(self) -> None:
        self.app.push_screen("help")
