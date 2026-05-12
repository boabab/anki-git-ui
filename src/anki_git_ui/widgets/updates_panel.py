"""UpdatesPanel: shows ``git log`` of recent commits on the remote branch.

Lives at the top of the deck-detail screen. Fetches once on mount, and the
user can click "Refresh" to fetch again.
"""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widgets import Button, RichLog, Static

from ..domain.text_utils import truncate
from ..workers.check_updates_worker import CommitLine


class UpdatesPanel(Vertical):
    DEFAULT_CSS = """
    UpdatesPanel {
        height: auto;
        border: round $panel-darken-1;
        padding: 1 2;
        margin-bottom: 1;
    }
    UpdatesPanel:dark {
        border: round $surface-lighten-2;
    }
    /* Header row = (title + status) on the left as one block, Refresh button
       on the right spanning the full block height. */
    UpdatesPanel > #updates-header-row {
        height: 3;
        width: 1fr;
        margin-bottom: 1;
    }
    UpdatesPanel > #updates-header-row > .updates-text {
        width: 1fr;
        height: auto;
    }
    UpdatesPanel > #updates-header-row > .updates-text > .updates-header {
        text-style: bold;
        padding-left: 1;
        margin-bottom: 1;
    }
    UpdatesPanel > #updates-header-row > .updates-text > .updates-status {
        color: $text-muted;
        padding-left: 1;
    }
    UpdatesPanel > RichLog {
        height: 7;
        background: $surface-darken-1;
        border: tall $surface-darken-2;
    }
    UpdatesPanel:dark > RichLog {
        border: tall $surface-lighten-1;
    }
    """

    class RefreshRequested(Message):
        """Posted when the user clicks Refresh — the screen owns the worker."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        # Keep the latest commits around so we can re-render on resize.
        self._commits: list[CommitLine] = []

    def compose(self) -> ComposeResult:
        with Horizontal(id="updates-header-row"):
            with Vertical(classes="updates-text"):
                yield Static("Git history", classes="updates-header")
                yield Static("Checking…", classes="updates-status", id="updates-status")
            yield Button("↻ Refresh", id="refresh-updates")
        yield RichLog(highlight=False, markup=False, max_lines=200, wrap=False)

    # ---------- public API ---------- #

    def set_status(self, text: str) -> None:
        self.query_one("#updates-status", Static).update(text)

    # Row layout: " • <date>  <subject…>  <hash>"
    # Leading space indents the bullets one cell past the header/status text.
    _BULLET = " • "
    _GAP = "  "
    _DATE_WIDTH = len("YYYY-MM-DD")  # 10
    _HASH_WIDTH = 7
    # Reserve room on the right so the vertical scrollbar (and a breath of
    # whitespace) doesn't sit on top of the commit hash.
    _RIGHT_GUTTER = 3

    def set_commits(self, commits: list[CommitLine]) -> None:
        self._commits = list(commits)
        self._render_commits()

    def on_resize(self, _) -> None:
        # Re-flow truncation when the window grows or shrinks so the date
        # column stays aligned at the right.
        if self._commits:
            self._render_commits()

    def _render_commits(self) -> None:
        log = self.query_one(RichLog)
        log.clear()
        if not self._commits:
            log.write("(no commits to show)")
            return
        subject_width = self._subject_column_width(log)
        for c in self._commits:
            log.write(self._format_commit(c, subject_width))

    def _subject_column_width(self, log: RichLog) -> int:
        """How many cells the subject column gets — the rest is fixed columns."""
        # ``content_size`` is the inner width after border/padding. Falls back
        # to a sensible default before the widget has been laid out.
        available = log.content_size.width or 80
        # Reserved: "• " + date + GAP + subject + GAP + hash + right gutter.
        reserved = (
            len(self._BULLET)
            + self._DATE_WIDTH
            + len(self._GAP)
            + len(self._GAP)
            + self._HASH_WIDTH
            + self._RIGHT_GUTTER
        )
        return max(10, available - reserved)

    @staticmethod
    def _format_commit(c: CommitLine, subject_width: int) -> Text:
        # Date on the left, subject in the middle (padded/truncated so the
        # hash stays right-aligned), hash on the right. New commits get a
        # cyan accent on the subject so they stand out from older history.
        if c.is_new:
            subj_style = "bold cyan"
            meta_style = "cyan"
            bullet_style = "bold cyan"
        else:
            subj_style = "default"
            meta_style = "dim"
            bullet_style = "dim"

        # Truncate with an ellipsis if the subject doesn't fit so the hash
        # stays at a fixed offset from the right edge; pad otherwise so the
        # date+hash column aligns across rows.
        subject = truncate(c.subject, subject_width).ljust(subject_width)

        line = Text()
        line.append(UpdatesPanel._BULLET, style=bullet_style)
        line.append(c.date, style=meta_style)
        line.append(UpdatesPanel._GAP, style=meta_style)
        line.append(subject, style=subj_style)
        line.append(UpdatesPanel._GAP, style=meta_style)
        line.append(c.short, style=meta_style)
        return line

    # ---------- events ---------- #

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "refresh-updates":
            event.stop()
            self.post_message(self.RefreshRequested())
