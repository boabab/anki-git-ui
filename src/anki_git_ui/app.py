"""Top-level Textual app — screen registration, global bindings, app state."""

from __future__ import annotations

from textual.app import App
from textual.binding import Binding

from .config import Config, config_exists
from .domain.theme import CUSTOM_THEMES, resolve_theme
from .screens.add_deck import AddDeckScreen
from .screens.dashboard import DashboardScreen
from .screens.help import HelpScreen
from .screens.settings import SettingsScreen
from .screens.welcome import WelcomeScreen
from .state import AppState


class AnkiGitUIApp(App):
    """Friendly, mouse-first TUI for anki-gitify."""

    TITLE = "Anki Community Deck Sync"
    SUB_TITLE = ""

    CSS = """
    .title {
        height: 3;
        content-align: left middle;
    }

    Screen {
        background: $surface;
    }

    /* Project-wide Button styling.
       - `border: none` instead of Textual's default `tall`. The tall border
         relies on ▊ (LEFT SEVEN EIGHTHS BLOCK) for the left edge, which
         renders as transparent on some terminal fonts (notably macOS
         Terminal.app's default), making buttons look like their left edge
         is "cut off". A no-border button is just a colored rectangle —
         visible everywhere, no font-rendering surprises.
       - The button's background is $panel — distinct from $surface so it
         reads as a clickable element against the screen background even
         in light mode without needing a border at all.
       - :focus only bolds the label. Coloring the border on focus made the
         "previously clicked" button look like it stayed orange when the
         user came back to the screen, because Textual restores focus on
         screen pop. */
    Button {
        height: 3;
        min-width: 14;
        border: none;
        padding: 0 2;
        background: $panel;
        color: $foreground;
    }
    Button:hover {
        background: $primary 30%;
    }
    Button:focus {
        text-style: bold;
    }
    Button:disabled {
        text-opacity: 40%;
        background-tint: $surface 30%;
    }

    Button.-primary {
        background: $primary;
        color: white;
        text-style: bold;
    }
    Button.-primary:hover {
        background: $primary-lighten-1;
    }

    Button.-error {
        background: $error;
        color: white;
        text-style: bold;
    }
    Button.-error:hover {
        background: $error-lighten-1;
    }

    /* Inline header buttons — sized just wide enough to fit the label
       (Textual adds `line-pad: 1` on Button, stealing 2 cells beyond our
       padding). Height stays 3 so the button reads as a proper button; the
       title widget alongside is set to height 3 + middle-aligned in CSS so
       the label visually sits next to the button on its middle row. */
    #refresh-updates, #refresh-decks {
        min-width: 15;
        width: 15;
    }
    DeckCard #open {
        min-width: 10;
        width: 10;
    }

    /* Input / RadioSet borders: match the card/log-panel grays.
       - light mode: $panel-darken-1 (darker than surface)
       - dark mode:  $surface-lighten-2 (lighter than surface)
       Focus uses $primary so an active field still pops. */
    Input, RadioSet {
        border: tall $panel-darken-1;
    }
    Input:dark, RadioSet:dark {
        border: tall $surface-lighten-2;
    }
    Input:focus, RadioSet:focus {
        border: tall $primary;
    }
    """

    SCREENS = {
        "welcome": WelcomeScreen,
        "dashboard": DashboardScreen,
        "help": HelpScreen,
        "settings": SettingsScreen,
        "add-deck": AddDeckScreen,
    }

    BINDINGS = [
        Binding("q", "quit", "Quit", priority=True),
        Binding("ctrl+c", "quit", "Quit", show=False, priority=True),
    ]

    def __init__(self, *, config: Config | None = None, app_state: AppState | None = None) -> None:
        super().__init__()
        self.config: Config = config if config is not None else Config.load()
        if app_state is not None:
            self.app_state = app_state
        else:
            self.app_state = AppState(
                decks=list(self.config.decks),
                anki=self.config.anki,
                default_save_folder=self.config.default_save_folder,
                theme=self.config.theme,
                is_first_run=not config_exists(),
            )

    def on_mount(self) -> None:
        for theme in CUSTOM_THEMES:
            self.register_theme(theme)
        self.apply_theme()
        if self.app_state.is_first_run:
            self.push_screen("welcome")
        else:
            self.push_screen("dashboard")

    def apply_theme(self) -> None:
        """Apply ``self.config.theme`` to the running app.

        Called on mount and again from the Settings screen after a save so
        a theme change takes effect in the current session, not just on the
        next launch. ``"system"`` is resolved to light/dark via :mod:`darkdetect`.
        """
        try:
            self.theme = resolve_theme(self.config.theme)
        except Exception:
            # Unknown theme name → fall back to Textual's default. Settings
            # may write something unexpected if the file was hand-edited.
            self.theme = "textual-dark"

    def action_quit(self) -> None:
        self.exit()
