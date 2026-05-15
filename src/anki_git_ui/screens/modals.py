"""Modal screens — friendly, plain-English dialogs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Static


# ---------- ConfirmModal ---------- #


class ConfirmModal(ModalScreen[bool]):
    """Generic two-button confirmation. Returns True on confirm, False on cancel."""

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
    """Returned via dismiss when the user confirms removal.

    Kept as a dataclass for future-proofing even though it currently has no
    fields — the modal always deletes the files now.
    """


class RemoveDeckModal(ModalScreen[RemoveDeckResult | None]):
    """Confirm removing a deck. Always deletes the local files on confirm.

    Returns ``None`` on cancel, or :class:`RemoveDeckResult` on confirm.
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
                "We'll remove this deck from your list and delete its files "
                "from your computer:",
                classes="remove-body",
            )
            yield Static(f"  {self._local_path}", classes="remove-path")
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
            self.dismiss(RemoveDeckResult())


# ---------- AnkiLockedModal ---------- #


class AnkiLockedModal(ModalScreen[bool]):
    """Friendly "close Anki and try again" dialog.

    Returns ``True`` if the user clicks "Try again" (caller should re-run
    the worker), or ``False`` on Cancel.
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
                "filtered-deck definitions.",
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
