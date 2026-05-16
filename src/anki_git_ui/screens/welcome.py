"""Welcome screen — first-run wizard."""

from __future__ import annotations

import sys

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Static

from ..domain.anki_interop import detect_profiles
from ..domain.git_ops import detect_git
from ..domain.models import WelcomeChecks


def run_checks() -> WelcomeChecks:
    """Run the three first-run checks and return their combined status."""

    git = detect_git()
    base, profiles = detect_profiles()
    return WelcomeChecks(
        python_ok=sys.version_info >= (3, 11),
        python_version=sys.version.split()[0],
        anki_found=base.is_dir(),
        anki_profiles=profiles,
        git_ok=git.found,
        git_version=git.version,
    )


class WelcomeScreen(Screen):
    BINDINGS = [
        Binding("enter", "press_continue", "Continue", show=False),
    ]

    def __init__(self) -> None:
        super().__init__(name="welcome")
        self._checks = run_checks()

    def compose(self) -> ComposeResult:
        with Vertical(id="welcome-card"):
            yield Static("Welcome to Anki Community Deck Sync", classes="welcome-title")
            yield Static(
                "Subscribe to Anki decks shared on GitHub. We download the deck for you "
                "and prepare a file you can open in Anki.",
                classes="welcome-body",
            )
            yield Static("Before we start, here's what we found on your computer:")
            yield from self._check_rows()
            yield Static("")
            with Horizontal(classes="welcome-buttons"):
                yield Button("Check again", id="recheck")
                yield Button(
                    "Get started",
                    id="continue",
                    variant="primary",
                    disabled=not self._checks.can_continue,
                )

    def _check_rows(self) -> list[Static]:
        c = self._checks
        rows: list[Static] = []
        rows.append(
            Static(
                f"  ✓  Python {c.python_version}",
                classes="check-row check-ok" if c.python_ok else "check-row check-error",
            )
        )
        if c.anki_found:
            joined = ", ".join(c.anki_profiles) if c.anki_profiles else "no profiles yet"
            rows.append(
                Static(f"  ✓  Anki is installed (profile: {joined})", classes="check-row check-ok")
            )
        else:
            rows.append(
                Static(
                    "  !  We couldn't find Anki on your computer. You can still continue, "
                    "but you'll need Anki to import the decks we prepare.",
                    classes="check-row check-warn",
                )
            )
        if c.git_ok:
            rows.append(
                Static(f"  ✓  git is installed ({c.git_version})", classes="check-row check-ok")
            )
        else:
            rows.append(
                Static(
                    "  !  We couldn't find git on your computer — we need it to download decks. "
                    "Please install git and click Check again.",
                    classes="check-row check-error",
                )
            )
        return rows

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "continue":
            self._save_initial_config()
            self.app.switch_screen("dashboard")
        elif event.button.id == "recheck":
            # Re-run checks and refresh the screen by replacing self.
            self.app.notify("Checking again…")
            self.app.switch_screen(WelcomeScreen())

    def action_press_continue(self) -> None:
        if self._checks.can_continue:
            self._save_initial_config()
            self.app.switch_screen("dashboard")

    def _save_initial_config(self) -> None:
        """Persist a default config so we don't show Welcome again next launch."""
        cfg = self.app.config
        # If multiple profiles, leave profile unset and let Settings pick.
        if len(self._checks.anki_profiles) == 1:
            cfg.anki.profile = self._checks.anki_profiles[0]
        cfg.save()
        self.app.app_state.is_first_run = False
