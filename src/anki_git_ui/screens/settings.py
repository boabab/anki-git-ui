"""Settings screen — Anki profile, default save folder, theme."""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Input, RadioButton, RadioSet, Static

from ..domain.profile_ops import detect_profiles


_CUSTOM_VALUE = "__custom__"


class SettingsScreen(Screen):
    DEFAULT_CSS = """
    SettingsScreen {
        layout: vertical;
    }
    #settings-bar {
        height: 3;
        padding: 0 2;
        background: $primary 10%;
    }
    #settings-bar .title {
        width: 1fr;
        content-align: left middle;
        text-style: bold;
        color: $primary;
    }
    #settings-bar Button {
        margin: 0 0 0 1;
    }
    #settings-body {
        padding: 1 4;
    }
    .settings-section {
        text-style: bold;
        color: $primary;
        padding: 1 0 0 0;
    }
    .settings-help {
        color: $text-muted;
        padding-bottom: 1;
    }
    .no-profiles {
        color: $warning;
        padding-bottom: 1;
    }
    #custom-collection-row {
        padding-bottom: 1;
    }
    .custom-collection-hidden {
        display: none;
    }
    #buttons-row {
        height: 3;
        align-horizontal: right;
        padding-top: 1;
    }
    #buttons-row Button {
        margin-left: 2;
        min-width: 12;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Back", show=False),
    ]

    def __init__(self) -> None:
        super().__init__(name="settings")
        base, profiles = detect_profiles()
        self._anki_base = base
        self._profiles = profiles

    def compose(self) -> ComposeResult:
        cfg = self.app.config
        selected_profile = cfg.anki.profile
        has_override = cfg.anki.collection_override is not None

        with Horizontal(id="settings-bar"):
            yield Static("Settings", classes="title")
            yield Button("◀ Back", id="back")

        with VerticalScroll(id="settings-body"):
            yield Static("Your Anki", classes="settings-section")
            if not self._profiles:
                yield Static(
                    f"We couldn't find an Anki profile at {self._anki_base}. "
                    "Open Anki once to create one, then come back here. You can "
                    "also point at a collection.anki2 file directly below.",
                    classes="no-profiles",
                )

            with RadioSet(id="anki-profile"):
                for name in self._profiles:
                    yield RadioButton(
                        name,
                        value=(selected_profile == name and not has_override),
                        id=f"profile-{_safe_id(name)}",
                    )
                yield RadioButton(
                    "Choose a different file…",
                    value=has_override,
                    id=f"profile-{_CUSTOM_VALUE}",
                )
            yield Input(
                value=str(cfg.anki.collection_override) if cfg.anki.collection_override else "",
                id="custom-collection",
                placeholder="/absolute/path/to/collection.anki2",
                classes="" if has_override else "custom-collection-hidden",
            )

            yield Static("Where new decks are saved on your computer", classes="settings-section")
            yield Static(
                "Each deck you subscribe to is saved as a folder inside this folder.",
                classes="settings-help",
            )
            yield Input(
                value=str(cfg.default_save_folder),
                id="save-folder",
                placeholder="~/AnkiDecks",
            )

            yield Static("Appearance", classes="settings-section")
            with RadioSet(id="theme"):
                yield RadioButton("Match my system", value=cfg.theme == "system", id="theme-system")
                yield RadioButton("Light", value=cfg.theme == "light", id="theme-light")
                yield RadioButton("Dark", value=cfg.theme == "dark", id="theme-dark")

            with Horizontal(id="buttons-row"):
                yield Button("Cancel", id="cancel")
                yield Button("Save", id="save", variant="primary")

    # ---------- event handlers ---------- #

    def on_radio_set_changed(self, event: RadioSet.Changed) -> None:
        if event.radio_set.id != "anki-profile":
            return
        is_custom = event.pressed.id == f"profile-{_CUSTOM_VALUE}"
        custom_input = self.query_one("#custom-collection", Input)
        if is_custom:
            custom_input.remove_class("custom-collection-hidden")
            custom_input.focus()
        else:
            custom_input.add_class("custom-collection-hidden")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "back" or bid == "cancel":
            self.app.pop_screen()
        elif bid == "save":
            self._save_and_back()

    def action_cancel(self) -> None:
        self.app.pop_screen()

    def _save_and_back(self) -> None:
        cfg = self.app.config

        # Profile selection
        radio_set = self.query_one("#anki-profile", RadioSet)
        pressed = radio_set.pressed_button
        if pressed is None or pressed.id is None:
            cfg.anki.profile = None
            cfg.anki.collection_override = None
        elif pressed.id == f"profile-{_CUSTOM_VALUE}":
            override_text = self.query_one("#custom-collection", Input).value.strip()
            if override_text:
                cfg.anki.profile = None
                cfg.anki.collection_override = Path(override_text).expanduser()
            else:
                self.app.notify(
                    "Please paste the path to your collection.anki2 file first.",
                    title="Anki file is missing",
                    severity="warning",
                )
                return
        else:
            assert pressed.id.startswith("profile-")
            cfg.anki.profile = pressed.label.plain
            cfg.anki.collection_override = None

        # Save folder
        save_folder_text = self.query_one("#save-folder", Input).value.strip()
        if save_folder_text:
            cfg.default_save_folder = Path(save_folder_text).expanduser()

        # Theme
        theme_radio = self.query_one("#theme", RadioSet).pressed_button
        if theme_radio is not None and theme_radio.id is not None:
            cfg.theme = theme_radio.id.removeprefix("theme-")

        cfg.save()
        # Apply the theme immediately so the change is visible without a relaunch.
        self.app.apply_theme()
        self.app.notify("Settings saved.", title="Saved")
        self.app.pop_screen()


def _safe_id(text: str) -> str:
    return "".join(c if c.isalnum() else "-" for c in text.lower()).strip("-") or "x"
