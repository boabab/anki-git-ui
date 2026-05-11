"""LogPanel: a streaming log + progress bar combo for long-running operations.

Used by the deck detail screen during downloads, builds, and filtered-deck
applications. Lines arrive via :py:meth:`add_line`; progress updates via
:py:meth:`set_progress` (0-100 plus an optional phase label).
"""

from __future__ import annotations

from datetime import datetime

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import ProgressBar, RichLog, Static


class LogPanel(Vertical):
    DEFAULT_CSS = """
    LogPanel {
        height: auto;
        border: round $border-blurred;
        padding: 1 2;
    }
    LogPanel:dark {
        border: round $surface-lighten-2;
    }
    LogPanel > .log-status {
        color: $text-muted;
        padding-bottom: 1;
    }
    LogPanel > RichLog {
        height: 12;
        background: $surface-darken-1;
        border: tall $surface-darken-2;
    }
    LogPanel > ProgressBar {
        margin-top: 1;
        display: none;
    }
    LogPanel.show-progress > ProgressBar {
        display: block;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("Ready.", classes="log-status")
        yield RichLog(highlight=False, markup=False, max_lines=2000, wrap=False)
        yield ProgressBar(total=100, show_percentage=True, show_eta=False)

    # ---------- public API ---------- #

    def set_status(self, text: str) -> None:
        self.query_one(".log-status", Static).update(text)

    def add_line(self, text: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        self.query_one(RichLog).write(f"[{ts}] {text}")

    def set_progress(self, percent: int | None, *, phase: str | None = None) -> None:
        bar = self.query_one(ProgressBar)
        if percent is None:
            self.remove_class("show-progress")
            return
        self.add_class("show-progress")
        bar.update(progress=max(0, min(100, percent)))
        if phase:
            self.set_status(f"{phase}…")

    def clear(self) -> None:
        self.query_one(RichLog).clear()
        self.remove_class("show-progress")
        self.set_status("Ready.")
