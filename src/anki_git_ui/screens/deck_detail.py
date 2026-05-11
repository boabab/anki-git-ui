"""Deck detail screen — the screen the user spends most time on.

Hosts the four primary actions (Download updates / Make Anki file / Set up
filtered decks / Open deck folder) and the streaming activity log. All
long-running calls run in threaded workers; modal flows for success, error,
and Anki-locked cases.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from anki_gitify.api import CardOverrideError
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Static
from textual.worker import Worker, WorkerState
from yaml import YAMLError, safe_load

from ..domain.apkg_paths import (
    open_with_default_app,
    reveal_in_file_manager,
)
from ..domain.git_ops import CloneProgress, GitError
from ..domain.models import DeckEntry, DeckStatus
from ..widgets.log_panel import LogPanel
from ..workers.download_deck_worker import download_deck
from ..workers.make_apkg_worker import make_apkg
from ..workers.filtered_decks_worker import (
    FilteredDecksResult,
    RebuildFilteredDecksResult,
    apply_filtered_decks,
    is_anki_desktop_running,
    is_locked_error,
    rebuild_filtered_decks,
)
from ..workers.update_deck_worker import update_deck
from .modals import AnkiFileReadyModal, AnkiLockedModal, ConfirmModal, ErrorModal


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


class DeckDetailScreen(Screen):
    DEFAULT_CSS = """
    DeckDetailScreen {
        layout: vertical;
    }
    #detail-bar {
        height: 3;
        padding: 0 2;
        background: $primary 10%;
    }
    #detail-bar .title {
        width: 1fr;
        content-align: left middle;
        text-style: bold;
        color: $primary;
    }
    #detail-bar Button {
        margin: 0 0 0 1;
    }
    #detail-body {
        padding: 1 4;
    }
    .deck-meta {
        color: $text-muted;
    }
    .deck-status-line {
        text-style: bold;
        padding-top: 1;
        padding-bottom: 1;
    }
    .action-card {
        height: auto;
        border: round $surface-lighten-2;
        padding: 1 2;
        margin-bottom: 1;
    }
    .action-card Button {
        min-width: 30;
        margin-bottom: 1;
    }
    .action-card .button-row {
        height: auto;
        margin-bottom: 1;
    }
    .action-card .button-row Button {
        margin: 0 1 0 0;
    }
    .action-card .action-help {
        color: $text-muted;
    }
    .action-card.disabled .action-help {
        color: $text-muted 50%;
    }
    """

    BINDINGS = [
        Binding("escape", "back", "Back", show=False),
    ]

    def __init__(self, *, deck: DeckEntry, auto_download: bool = False) -> None:
        super().__init__()
        self._deck = deck
        self._auto_download = auto_download
        self._busy = False
        self._current_op: str | None = None  # "download" | "update" | "build"

    # ---------- compose ---------- #

    def compose(self) -> ComposeResult:
        with Horizontal(id="detail-bar"):
            yield Static(self._deck.nickname, classes="title")
            yield Button("◀ Back", id="back")

        with VerticalScroll(id="detail-body"):
            yield Static(self._deck.url, classes="deck-meta")
            yield Static(str(self._deck.local_path), classes="deck-meta")
            yield Static(self._status_line(), classes="deck-status-line", id="status-line")

            # Download / Update card
            with Vertical(classes="action-card", id="download-card"):
                yield Button(self._download_label(), id="download", variant="primary")
                yield Static(self._download_help(), classes="action-help", id="download-help")

            # Make Anki file card
            with Vertical(classes="action-card", id="make-card"):
                yield Button("Make Anki file", id="make")
                yield Static(
                    "Prepare a deck file you can open in Anki.",
                    classes="action-help",
                )

            # Filtered decks card — always shown so the action is discoverable.
            with Vertical(classes="action-card", id="filtered-card"):
                with Horizontal(classes="button-row"):
                    yield Button(
                        self._filtered_decks_button_label(),
                        id="filtered",
                        disabled=self._filtered_decks_disabled(),
                    )
                    yield Button(
                        "Rebuild all",
                        id="rebuild-filtered",
                        disabled=self._filtered_decks_disabled(),
                    )
                yield Static(
                    self._filtered_decks_help_text(),
                    classes="action-help",
                    id="filtered-help",
                )

            # Open folder card
            with Vertical(classes="action-card", id="open-card"):
                yield Button("Open deck folder", id="open-folder")
                yield Static(
                    "Show this deck's files on your computer in your file manager.",
                    classes="action-help",
                )

            yield LogPanel()

    def on_mount(self) -> None:
        if self._auto_download:
            self._start_download(initial=True)

    # ---------- helpers / labels ---------- #

    def _status_line(self) -> str:
        if self._deck.status is DeckStatus.NOT_DOWNLOADED:
            return "Status: Not downloaded yet"
        if self._deck.last_built_commit is None:
            prepared = "Last prepared: never"
        elif self._deck.last_built_commit == self._deck.last_pulled_commit:
            prepared = f"Last prepared: {_humanize(self._deck.last_built_at)} (same version)"
        else:
            prepared = (
                f"Last prepared: {_humanize(self._deck.last_built_at)} "
                "(an older version — make a new Anki file to refresh)"
            )
        downloaded = f"Last downloaded: {_humanize(self._deck.last_pulled_at)}"
        if self._deck.status is DeckStatus.UPDATES_AVAILABLE:
            return f"Status: {self._deck.updates_available} updates available · {downloaded} · {prepared}"
        return f"Status: Up to date · {downloaded} · {prepared}"

    def _download_label(self) -> str:
        if self._deck.status is DeckStatus.NOT_DOWNLOADED:
            return "Download deck"
        if self._deck.status is DeckStatus.UPDATES_AVAILABLE:
            return "Download updates"
        return "Check for updates"

    def _download_help(self) -> str:
        if self._deck.status is DeckStatus.NOT_DOWNLOADED:
            return "Save a copy of this deck onto your computer."
        return "Save the latest version of this deck onto your computer."

    def _filtered_decks_count(self) -> int:
        path = self._deck.local_path / "filtered_decks.yml"
        if not path.is_file():
            return 0
        try:
            data = safe_load(path.read_text(encoding="utf-8"))
        except (OSError, YAMLError):
            return 0
        if not isinstance(data, dict):
            return 0
        entries = data.get("filtered_decks") or []
        return len(entries) if isinstance(entries, list) else 0

    def _filtered_decks_button_label(self) -> str:
        count = self._filtered_decks_count()
        if count == 0:
            return "Set up filtered decks (none in this deck)"
        return f"Set up filtered decks ({count} found)"

    def _filtered_decks_help_text(self) -> str:
        if self._deck.status is DeckStatus.NOT_DOWNLOADED:
            return "Download this deck first to see whether it includes filtered-deck definitions."
        if self._filtered_decks_count() == 0:
            return "This deck doesn't include any filtered-deck definitions."
        return (
            "This deck includes special review settings. Use 'Set up' to add them "
            "to your Anki collection, or 'Rebuild all' to refresh the cards inside "
            "existing filtered decks. Anki must be closed first."
        )

    def _filtered_decks_disabled(self) -> bool:
        return self._filtered_decks_count() == 0

    # ---------- buttons ---------- #

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if self._busy and event.button.id != "back":
            self.app.notify(
                "Please wait for the current task to finish.", severity="information"
            )
            return
        bid = event.button.id
        if bid == "back":
            self.app.pop_screen()
        elif bid == "download":
            initial = self._deck.status is DeckStatus.NOT_DOWNLOADED
            self._start_download(initial=initial)
        elif bid == "make":
            self._start_make_apkg()
        elif bid == "filtered":
            self._start_filtered_decks()
        elif bid == "rebuild-filtered":
            self._start_rebuild_filtered()
        elif bid == "open-folder":
            if not reveal_in_file_manager(self._deck.local_path):
                self.app.notify(
                    f"Couldn't open {self._deck.local_path}.", severity="warning"
                )

    def action_back(self) -> None:
        self.app.pop_screen()

    # ---------- worker dispatch ---------- #

    def _start_download(self, *, initial: bool) -> None:
        self._busy = True
        self._current_op = "download" if initial else "update"
        log = self.query_one(LogPanel)
        log.clear()
        log.set_status(
            "Downloading…" if initial else "Checking for updates and downloading…"
        )
        log.set_progress(0, phase="Connecting")
        self._set_action_buttons_enabled(False)

        if initial:
            self.run_worker(
                self._do_initial_download,
                thread=True,
                exclusive=True,
                group="deck-actions",
            )
        else:
            self.run_worker(
                self._do_update,
                thread=True,
                exclusive=True,
                group="deck-actions",
            )

    def _start_filtered_decks(self) -> None:
        if is_anki_desktop_running():
            self._show_locked_modal(
                retry=self._start_filtered_decks, op_label="Filtered-decks setup"
            )
            return
        self._busy = True
        self._current_op = "filtered"
        log = self.query_one(LogPanel)
        log.clear()
        log.set_status("Setting up filtered decks…")
        self._set_action_buttons_enabled(False)
        self.run_worker(
            self._do_filtered_decks,
            thread=True,
            exclusive=True,
            group="deck-actions",
        )

    def _do_filtered_decks(self):
        return apply_filtered_decks(
            self._deck,
            self.app.config.anki,
            on_log=self._on_log,
        )

    def _start_rebuild_filtered(self) -> None:
        if is_anki_desktop_running():
            self._show_locked_modal(
                retry=self._start_rebuild_filtered, op_label="Rebuild"
            )
            return
        self._busy = True
        self._current_op = "rebuild"
        log = self.query_one(LogPanel)
        log.clear()
        log.set_status("Rebuilding filtered decks…")
        self._set_action_buttons_enabled(False)
        self.run_worker(
            self._do_rebuild_filtered,
            thread=True,
            exclusive=True,
            group="deck-actions",
        )

    def _do_rebuild_filtered(self):
        return rebuild_filtered_decks(
            self._deck,
            self.app.config.anki,
            on_log=self._on_log,
        )

    def _start_make_apkg(self) -> None:
        if self._deck.status is DeckStatus.NOT_DOWNLOADED:
            self.app.notify(
                "Download the deck first before making an Anki file.",
                title="Not downloaded yet",
                severity="warning",
            )
            return
        self._busy = True
        self._current_op = "build"
        log = self.query_one(LogPanel)
        log.clear()
        log.set_status("Preparing Anki file…")
        self._set_action_buttons_enabled(False)
        self.run_worker(
            self._do_make_apkg,
            thread=True,
            exclusive=True,
            group="deck-actions",
        )

    # ---------- thread workers ---------- #

    def _on_log(self, line: str) -> None:
        self.app.call_from_thread(self.query_one(LogPanel).add_line, line)

    def _on_progress(self, pg: CloneProgress) -> None:
        if pg.percent is None:
            return
        self.app.call_from_thread(
            self.query_one(LogPanel).set_progress, pg.percent, phase=pg.phase
        )

    def _do_initial_download(self) -> None:
        download_deck(self._deck, on_log=self._on_log, on_progress=self._on_progress)

    def _do_update(self) -> None:
        update_deck(self._deck, on_log=self._on_log)

    def _do_make_apkg(self):
        return make_apkg(
            self._deck,
            self.app.config.default_save_folder,
            on_log=self._on_log,
        )

    # ---------- worker completion ---------- #

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        if event.state not in (WorkerState.SUCCESS, WorkerState.ERROR):
            return
        op = self._current_op
        self._busy = False
        self._current_op = None
        self._set_action_buttons_enabled(True)
        log = self.query_one(LogPanel)
        log.set_progress(None)

        if event.state == WorkerState.SUCCESS:
            self._on_worker_success(op, event.worker.result)
        else:
            self._on_worker_error(op, event.worker.error)

    def _on_worker_success(self, op: str | None, result) -> None:
        log = self.query_one(LogPanel)
        if op == "download":
            self._deck.status = DeckStatus.UP_TO_DATE
            self.app.config.save()
            log.set_status("Download complete.")
        elif op == "update":
            self._deck.status = DeckStatus.UP_TO_DATE
            self._deck.updates_available = 0
            self.app.config.save()
            log.set_status(
                "Already up to date." if (result and result.no_changes) else "Updates downloaded."
            )
        elif op == "build":
            self.app.config.save()
            log.set_status("Anki file is ready.")
            apkg = self._deck.last_built_apkg
            if apkg is not None:
                self._show_ready_modal(apkg)
        elif op == "filtered" and isinstance(result, FilteredDecksResult):
            if result.locked:
                self._show_locked_modal(retry=self._start_filtered_decks, op_label="Filtered-decks setup")
            else:
                self._on_filtered_decks_done(result)
        elif op == "rebuild" and isinstance(result, RebuildFilteredDecksResult):
            if result.locked:
                self._show_locked_modal(retry=self._start_rebuild_filtered, op_label="Rebuild")
            else:
                self._on_rebuild_filtered_done(result)
        self._refresh_status_line()

    def _on_worker_error(self, op: str | None, err: BaseException | None) -> None:
        log = self.query_one(LogPanel)
        if op == "download" and isinstance(err, GitError):
            log.set_status("Download failed.")
            # Roll back the entry — partial state confuses the dashboard.
            if self._deck in self.app.app_state.decks:
                self.app.app_state.decks.remove(self._deck)
            if self._deck in self.app.config.decks:
                self.app.config.decks.remove(self._deck)
            self.app.config.save()

            def _after(_: None) -> None:
                self.app.pop_screen()

            self.app.push_screen(
                ErrorModal(title="We couldn't download the deck", body=str(err)),
                _after,
            )
            return

        if op == "update" and isinstance(err, GitError):
            log.set_status("Couldn't update the deck.")
            self.app.push_screen(
                ErrorModal(title="Couldn't update the deck", body=str(err))
            )
            return

        if op == "build" and isinstance(err, CardOverrideError):
            log.set_status("Build paused — needs your decision.")
            self._handle_card_overrides()
            return

        if op == "filtered" and is_locked_error(err):
            log.set_status("Filtered-decks setup paused — Anki is open.")

            def _retry(retry: bool | None) -> None:
                if retry:
                    self._start_filtered_decks()

            self.app.push_screen(AnkiLockedModal(), _retry)
            return

        if op == "filtered" and isinstance(err, FileNotFoundError):
            log.set_status("Couldn't set up filtered decks.")
            self.app.push_screen(
                ErrorModal(
                    title="We couldn't find your Anki",
                    body=str(err)
                    or "We couldn't locate your Anki collection. Open Settings to "
                    "pick the right Anki profile or collection file.",
                )
            )
            return

        if op == "filtered" and isinstance(err, (ValueError, RuntimeError)):
            log.set_status("Couldn't set up filtered decks.")
            self.app.push_screen(
                ErrorModal(
                    title="Couldn't set up filtered decks",
                    body="Something went wrong while applying the filtered-deck settings. "
                    "Please check your Anki profile in Settings and try again.",
                    details=f"{type(err).__name__}: {err}" if err else None,
                )
            )
            return

        if op == "rebuild" and is_locked_error(err):
            log.set_status("Rebuild paused — Anki is open.")

            def _retry_rebuild(retry: bool | None) -> None:
                if retry:
                    self._start_rebuild_filtered()

            self.app.push_screen(AnkiLockedModal(), _retry_rebuild)
            return

        if op == "rebuild" and isinstance(err, FileNotFoundError):
            log.set_status("Couldn't rebuild filtered decks.")
            self.app.push_screen(
                ErrorModal(
                    title="We couldn't find your Anki",
                    body=str(err)
                    or "We couldn't locate your Anki collection. Open Settings to "
                    "pick the right Anki profile or collection file.",
                )
            )
            return

        if op == "rebuild" and isinstance(err, (ValueError, RuntimeError)):
            log.set_status("Couldn't rebuild filtered decks.")
            self.app.push_screen(
                ErrorModal(
                    title="Couldn't rebuild filtered decks",
                    body="Something went wrong while rebuilding. Please check your "
                    "Anki profile in Settings and try again.",
                    details=f"{type(err).__name__}: {err}" if err else None,
                )
            )
            return

        if op == "build" and isinstance(err, (ValueError, FileNotFoundError)):
            log.set_status("Couldn't make the Anki file.")
            self.app.push_screen(
                ErrorModal(
                    title="The deck files don't look right",
                    body="We couldn't prepare an Anki file from this deck. The files "
                    "might be incomplete or in a format we don't understand.",
                    details=str(err),
                )
            )
            return

        # Generic fallback
        log.set_status("Something went wrong.")
        self.app.push_screen(
            ErrorModal(
                title="Something went wrong",
                body="We hit an unexpected error. The technical details below may "
                "help you figure out what happened.",
                details=f"{type(err).__name__}: {err}" if err else None,
            )
        )

    def _show_locked_modal(self, *, retry, op_label: str) -> None:
        log = self.query_one(LogPanel)
        log.set_status(f"{op_label} paused — Anki is open.")

        def _on_close(should_retry: bool | None) -> None:
            if should_retry:
                retry()

        self.app.push_screen(AnkiLockedModal(), _on_close)

    def _handle_card_overrides(self) -> None:
        def _on_choice(confirmed: bool | None) -> None:
            if not confirmed:
                self.query_one(LogPanel).set_status("Build cancelled.")
                return
            # Re-run the build with the override flag set.
            self._busy = True
            self._current_op = "build"
            self._set_action_buttons_enabled(False)
            log = self.query_one(LogPanel)
            log.set_status("Preparing Anki file (with cards.csv ignored)…")
            self.run_worker(
                lambda: make_apkg(
                    self._deck,
                    self.app.config.default_save_folder,
                    on_log=self._on_log,
                    ignore_card_overrides=True,
                ),
                thread=True,
                exclusive=True,
                group="deck-actions",
            )

        self.app.push_screen(
            ConfirmModal(
                title="This deck has special card placement",
                body=(
                    "Some cards in this deck live in different decks than their notes. "
                    "We can still prepare an Anki file, but those cards will all land "
                    "in their note's main deck. Continue anyway?"
                ),
                confirm_label="Yes, prepare anyway",
                cancel_label="Cancel",
                confirm_variant="primary",
            ),
            _on_choice,
        )

    def _on_filtered_decks_done(self, result: FilteredDecksResult) -> None:
        log = self.query_one(LogPanel)
        if result.created:
            for name in result.created:
                log.add_line(f"  + {name} (added)")
        if result.skipped:
            for name in result.skipped:
                log.add_line(f"  = {name} (already there)")
        if result.conflicts:
            for name in result.conflicts:
                log.add_line(f"  ! {name} (a normal deck with this name already exists)")

        if result.conflicts:
            log.set_status(
                f"Done — {len(result.created)} added, {len(result.conflicts)} couldn't be added."
            )
            self.app.push_screen(
                ErrorModal(
                    title="Some filtered decks couldn't be added",
                    body=(
                        "These names already exist as normal decks in your Anki "
                        "collection, so we left them alone. Rename the existing "
                        "deck in Anki and click 'Set up filtered decks' again to add "
                        "the filtered version:\n\n  "
                        + "\n  ".join(result.conflicts)
                    ),
                )
            )
            return

        if result.created:
            self.app.notify(
                f"Added {len(result.created)} filtered deck(s) to your Anki collection.",
                title="Filtered decks ready",
            )
        else:
            self.app.notify(
                "Filtered decks were already set up — nothing to add.",
                title="Already done",
            )
        log.set_status("Filtered decks ready.")

    def _on_rebuild_filtered_done(self, result: RebuildFilteredDecksResult) -> None:
        log = self.query_one(LogPanel)
        for name in result.rebuilt:
            log.add_line(f"  ✓ {name} (rebuilt)")
        for name in result.missing:
            log.add_line(f"  ? {name} (not in your Anki yet)")
        for name in result.conflicts:
            log.add_line(f"  ! {name} (a normal deck with this name already exists)")

        if result.total == 0:
            self.app.notify(
                "This deck has no filtered-deck definitions to rebuild.",
                title="Nothing to rebuild",
            )
            log.set_status("Nothing to rebuild.")
            return

        if not result.rebuilt and result.missing and not result.conflicts:
            log.set_status("Nothing rebuilt — filtered decks aren't in your Anki yet.")
            self.app.push_screen(
                ErrorModal(
                    title="No filtered decks to rebuild",
                    body=(
                        "These filtered decks aren't in your Anki collection yet. "
                        "Click 'Set up filtered decks' first, then 'Rebuild all' to "
                        "refresh them later."
                    ),
                )
            )
            return

        if result.conflicts:
            log.set_status(
                f"Done — {len(result.rebuilt)} rebuilt, {len(result.conflicts)} couldn't be rebuilt."
            )
            self.app.push_screen(
                ErrorModal(
                    title="Some decks couldn't be rebuilt",
                    body=(
                        "These names exist as normal decks (not filtered) in your "
                        "Anki collection, so we left them alone:\n\n  "
                        + "\n  ".join(result.conflicts)
                    ),
                )
            )
            return

        self.app.notify(
            f"Rebuilt {len(result.rebuilt)} filtered deck(s)."
            + (f" {len(result.missing)} not in Anki yet." if result.missing else ""),
            title="Filtered decks rebuilt",
        )
        log.set_status("Filtered decks rebuilt.")

    def _show_ready_modal(self, apkg: Path) -> None:
        def _on_ready(choice: str | None) -> None:
            if choice == "open":
                if not open_with_default_app(apkg):
                    self.app.notify(
                        f"Couldn't open {apkg.name}. Use 'Show file' and open it manually.",
                        severity="warning",
                    )
            elif choice == "reveal":
                reveal_in_file_manager(apkg)

        self.app.push_screen(AnkiFileReadyModal(apkg_path=apkg), _on_ready)

    # ---------- UI mutation helpers ---------- #

    def _set_action_buttons_enabled(self, enabled: bool) -> None:
        for btn_id in ("download", "make", "filtered", "rebuild-filtered", "open-folder"):
            try:
                btn = self.query_one(f"#{btn_id}", Button)
            except Exception:
                continue
            if btn_id in ("filtered", "rebuild-filtered") and self._filtered_decks_disabled():
                btn.disabled = True
                continue
            btn.disabled = not enabled

    def _refresh_status_line(self) -> None:
        try:
            self.query_one("#status-line", Static).update(self._status_line())
            self.query_one("#download", Button).label = self._download_label()
            self.query_one("#download-help", Static).update(self._download_help())
            filtered_btn = self.query_one("#filtered", Button)
            filtered_btn.label = self._filtered_decks_button_label()
            filtered_btn.disabled = self._filtered_decks_disabled()
            self.query_one("#rebuild-filtered", Button).disabled = self._filtered_decks_disabled()
            self.query_one("#filtered-help", Static).update(self._filtered_decks_help_text())
        except Exception:
            pass
