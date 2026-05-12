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

    CSS_PATH = [
        "styles/app.tcss",
        "styles/components.tcss",
        "styles/widgets.tcss",
        "styles/screens.tcss",
        "styles/modals.tcss",
    ]

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
