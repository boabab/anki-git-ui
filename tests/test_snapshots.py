"""Textual snapshot tests — catch accidental layout regressions cheaply.

Run once to create the SVGs, then re-runs compare. Each snapshot is the
representative state of a screen; if you intentionally change the layout
or copy, regenerate with ``--snapshot-update``.
"""

from __future__ import annotations

import pytest

from anki_git_ui.domain.models import WelcomeChecks


@pytest.fixture(autouse=True)
def stable_theme(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force the dark theme regardless of host OS appearance.

    Snapshots run on the dev machine and CI; without this, a developer on a
    light-mode Mac would generate different SVGs than the CI runner.
    """
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setattr(
        "anki_git_ui.domain.theme.darkdetect.theme", lambda: "Dark"
    )


@pytest.fixture
def stable_welcome_checks(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make Welcome screen checks deterministic regardless of host."""
    monkeypatch.setattr(
        "anki_git_ui.screens.welcome.run_checks",
        lambda: WelcomeChecks(
            python_ok=True,
            python_version="3.13.0",
            anki_found=True,
            anki_profiles=["User 1"],
            git_ok=True,
            git_version="git version 2.46.0",
        ),
    )


def test_dashboard_snapshot(make_app, snap_compare) -> None:
    app = make_app()
    assert snap_compare(app, terminal_size=(120, 40))


def test_welcome_snapshot(make_app, snap_compare, stable_welcome_checks) -> None:
    from anki_git_ui.state import AppState

    # Force the first-run path so Welcome shows.
    app = make_app(state=AppState(decks=[], is_first_run=True))
    assert snap_compare(app, terminal_size=(120, 40))


def test_help_snapshot(make_app, snap_compare) -> None:
    async def kick(pilot) -> None:
        from textual.widgets import Button

        await pilot.pause()
        app = pilot.app
        app.screen.query_one("#help", Button).press()
        await pilot.pause()

    app = make_app()
    assert snap_compare(app, terminal_size=(120, 40), run_before=kick)


def test_settings_snapshot(make_app, snap_compare) -> None:
    async def kick(pilot) -> None:
        from textual.widgets import Button

        await pilot.pause()
        pilot.app.screen.query_one("#settings", Button).press()
        await pilot.pause()

    app = make_app()
    assert snap_compare(app, terminal_size=(120, 40), run_before=kick)


def test_add_deck_step1_snapshot(make_app, snap_compare) -> None:
    async def kick(pilot) -> None:
        from textual.widgets import Button

        await pilot.pause()
        pilot.app.screen.query_one("#add-deck", Button).press()
        await pilot.pause()

    app = make_app()
    assert snap_compare(app, terminal_size=(120, 40), run_before=kick)
