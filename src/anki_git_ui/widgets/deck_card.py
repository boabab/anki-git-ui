"""DeckCard: one row in the dashboard list.

Each card shows the deck nickname, status (in plain English), and an
"Open" button. The whole card is clickable to open the deck's detail
screen; deletion happens from inside the detail view.
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
    last = _humanize(deck.last_pulled_at, fallback="never")
    return f"{label} · last downloaded {last}"


class DeckCard(Vertical):
    """A single deck row, shown as a card with two action buttons."""

    DEFAULT_CSS = """
    DeckCard {
        height: auto;
        border: round $panel-darken-1;
        padding: 1 2;
        margin-bottom: 1;
    }
    DeckCard:dark {
        border: round $surface-lighten-2;
    }
    /* Header is title + detail line as a single block on the left, with the
       Open button on the right spanning the full block height. */
    DeckCard .deck-header {
        height: 3;
        width: 1fr;
    }
    DeckCard .deck-text {
        width: 1fr;
        height: auto;
    }
    DeckCard .deck-title {
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }
    DeckCard .deck-detail {
        color: $text-muted;
    }
    """

    class Open(Message):
        def __init__(self, nickname: str) -> None:
            super().__init__()
            self.nickname = nickname

    def __init__(self, deck: DeckEntry) -> None:
        super().__init__(id=f"deck-{_slug(deck.nickname)}")
        self._deck = deck

    def compose(self) -> ComposeResult:
        with Horizontal(classes="deck-header"):
            with Vertical(classes="deck-text"):
                yield Static(self._deck.nickname, classes="deck-title")
                yield Static(_detail_line(self._deck), classes="deck-detail")
            yield Button("Open", id="open", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        if event.button.id == "open":
            self.post_message(self.Open(self._deck.nickname))


def _slug(text: str) -> str:
    return "".join(c if c.isalnum() else "-" for c in text.lower()).strip("-")
