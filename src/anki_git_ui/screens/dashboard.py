"""Dashboard — list of tracked decks. Mouse-first."""

from __future__ import annotations

from datetime import datetime, timezone

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Footer, Static
from textual.worker import Worker, WorkerState

from ..domain.models import DeckEntry, DeckStatus
from ..widgets.deck_card import DeckCard
from ..workers.check_updates_worker import check_for_updates


def _humanize(dt: datetime | None) -> str:
    if dt is None:
        return "never"
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
    /* Decks header: "Your community decks" + status on the left, Refresh
       on the right — mirrors the UpdatesPanel pattern. */
    #decks-header {
        height: 3;
        width: 1fr;
        margin-bottom: 1;
    }
    #decks-header > .decks-text {
        width: 1fr;
        height: auto;
    }
    #decks-header > .decks-text > .section-title {
        text-style: bold;
        margin-bottom: 1;
    }
    #decks-header > .decks-text > .decks-status {
        color: $text-muted;
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

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._is_refreshing: bool = False
        self._last_refresh_at: datetime | None = None

    def compose(self) -> ComposeResult:
        with Horizontal(id="app-bar"):
            yield Static("Anki Community Deck Sync", classes="title")
            yield Button("Help", id="help")
            yield Button("Settings", id="settings")
        with VerticalScroll(id="dashboard-body"):
            with Horizontal(id="decks-header"):
                with Vertical(classes="decks-text"):
                    yield Static("Your community decks", classes="section-title")
                    yield Static(
                        self._refresh_status_text(),
                        classes="decks-status",
                        id="decks-status",
                    )
                yield Button("↻ Refresh", id="refresh-decks")
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

    def on_mount(self) -> None:
        # Refresh on first paint so deck cards show fresh statuses.
        self._start_refresh()

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
        elif bid == "refresh-decks":
            self._start_refresh()

    # ---------- refresh-all flow ---------- #

    def _refresh_status_text(self) -> str:
        if self._is_refreshing:
            return "• Refreshing decks…"
        if self._last_refresh_at is not None:
            return f"• Last refreshed {_humanize(self._last_refresh_at)}"
        return ""

    def _update_status_label(self) -> None:
        try:
            self.query_one("#decks-status", Static).update(self._refresh_status_text())
        except Exception:
            pass

    def _start_refresh(self) -> None:
        if self._is_refreshing:
            return
        # Nothing to refresh if there are no decks (or they're all NOT_DOWNLOADED).
        if not any(
            d.status is not DeckStatus.NOT_DOWNLOADED
            for d in self.app.app_state.decks
        ):
            self._last_refresh_at = datetime.now(timezone.utc)
            self._update_status_label()
            return
        self._is_refreshing = True
        self._update_status_label()
        self.run_worker(
            self._do_refresh_all,
            thread=True,
            exclusive=True,
            group="dashboard-refresh",
            name="dashboard-refresh",
        )

    def _do_refresh_all(self) -> None:
        for deck in list(self.app.app_state.decks):
            if deck.status is DeckStatus.NOT_DOWNLOADED:
                continue
            result = check_for_updates(deck)
            if result.error is not None:
                continue
            new_count = sum(1 for c in result.commits if c.is_new)
            if new_count > 0:
                deck.status = DeckStatus.UPDATES_AVAILABLE
                deck.updates_available = new_count
            else:
                deck.status = DeckStatus.UP_TO_DATE
                deck.updates_available = 0

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        if event.worker.name != "dashboard-refresh":
            return
        if event.state not in (WorkerState.SUCCESS, WorkerState.ERROR):
            return
        self._is_refreshing = False
        self._last_refresh_at = datetime.now(timezone.utc)
        self._update_status_label()
        # Surgically update each card's detail line — avoid a full recompose
        # so any in-flight user interactions (button clicks, scrolling) aren't
        # disrupted.
        for card in self.query(DeckCard):
            card.refresh_display()

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
