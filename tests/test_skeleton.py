"""M2 skeleton tests: confirm screens render and basic navigation works."""

from __future__ import annotations

import pytest

from anki_git_ui.screens.dashboard import DashboardScreen
from anki_git_ui.screens.help import HelpScreen
from anki_git_ui.screens.settings import SettingsScreen


@pytest.mark.asyncio
async def test_app_starts_at_dashboard_when_state_is_not_first_run(make_app) -> None:
    app = make_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        assert isinstance(app.screen, DashboardScreen), (
            f"Expected dashboard but got {type(app.screen).__name__}"
        )


@pytest.mark.asyncio
async def test_help_screen_pushes_and_pops(make_app) -> None:
    app = make_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.click("#help")
        await pilot.pause()
        assert isinstance(app.screen, HelpScreen)
        await pilot.click("#back")
        await pilot.pause()
        assert isinstance(app.screen, DashboardScreen)


@pytest.mark.asyncio
async def test_dashboard_renders_three_mock_decks(make_app) -> None:
    app = make_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        from anki_git_ui.widgets.deck_card import DeckCard

        cards = list(app.screen.query(DeckCard))
        assert len(cards) == 3, f"expected 3 mock decks, got {len(cards)}"


@pytest.mark.asyncio
async def test_settings_screen_pushes_and_pops(make_app) -> None:
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.click("#settings")
        await pilot.pause()
        assert isinstance(app.screen, SettingsScreen)
        # Escape is bound to the cancel action — works regardless of scroll
        # position, unlike clicking the (possibly off-screen) cancel button.
        await pilot.press("escape")
        await pilot.pause()
        assert isinstance(app.screen, DashboardScreen)
