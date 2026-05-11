"""DeckCard: one row in the dashboard list.

Each card shows the deck nickname, status (in plain English), and two
buttons. The whole card is clickable to open the deck's detail screen, but
the visible buttons are the discoverable interaction.
"""

from __future__ import annotations

from datetime import datetime, timezone

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widgets import Button, Static

from ..domain.models import DeckEntry, DeckStatus, status_label


def _humanize(dt: datetime | None, fallback: str = "never") -> str:
    if dt is None:
        return fallback
    delta = datetime.now(timezone.utc) - (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc))
    secs = int(delta.total_seconds())
    if secs < 60:
        return "just now"
    if secs < 3600:
        return f"{secs // 60} minute{'s' if secs >= 120 else ''} ago"
    if secs < 86400:
        return f"{secs // 3600} hour{'s' if secs >= 7200 else ''} ago"
    days = secs // 86400
    return f"{days} day{'s' if days != 1 else ''} ago"


def _detail_line(deck: DeckEntry) -> str:
    label = status_label(deck.status, count=deck.updates_available)
    if deck.status is DeckStatus.NOT_DOWNLOADED:
        return label
    last = _humanize(deck.last_built_at, fallback="never")
    return f"{label} · last prepared {last}"


class DeckCard(Vertical):
    """A single deck row, shown as a card with two action buttons."""

    DEFAULT_CSS = """
    DeckCard {
        height: auto;
        border: round $border-blurred;
        padding: 1 2;
        margin-bottom: 1;
    }
    DeckCard:dark {
        border: round $surface-lighten-2;
    }
    DeckCard .deck-title {
        text-style: bold;
        color: $primary;
    }
    DeckCard .deck-detail {
        color: $text-muted;
        padding-bottom: 1;
    }
    DeckCard .deck-actions {
        height: 3;
        align-horizontal: right;
    }
    DeckCard .deck-actions Button {
        margin-left: 2;
    }
    """

    class Open(Message):
        def __init__(self, nickname: str) -> None:
            super().__init__()
            self.nickname = nickname

    class Remove(Message):
        def __init__(self, nickname: str) -> None:
            super().__init__()
            self.nickname = nickname

    def __init__(self, deck: DeckEntry) -> None:
        super().__init__(id=f"deck-{_slug(deck.nickname)}")
        self._deck = deck

    def compose(self) -> ComposeResult:
        yield Static(self._deck.nickname, classes="deck-title")
        yield Static(_detail_line(self._deck), classes="deck-detail")
        with Horizontal(classes="deck-actions"):
            yield Button("Open", id="open", variant="primary")
            yield Button("Remove", id="remove")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        if event.button.id == "open":
            self.post_message(self.Open(self._deck.nickname))
        elif event.button.id == "remove":
            self.post_message(self.Remove(self._deck.nickname))


def _slug(text: str) -> str:
    return "".join(c if c.isalnum() else "-" for c in text.lower()).strip("-")
