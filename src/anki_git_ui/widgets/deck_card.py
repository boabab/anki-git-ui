"""DeckCard: one row in the dashboard list.

Each card shows the deck nickname, status (in plain English), and an
"Open" button. The whole card is clickable to open the deck's detail
screen; deletion happens from inside the detail view.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.css.query import NoMatches
from textual.message import Message
from textual.widgets import Button, Static

from ..domain.models import DeckEntry, DeckStatus, status_label
from ..domain.text_utils import humanize_age


def _detail_line(deck: DeckEntry) -> str:
    label = status_label(deck.status, count=deck.updates_available)
    if deck.status is DeckStatus.NOT_DOWNLOADED:
        return label
    last = humanize_age(deck.last_pulled_at, fallback="never")
    return f"{label} · last downloaded {last}"


class DeckCard(Vertical):
    """A single deck row, shown as a card with two action buttons."""

    DEFAULT_CLASSES = "card"

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

    def refresh_display(self) -> None:
        """Re-render based on the current deck state — used after a dashboard
        refresh so cards reflect the new status without a recompose."""
        try:
            self.query_one(".deck-detail", Static).update(_detail_line(self._deck))
        except NoMatches:
            self.log.debug(".deck-detail not in DOM during refresh")


def _slug(text: str) -> str:
    return "".join(c if c.isalnum() else "-" for c in text.lower()).strip("-")
