"""Add-deck wizard — two steps. No URL pre-validation; bad/private/non-HTTPS
links surface as friendly errors at download time."""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Input, Static
from textual.worker import Worker, WorkerState

from ..domain.git_ops import GitError, verify_remote
from ..domain.models import DeckEntry, DeckStatus
from ..workers.download_deck_worker import deck_local_path, deck_nickname


class AddDeckScreen(Screen):
    """Two-step add flow: paste link → name + folder → save and download."""

    DEFAULT_CSS = """
    AddDeckScreen {
        layout: vertical;
    }
    #add-bar {
        height: 3;
        padding: 0 2;
        background: $primary 10%;
    }
    #add-bar .title {
        width: 1fr;
        content-align: left middle;
        text-style: bold;
        color: $primary;
    }
    #add-body {
        padding: 1 4;
    }
    .step-heading {
        text-style: bold;
        color: $primary;
        padding-bottom: 1;
    }
    .field-label {
        padding: 1 0 0 0;
    }
    .field-help {
        color: $text-muted;
        padding-bottom: 1;
    }
    #add-buttons {
        height: auto;
        align-horizontal: right;
        padding-top: 1;
    }
    #add-buttons Button {
        margin-left: 2;
        min-width: 14;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
    ]

    def __init__(self) -> None:
        super().__init__(name="add-deck")
        self._step = 1  # 1 = URL entry, 2 = name + folder
        self._url = ""
        self._nickname = ""
        self._local_path = ""
        self._verifying = False

    # ---------- compose / render ---------- #

    def compose(self) -> ComposeResult:
        with Horizontal(id="add-bar"):
            yield Static(f"Add a new deck ({self._step} of 2)", classes="title")
            yield Button("◀ Back to dashboard", id="back-to-dashboard")
        if self._step == 1:
            yield from self._compose_step1()
        else:
            yield from self._compose_step2()

    def _compose_step1(self) -> ComposeResult:
        with VerticalScroll(id="add-body"):
            yield Static("Paste the link to the deck on GitHub:", classes="step-heading")
            yield Input(
                value=self._url,
                placeholder="https://github.com/<someone>/<deck-name>",
                id="url-input",
            )
            yield Static(
                "The link should start with https:// and look like the example above. "
                "We'll only download the deck — we don't need a GitHub account.",
                classes="field-help",
            )
            with Horizontal(id="add-buttons"):
                yield Button("Cancel", id="cancel")
                yield Button("Next", id="next", variant="primary")

    def _compose_step2(self) -> ComposeResult:
        cfg = self.app.config
        if not self._nickname:
            self._nickname = deck_nickname(self._url)
        if not self._local_path:
            self._local_path = str(deck_local_path(cfg.default_save_folder, self._url))
        with VerticalScroll(id="add-body"):
            yield Static("What should we call this deck?", classes="step-heading")
            yield Input(
                value=self._nickname,
                placeholder="My deck",
                id="nickname-input",
            )
            yield Static(
                "This is just a label shown in your list — pick anything you'll recognise.",
                classes="field-help",
            )

            yield Static(
                "Where should we save it on your computer?", classes="step-heading"
            )
            yield Input(
                value=self._local_path,
                placeholder=str(cfg.default_save_folder / "deck"),
                id="path-input",
            )
            yield Static(
                "We'll create this folder and download the deck files into it. "
                "If a folder with the same name already exists, we'll ask you to "
                "choose another.",
                classes="field-help",
            )

            with Horizontal(id="add-buttons"):
                yield Button("Back", id="prev")
                yield Button("Cancel", id="cancel")
                yield Button("Add and download", id="add", variant="primary")

    # ---------- event handlers ---------- #

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if self._verifying:
            return
        bid = event.button.id
        if bid in ("cancel", "back-to-dashboard"):
            self.app.pop_screen()
        elif bid == "next":
            url = self.query_one("#url-input", Input).value.strip()
            if not url:
                self.app.notify(
                    "Please paste a link first.",
                    title="Link is empty",
                    severity="warning",
                )
                return
            self._url = url
            self._verifying = True
            self.app.notify("Checking the link…", timeout=2)
            self.run_worker(
                lambda: verify_remote(self._url),
                thread=True,
                exclusive=True,
                group="add-deck-verify",
            )
        elif bid == "prev":
            # Save edits to step-2 fields so they don't reset on Back.
            self._capture_step2()
            self._step = 1
            self._refresh()
        elif bid == "add":
            self._submit()

    def action_cancel(self) -> None:
        self.app.pop_screen()

    # ---------- internals ---------- #

    def _refresh(self) -> None:
        """Re-mount the screen with the new step. Cheaper than tracking widget visibility."""
        self.app.switch_screen(_clone_self(self))

    def _capture_step2(self) -> None:
        try:
            self._nickname = self.query_one("#nickname-input", Input).value
        except Exception:
            pass
        try:
            self._local_path = self.query_one("#path-input", Input).value
        except Exception:
            pass

    def _submit(self) -> None:
        self._capture_step2()
        nickname = self._nickname.strip()
        local_path = self._local_path.strip()
        if not nickname:
            self.app.notify("Please give the deck a name.", severity="warning")
            return
        if not local_path:
            self.app.notify(
                "Please choose a folder to save the deck in.", severity="warning"
            )
            return

        local = Path(local_path).expanduser()
        if local.exists():
            self.app.notify(
                f"The folder {local} already exists. Please choose a different folder.",
                title="Folder already exists",
                severity="warning",
            )
            return

        # URL was already validated at step 1, so we can create + switch directly.
        deck = DeckEntry(
            nickname=nickname,
            url=self._url,
            local_path=local,
            status=DeckStatus.NOT_DOWNLOADED,
        )
        self.app.app_state.decks.append(deck)
        self.app.config.decks.append(deck)
        self.app.config.save()

        # Lazy import to avoid circular dependency.
        from .deck_detail import DeckDetailScreen

        # Replace add-deck with the deck-detail screen so Back from there
        # goes to the dashboard, not back to the add wizard.
        self.app.switch_screen(DeckDetailScreen(deck=deck, auto_download=True))

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        if event.state not in (WorkerState.SUCCESS, WorkerState.ERROR):
            return
        self._verifying = False
        if event.state == WorkerState.ERROR:
            self.app.notify(
                "We couldn't check that link.",
                title="Link is not valid",
                severity="error",
            )
            return
        err: GitError | None = event.worker.result
        if err is not None:
            self.app.notify(
                str(err),
                title="Link is not valid",
                severity="error",
            )
            return
        self._step = 2
        self._refresh()


def _clone_self(screen: AddDeckScreen) -> AddDeckScreen:
    new = AddDeckScreen()
    new._step = screen._step
    new._url = screen._url
    new._nickname = screen._nickname
    new._local_path = screen._local_path
    return new
