"""Modal screens — friendly, plain-English dialogs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Checkbox, Static


# ---------- ConfirmModal ---------- #


class ConfirmModal(ModalScreen[bool]):
    """Generic two-button confirmation. Returns True on confirm, False on cancel."""

    DEFAULT_CSS = """
    ConfirmModal {
        align: center middle;
    }
    #confirm-card {
        width: 70;
        height: auto;
        background: $surface;
        border: round $primary;
        padding: 2 3;
    }
    .confirm-title {
        text-style: bold;
        color: $primary;
        padding-bottom: 1;
    }
    .confirm-body {
        padding-bottom: 1;
    }
    #confirm-buttons {
        height: 3;
        align-horizontal: right;
        padding-top: 1;
    }
    #confirm-buttons Button {
        margin-left: 2;
    }
    """

    BINDINGS = [
        Binding("escape", "dismiss(False)", "Cancel", show=False),
    ]

    def __init__(
        self,
        *,
        title: str,
        body: str,
        confirm_label: str = "Yes",
        cancel_label: str = "Cancel",
        confirm_variant: str = "primary",
    ) -> None:
        super().__init__()
        self._title = title
        self._body = body
        self._confirm_label = confirm_label
        self._cancel_label = cancel_label
        self._confirm_variant = confirm_variant

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-card"):
            yield Static(self._title, classes="confirm-title")
            yield Static(self._body, classes="confirm-body")
            with Horizontal(id="confirm-buttons"):
                yield Button(self._cancel_label, id="cancel")
                yield Button(self._confirm_label, id="confirm", variant=self._confirm_variant)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "confirm")


# ---------- RemoveDeckModal ---------- #


@dataclass
class RemoveDeckResult:
    """Returned via dismiss when the user confirms removal."""

    delete_files: bool


class RemoveDeckModal(ModalScreen[RemoveDeckResult | None]):
    """Confirm removing a deck. Separates 'remove from list' from 'delete files'.

    Returns ``None`` on cancel, or :class:`RemoveDeckResult` on confirm.
    """

    DEFAULT_CSS = """
    RemoveDeckModal {
        align: center middle;
    }
    #remove-card {
        width: 75;
        height: auto;
        background: $surface;
        border: round $error;
        padding: 2 3;
    }
    .remove-title {
        text-style: bold;
        color: $error;
        padding-bottom: 1;
    }
    .remove-body {
        padding-bottom: 1;
    }
    .remove-path {
        color: $text-muted;
        padding-bottom: 1;
    }
    #delete-row {
        padding-bottom: 1;
    }
    .delete-help {
        color: $text-muted;
        padding-left: 4;
        padding-bottom: 1;
    }
    .remove-foot {
        color: $text-muted;
        padding-bottom: 1;
    }
    #remove-buttons {
        height: 3;
        align-horizontal: right;
        padding-top: 1;
    }
    #remove-buttons Button {
        margin-left: 2;
    }
    """

    BINDINGS = [
        Binding("escape", "dismiss(None)", "Cancel", show=False),
    ]

    def __init__(self, *, nickname: str, local_path: Path) -> None:
        super().__init__()
        self._nickname = nickname
        self._local_path = local_path

    def compose(self) -> ComposeResult:
        with Vertical(id="remove-card"):
            yield Static(f'Remove "{self._nickname}"?', classes="remove-title")
            yield Static(
                "We'll remove this deck from your list in this app.",
                classes="remove-body",
            )
            yield Static("The deck files on your computer:", classes="remove-body")
            yield Static(f"  {self._local_path}", classes="remove-path")
            yield Checkbox(
                "Also delete the deck files from my computer",
                value=False,
                id="delete-files",
            )
            yield Static(
                "Leave unchecked to keep the files; you can re-add the deck later "
                "by adding the same link.",
                classes="delete-help",
            )
            yield Static(
                "The .apkg file you already prepared (if any) won't be touched. "
                "Cards already imported into Anki stay in Anki — this app does not "
                "change Anki itself.",
                classes="remove-foot",
            )
            with Horizontal(id="remove-buttons"):
                yield Button("Cancel", id="cancel")
                yield Button("Remove", id="remove", variant="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            self.dismiss(None)
        elif event.button.id == "remove":
            delete = self.query_one("#delete-files", Checkbox).value
            self.dismiss(RemoveDeckResult(delete_files=delete))


# ---------- AnkiFileReadyModal ---------- #


class AnkiFileReadyModal(ModalScreen[str | None]):
    """Shown after a successful "Make Anki file" build.

    Returns one of: ``"open"`` (open with default app), ``"reveal"`` (show
    in file manager), or ``None`` (Done).
    """

    DEFAULT_CSS = """
    AnkiFileReadyModal {
        align: center middle;
    }
    #ready-card {
        width: 80;
        height: auto;
        background: $surface;
        border: round $success;
        padding: 2 3;
    }
    .ready-title {
        text-style: bold;
        color: $success;
        padding-bottom: 1;
    }
    .ready-body {
        padding-bottom: 1;
    }
    .ready-path {
        color: $text-muted;
        padding: 0 0 1 2;
    }
    #ready-buttons {
        height: 3;
        align-horizontal: right;
        padding-top: 1;
    }
    #ready-buttons Button {
        margin-left: 2;
    }
    """

    BINDINGS = [
        Binding("escape", "dismiss(None)", "Done", show=False),
    ]

    def __init__(self, *, apkg_path: Path) -> None:
        super().__init__()
        self._apkg_path = apkg_path

    def compose(self) -> ComposeResult:
        with Vertical(id="ready-card"):
            yield Static("Anki file is ready!", classes="ready-title")
            yield Static("We saved the file at:", classes="ready-body")
            yield Static(str(self._apkg_path), classes="ready-path")
            yield Static(
                "To finish, open Anki and use File → Import on this file.",
                classes="ready-body",
            )
            with Horizontal(id="ready-buttons"):
                yield Button("Show file", id="reveal")
                yield Button("Open in Anki", id="open")
                yield Button("Done", id="done", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "open":
            self.dismiss("open")
        elif bid == "reveal":
            self.dismiss("reveal")
        else:
            self.dismiss(None)


# ---------- AnkiLockedModal ---------- #


class AnkiLockedModal(ModalScreen[bool]):
    """Friendly "close Anki and try again" dialog.

    Returns ``True`` if the user clicks "Try again" (caller should re-run
    the worker), or ``False`` on Cancel.
    """

    DEFAULT_CSS = """
    AnkiLockedModal {
        align: center middle;
    }
    #locked-card {
        width: 70;
        height: auto;
        background: $surface;
        border: round $warning;
        padding: 2 3;
    }
    .locked-title {
        text-style: bold;
        color: $warning;
        padding-bottom: 1;
    }
    .locked-body {
        padding-bottom: 1;
    }
    .locked-hint {
        color: $text-muted;
        padding-bottom: 1;
    }
    #locked-buttons {
        height: 3;
        align-horizontal: right;
        padding-top: 1;
    }
    #locked-buttons Button {
        margin-left: 2;
    }
    """

    BINDINGS = [
        Binding("escape", "dismiss(False)", "Cancel", show=False),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="locked-card"):
            yield Static("Close Anki to continue", classes="locked-title")
            yield Static(
                "We need to make changes to your Anki collection, but Anki is open "
                "and has it locked. Please close Anki and click Try again.",
                classes="locked-body",
            )
            yield Static(
                "Your existing cards and reviews stay untouched — we only add the "
                "smart-deck definitions.",
                classes="locked-hint",
            )
            with Horizontal(id="locked-buttons"):
                yield Button("Cancel", id="cancel")
                yield Button("Try again", id="retry", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "retry")


# ---------- ErrorModal ---------- #


class ErrorModal(ModalScreen[None]):
    """Generic error message with optional collapsible technical details."""

    DEFAULT_CSS = """
    ErrorModal {
        align: center middle;
    }
    #error-card {
        width: 75;
        max-height: 80%;
        background: $surface;
        border: round $error;
        padding: 2 3;
    }
    .error-title {
        text-style: bold;
        color: $error;
        padding-bottom: 1;
    }
    .error-body {
        padding-bottom: 1;
    }
    .error-details-toggle {
        color: $text-muted;
        padding-bottom: 1;
    }
    .error-details {
        color: $text-muted;
        padding: 1 0 1 2;
        background: $surface-darken-1;
        display: none;
    }
    .show-details .error-details {
        display: block;
    }
    #error-buttons {
        height: 3;
        align-horizontal: right;
        padding-top: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "dismiss(None)", "Close", show=False),
    ]

    def __init__(self, *, title: str, body: str, details: str | None = None) -> None:
        super().__init__()
        self._title = title
        self._body = body
        self._details = details

    def compose(self) -> ComposeResult:
        with Vertical(id="error-card"):
            yield Static(self._title, classes="error-title")
            yield Static(self._body, classes="error-body")
            if self._details:
                yield Button("Show technical details", id="toggle-details", classes="error-details-toggle")
                yield Static(self._details, classes="error-details")
            with Horizontal(id="error-buttons"):
                yield Button("Close", id="close", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "close":
            self.dismiss(None)
        elif event.button.id == "toggle-details":
            card = self.query_one("#error-card", Vertical)
            if "show-details" in card.classes:
                card.remove_class("show-details")
                event.button.label = "Show technical details"
            else:
                card.add_class("show-details")
                event.button.label = "Hide technical details"
