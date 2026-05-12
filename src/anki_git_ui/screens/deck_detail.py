"""Deck detail screen — the screen the user spends most time on.

Hosts the primary actions (Download changes / Set up filtered decks) and the
streaming activity log. Downloads automatically chain into an Anki-file
build; the build result (clickable apkg path + "Open in Anki" button) is
surfaced inside the LogPanel. A top-of-screen UpdatesPanel fetches the
remote and lists recent commits so the user can see what's available.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from anki_gitify.api import CardOverrideError
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.css.query import NoMatches
from textual.screen import Screen
from textual.widgets import Button, Static
from textual.worker import Worker, WorkerState
from yaml import YAMLError, safe_load

from ..domain.apkg_paths import open_with_default_app, reveal_in_file_manager
from ..domain.deck_ops import delete_deck_files
from ..domain.text_utils import format_path, humanize_age, truncate
from ..domain.git_ops import CloneProgress, GitError
from ..domain.models import DeckEntry, DeckStatus
from ..widgets.log_panel import LogPanel
from ..widgets.updates_panel import UpdatesPanel
from ..workers.check_updates_worker import CheckUpdatesResult, check_for_updates
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
from .modals import AnkiLockedModal, ConfirmModal, ErrorModal, RemoveDeckModal, RemoveDeckResult


class _MetaLink(Static):
    """The clickable link/path inside a meta row — hover-underlined, not the whole line.

    Truncates itself with `…` if its allotted width can't fit the full text,
    so the row stays one line tall regardless of URL/path length.
    """

    DEFAULT_CSS = """
    _MetaLink {
        width: 1fr;
        color: $text-muted;
    }
    _MetaLink:hover {
        color: $primary;
        text-style: underline;
    }
    """

    def __init__(self, text: str, *, on_open: Callable[[], None], **kwargs) -> None:
        super().__init__("", **kwargs)
        self._on_open = on_open
        self._full_text = text

    def on_mount(self) -> None:
        self._refresh_display()

    def on_resize(self, _) -> None:
        self._refresh_display()

    def update(self, renderable="") -> None:
        # Called by external code (e.g. _show_build_result) to swap the link.
        self._full_text = str(renderable)
        self._refresh_display()

    def _refresh_display(self) -> None:
        width = self.size.width
        super().update(truncate(self._full_text, width) if width > 0 else self._full_text)

    def on_click(self) -> None:
        self._on_open()


class DeckDetailScreen(Screen):
    BINDINGS = [
        Binding("escape", "back", "Back", show=False),
    ]

    def __init__(self, *, deck: DeckEntry, auto_download: bool = False) -> None:
        super().__init__()
        self._deck = deck
        self._auto_download = auto_download
        self._busy = False
        # "download" | "update" | "build" | "filtered" | "rebuild" | "check"
        self._current_op: str | None = None
        # Track whether we should chain a build after the next download/update.
        self._chain_build: bool = False
        # Path of the most recently built .apkg — used by the "Open in Anki"
        # button and the clickable link inside the download card.
        self._apkg_path: Path | None = None

    # ---------- compose ---------- #

    def compose(self) -> ComposeResult:
        with Horizontal(id="detail-bar", classes="app-bar"):
            yield Static(self._deck.nickname, classes="title")
            yield Button("◀ Back", id="back")

        with VerticalScroll(id="detail-body"):
            with Vertical(classes="action-card card", id="links-card"):
                yield Static("Click to open", classes="card-title")
                with Horizontal(classes="meta-row"):
                    yield Static("Remote repository: ", classes="meta-prefix")
                    yield _MetaLink(
                        self._deck.url, on_open=self._open_remote_repository
                    )
                with Horizontal(classes="meta-row"):
                    yield Static("Local folder: ", classes="meta-prefix")
                    yield _MetaLink(
                        format_path(self._deck.local_path),
                        on_open=self._open_local_folder,
                    )
                with Horizontal(classes="meta-row", id="apkg-row"):
                    yield Static("Anki deck file: ", classes="meta-prefix")
                    yield _MetaLink(
                        "", on_open=self._reveal_apkg, id="apkg-link"
                    )

            yield UpdatesPanel(id="updates-panel")

            # Download / Update card — also auto-builds the .apkg on success.
            with Vertical(classes="action-card card", id="download-card"):
                yield Static(
                    self._status_line(),
                    classes="deck-status-line",
                    id="status-line",
                )
                yield Button(self._download_label(), id="download")
                yield Button(
                    "(Re)import deck to Anki",
                    id="open-in-anki",
                    classes="build-row",
                )
                yield Static(self._download_help(), classes="action-help", id="download-help")

            # Filtered decks card — always shown so the action is discoverable.
            with Vertical(classes="action-card card", id="filtered-card"):
                yield Button(
                    self._filtered_decks_button_label(),
                    id="filtered",
                    disabled=self._filtered_decks_disabled(),
                )
                yield Button(
                    "Rebuild all (apply filters)",
                    id="rebuild-filtered",
                    disabled=self._filtered_decks_disabled(),
                )
                yield Static(
                    self._filtered_decks_help_text(),
                    classes="action-help",
                    id="filtered-help",
                )

            yield LogPanel()

            # Remove this deck — destructive, lives at the bottom of the screen.
            with Vertical(classes="action-card card", id="remove-card"):
                yield Button(
                    "Remove this deck", id="remove-deck", variant="error"
                )
                yield Static(
                    "Remove this deck from your list and delete its files "
                    "from your computer.",
                    classes="action-help",
                )

    def on_mount(self) -> None:
        # If we've previously built an apkg for this deck, surface it right
        # away so the user can re-open it without re-downloading. Don't scroll
        # to it here — we scroll the download card to the top instead, so the
        # primary action is the first thing the user sees.
        if self._deck.last_built_apkg is not None and self._deck.last_built_apkg.exists():
            self._show_build_result(self._deck.last_built_apkg, scroll=False)
        self._refresh_button_variants()
        # Land on the download card after the first layout pass — the
        # links/updates context lives one scroll up.
        self.call_after_refresh(self._scroll_to_download_card)

        if self._auto_download:
            self._start_download(initial=True)
        elif self._deck.status is not DeckStatus.NOT_DOWNLOADED:
            # Background fetch so the UpdatesPanel reflects the remote on
            # arrival — doesn't block any user-initiated action.
            self._start_check_updates()
        else:
            self.query_one(UpdatesPanel).set_status(
                "Download the deck first to see its commit history."
            )

    # ---------- helpers / labels ---------- #

    def _status_line(self) -> str:
        if self._deck.status is DeckStatus.NOT_DOWNLOADED:
            return "Status: Not downloaded yet"
        downloaded = f"Last download: {humanize_age(self._deck.last_pulled_at)}"
        if self._deck.status is DeckStatus.UPDATES_AVAILABLE:
            status = f"Status: {self._deck.updates_available} updates available"
        else:
            status = "Status: Up to date"
        return f"{status}\n{downloaded}"

    def _download_label(self) -> str:
        if self._deck.status is DeckStatus.NOT_DOWNLOADED:
            return "Download deck"
        return "Download latest updates"

    def _download_help(self) -> str:
        if self._deck.status is DeckStatus.NOT_DOWNLOADED:
            return "Save a copy of this deck onto your computer and prepare an Anki deck file."
        return (
            "Pull the latest updates from the remote and import the latest Anki deck file."
        )

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
            return (
                "Filtered decks are saved searches that build focused review "
                "sessions (e.g. only due cards, or only cards with a given tag). "
                "Download this deck first to see whether it ships with any."
            )
        if self._filtered_decks_count() == 0:
            return (
                "This deck doesn't ship with any filtered-deck definitions, so "
                "there's nothing to set up here."
            )
        return (
            "This deck ships with filtered-deck definitions — saved searches "
            "that build focused review sessions.\n"
            "\n"
            "\"Set up filtered decks\" adds them to your Anki collection.\n"
            "\n"
            "\"Rebuild all\" refreshes the cards inside the "
            "existing ones to match the latest deck contents.\n"
            "\n"
            "Anki must be closed first."
        )

    def _filtered_decks_disabled(self) -> bool:
        return self._filtered_decks_count() == 0

    # ---------- buttons ---------- #

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        # The "Open in Anki" button stays usable during operations — it just
        # opens a previously built file and doesn't touch deck state.
        if bid == "open-in-anki":
            self._open_in_anki()
            return
        if self._busy and bid != "back":
            self.app.notify(
                "Please wait for the current task to finish.", severity="information"
            )
            return
        if bid == "back":
            self.app.pop_screen()
        elif bid == "download":
            initial = self._deck.status is DeckStatus.NOT_DOWNLOADED
            self._start_download(initial=initial)
        elif bid == "filtered":
            self._start_filtered_decks()
        elif bid == "rebuild-filtered":
            self._start_rebuild_filtered()
        elif bid == "remove-deck":
            self._start_remove_deck()

    def on_updates_panel_refresh_requested(
        self, _: UpdatesPanel.RefreshRequested
    ) -> None:
        if self._busy:
            self.app.notify(
                "Please wait for the current task to finish.", severity="information"
            )
            return
        if self._deck.status is DeckStatus.NOT_DOWNLOADED:
            self.query_one(UpdatesPanel).set_status(
                "Download the deck first to see its commit history."
            )
            return
        self._start_check_updates()

    def action_back(self) -> None:
        self.app.pop_screen()

    # ---------- meta-link clicks ---------- #

    def _open_remote_repository(self) -> None:
        self.app.open_url(self._deck.url)
        self.app.notify(self._deck.url, title="Opened Link")

    def _open_local_folder(self) -> None:
        if reveal_in_file_manager(self._deck.local_path):
            self.app.notify(format_path(self._deck.local_path), title="Opened Folder")
        else:
            self.app.notify(
                f"Couldn't open {self._deck.local_path}.", severity="warning"
            )

    # ---------- worker dispatch ---------- #

    def _start_download(self, *, initial: bool) -> None:
        self._busy = True
        self._current_op = "download" if initial else "update"
        self._chain_build = True
        log = self.query_one(LogPanel)
        log.clear()
        log.set_status(
            "Downloading…" if initial else "Downloading latest version…"
        )
        log.set_progress(0, phase="Connecting")
        self._hide_build_result()
        self._set_action_buttons_enabled(False)
        self.app.notify(
            "Downloading the deck…" if initial else "Downloading the latest version…",
            title="Started",
        )

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

    def _start_check_updates(self) -> None:
        # Background, informational. Don't touch _busy / action-button enabled
        # state — the user should be able to keep clicking buttons while the
        # fetch happens, and disabling them visibly flashes the buttons grey
        # for a moment after the screen mounts.
        panel = self.query_one(UpdatesPanel)
        panel.set_status("Checking for updates…")
        self.run_worker(
            self._do_check_updates,
            thread=True,
            exclusive=True,
            group="deck-actions",
            name="check-updates",
        )

    def _do_check_updates(self) -> CheckUpdatesResult:
        return check_for_updates(self._deck, on_log=self._on_log)

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

    def _start_chained_build(self) -> None:
        """Auto-build the .apkg after a successful download/update."""
        self._busy = True
        self._current_op = "build"
        log = self.query_one(LogPanel)
        log.set_status("Preparing Anki file…")
        self._set_action_buttons_enabled(False)
        self.app.notify("Preparing the Anki file…", title="Building")
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
        # Background check runs without touching _busy / button state — route
        # it past the standard "deck action completed" bookkeeping.
        if event.worker.name == "check-updates":
            if event.state == WorkerState.SUCCESS:
                self._on_worker_success("check", event.worker.result)
            else:
                self._on_worker_error("check", event.worker.error)
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
            if result is not None and result.error is not None:
                self._chain_build = False
                self._handle_download_failed(result.error)
                return
            self._deck.status = DeckStatus.UP_TO_DATE
            self.app.config.save()
            log.set_status("Download complete.")
            self.app.notify("Deck downloaded.", title="Done")
            if self._chain_build:
                self._chain_build = False
                self._start_chained_build()
                return
        elif op == "update":
            if result is not None and result.error is not None:
                self._chain_build = False
                self._handle_update_failed(result.error)
                return
            self._deck.status = DeckStatus.UP_TO_DATE
            self._deck.updates_available = 0
            self.app.config.save()
            no_changes = bool(result and result.no_changes)
            log.set_status(
                "Already up to date." if no_changes else "Updates downloaded."
            )
            self.app.notify(
                "Already up to date." if no_changes else "Latest version downloaded.",
                title="Done",
            )
            if self._chain_build:
                self._chain_build = False
                if no_changes and self._deck.last_built_commit == self._deck.last_pulled_commit:
                    # No new changes AND we already built this commit — skip rebuild.
                    apkg = self._deck.last_built_apkg
                    if apkg is not None:
                        self._show_build_result(apkg)
                else:
                    self._start_chained_build()
                    return
        elif op == "build":
            self.app.config.save()
            log.set_status("Anki file is ready.")
            apkg = self._deck.last_built_apkg
            if apkg is not None:
                self._show_build_result(apkg)
                self.app.notify(str(apkg), title="Anki file ready")
            # Populate the Git history panel — for a fresh deck the panel
            # would still be on its initial "Checking…" placeholder otherwise,
            # since on_mount started a download instead of a check.
            self._start_check_updates()
        elif op == "check" and isinstance(result, CheckUpdatesResult):
            self._on_check_updates_done(result)
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
            self._handle_download_failed(err)
            return

        if op == "update" and isinstance(err, GitError):
            self._handle_update_failed(err)
            return

        if op == "check":
            # Background fetch — surface in the panel, not as a modal.
            panel = self.query_one(UpdatesPanel)
            panel.set_status(f"Couldn't check for updates: {err}" if err else "Couldn't check for updates.")
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

    def _handle_download_failed(self, err: GitError) -> None:
        log = self.query_one(LogPanel)
        log.set_status("Download failed.")
        # Roll back the deck entry — partial state confuses the dashboard.
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

    def _handle_update_failed(self, err: GitError) -> None:
        self.query_one(LogPanel).set_status("Couldn't update the deck.")
        self.app.push_screen(
            ErrorModal(title="Couldn't update the deck", body=str(err))
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

    def _on_check_updates_done(self, result: CheckUpdatesResult) -> None:
        panel = self.query_one(UpdatesPanel)
        if result.error is not None:
            panel.set_status(f"Couldn't check for updates: {result.error}")
            return
        panel.set_commits(result.commits)
        new_count = sum(1 for c in result.commits if c.is_new)
        local = (self._deck.last_pulled_commit or "")[:7]
        if new_count and local:
            panel.set_status(
                f"{new_count} new commit(s) available — local at {local}."
            )
            self._deck.status = DeckStatus.UPDATES_AVAILABLE
            self._deck.updates_available = new_count
        elif local:
            panel.set_status(f"Up to date (local at {local}).")
            self._deck.status = DeckStatus.UP_TO_DATE
            self._deck.updates_available = 0
        else:
            panel.set_status(f"Showing {len(result.commits)} recent commit(s).")
        self._refresh_button_variants()

    def _scroll_to_download_card(self) -> None:
        try:
            self.query_one("#download-card").scroll_visible(animate=False, top=True)
        except NoMatches:
            self.log.debug("#download-card not in DOM during scroll")

    def _show_build_result(self, apkg: Path, *, scroll: bool = True) -> None:
        """Reveal the apkg meta-row link + Import-to-Anki button.

        ``scroll=True`` brings the download card into view (after a fresh build);
        callers seeding the result from disk on mount should pass ``False`` so
        the user starts at the top of the screen.
        """
        self._apkg_path = apkg
        try:
            self.query_one("#apkg-link", _MetaLink).update(str(apkg))
            self.add_class("has-build")
            if scroll:
                self.query_one("#download-card").scroll_visible(animate=False)
            self._refresh_button_variants()
        except NoMatches:
            self.log.debug("build-result UI not in DOM (#apkg-link / #download-card)")

    def _hide_build_result(self) -> None:
        try:
            self.remove_class("has-build")
            self._refresh_button_variants()
        except NoMatches:
            self.log.debug("hide-build-result: query refs not in DOM")

    def _refresh_button_variants(self) -> None:
        """Highlight the action that makes sense for the current deck state.

        - NOT_DOWNLOADED: download is primary (only action).
        - UPDATES_AVAILABLE: download is primary, import is the secondary path.
        - UP_TO_DATE: import is primary (re-import locally), download is muted.
        """
        try:
            download = self.query_one("#download", Button)
            import_btn = self.query_one("#open-in-anki", Button)
        except NoMatches:
            self.log.debug("button-variant refs not in DOM (#download / #open-in-anki)")
            return
        status = self._deck.status
        if status is DeckStatus.UPDATES_AVAILABLE or status is DeckStatus.NOT_DOWNLOADED:
            download.variant = "primary"
            import_btn.variant = "default"
        else:
            download.variant = "default"
            import_btn.variant = "primary"

    def _reveal_apkg(self) -> None:
        if self._apkg_path is None:
            return
        if reveal_in_file_manager(self._apkg_path):
            self.app.notify(format_path(self._apkg_path), title="Opened Folder")
        else:
            self.app.notify(
                f"Couldn't open {self._apkg_path}.", severity="warning"
            )

    def _open_in_anki(self) -> None:
        if self._apkg_path is None:
            return
        if not open_with_default_app(self._apkg_path):
            self.app.notify(
                f"Couldn't open {self._apkg_path.name}.", severity="warning"
            )

    # ---------- remove flow ---------- #

    def _start_remove_deck(self) -> None:
        def _on_choice(result: RemoveDeckResult | None) -> None:
            if result is None:
                return
            self._finalize_remove_deck()

        self.app.push_screen(
            RemoveDeckModal(
                nickname=self._deck.nickname, local_path=self._deck.local_path
            ),
            _on_choice,
        )

    def _finalize_remove_deck(self) -> None:
        deck = self._deck
        if deck in self.app.app_state.decks:
            self.app.app_state.decks.remove(deck)
        if deck in self.app.config.decks:
            self.app.config.decks.remove(deck)
        self.app.config.save()

        outcome = delete_deck_files(deck.local_path)
        if outcome == "deleted":
            self.app.notify(
                f'"{deck.nickname}" removed and deleted from disk.', title="Removed"
            )
        elif outcome == "skipped-unsafe":
            self.app.notify(
                f'"{deck.nickname}" removed from the list. The files at '
                f'{deck.local_path} weren\'t deleted because the path looked '
                "unsafe to remove.",
                title="Files kept",
                severity="warning",
            )
        elif outcome == "missing":
            self.app.notify(
                f'"{deck.nickname}" removed. The files at {deck.local_path} '
                "were already gone.",
                title="Removed",
            )
        else:  # "error"
            self.app.notify(
                f'"{deck.nickname}" removed from the list, but we couldn\'t '
                f'delete the files at {deck.local_path}.',
                title="Couldn't delete files",
                severity="warning",
            )

        # Return to the dashboard — this deck no longer exists.
        self.app.pop_screen()

    # ---------- UI mutation helpers ---------- #

    def _set_action_buttons_enabled(self, enabled: bool) -> None:
        for btn_id in ("download", "filtered", "rebuild-filtered"):
            try:
                btn = self.query_one(f"#{btn_id}", Button)
            except NoMatches:
                self.log.debug(f"#{btn_id} not in DOM during enable/disable")
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
        except NoMatches:
            self.log.debug("status-line refs not in DOM during refresh")
        self._refresh_button_variants()
