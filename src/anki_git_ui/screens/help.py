"""Help / about screen."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Static

from .. import __version__


_WHAT = (
    "Anki Community Deck Sync downloads Anki decks that have been shared on "
    "GitHub and prepares them as Anki deck files (.apkg) that you can import "
    "in Anki. Think of it as a subscription manager for community decks."
)

_HOW = (
    "1. Click \"+ Add a new community deck\" on the dashboard and paste the GitHub link.\n"
    "2. Click \"Download latest updates\" to pull the latest version and prepare a new Anki deck file.\n"
    "3. Click \"Import to Anki\" to open the file in Anki, or use File → Import in Anki manually."
)

_SHORTCUTS = (
    "Most actions are clickable buttons. A few keyboard shortcuts:\n"
    "  q          Quit\n"
    "  Esc        Go back / close a dialog\n"
    "  Tab        Move between buttons\n"
    "  Enter      Activate the focused button"
)


class HelpScreen(Screen):
    DEFAULT_CSS = """
    HelpScreen {
        layout: vertical;
    }
    #help-bar {
        height: 3;
        padding: 0 2;
        background: $primary 10%;
    }
    #help-bar .title {
        width: 1fr;
        content-align: left middle;
        text-style: bold;
        color: $primary;
    }
    #help-bar Button {
        margin: 0 0 0 1;
    }
    #help-body {
        padding: 1 4;
    }
    .help-section-title {
        text-style: bold;
        color: $primary;
        padding: 1 0 0 0;
    }
    .help-section-body {
        padding-bottom: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "back", "Back"),
    ]

    def compose(self) -> ComposeResult:
        with Horizontal(id="help-bar"):
            yield Static("Help", classes="title")
            yield Button("◀ Back", id="back", variant="primary")
        with VerticalScroll(id="help-body"):
            yield Static("What is this?", classes="help-section-title")
            yield Static(_WHAT, classes="help-section-body")
            yield Static("How do I use it?", classes="help-section-title")
            yield Static(_HOW, classes="help-section-body")
            yield Static("Keyboard shortcuts", classes="help-section-title")
            yield Static(_SHORTCUTS, classes="help-section-body")
            yield Static("About", classes="help-section-title")
            yield Static(
                f"Anki Community Deck Sync version {__version__}\n"
                "Built on top of anki-gitify.",
                classes="help-section-body",
            )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back":
            self.app.pop_screen()

    def action_back(self) -> None:
        self.app.pop_screen()
