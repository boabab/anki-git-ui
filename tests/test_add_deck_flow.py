"""Tests for the add-deck wizard and remove-deck flow."""

from __future__ import annotations

import pytest
from textual.widgets import Button, Input

from anki_git_ui.screens.add_deck import AddDeckScreen
from anki_git_ui.screens.dashboard import DashboardScreen
from anki_git_ui.screens.modals import RemoveDeckModal


def _press(app, selector: str) -> None:
    """Press a button by selector — bypasses spatial bounds checks that
    pilot.click() enforces for off-screen widgets."""
    app.screen.query_one(selector, Button).press()


@pytest.mark.asyncio
async def test_dashboard_add_button_pushes_add_deck_screen(make_app) -> None:
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        _press(app, "#add-deck")
        await pilot.pause()
        assert isinstance(app.screen, AddDeckScreen)


@pytest.mark.asyncio
async def test_add_deck_empty_url_does_not_advance(make_app) -> None:
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        _press(app, "#add-deck")
        await pilot.pause()
        _press(app, "#next")
        await pilot.pause()
        assert app.screen._step == 1


@pytest.mark.asyncio
async def test_add_deck_step_1_advances_to_step_2(make_app) -> None:
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        _press(app, "#add-deck")
        await pilot.pause()
        app.screen.query_one("#url-input", Input).value = (
            "https://github.com/example/jlpt-n5-deck"
        )
        _press(app, "#next")
        await pilot.pause()
        assert app.screen._step == 2
        nickname = app.screen.query_one("#nickname-input", Input).value
        assert "Jlpt" in nickname or "jlpt" in nickname.lower()


@pytest.mark.asyncio
async def test_add_deck_back_preserves_url(make_app) -> None:
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        _press(app, "#add-deck")
        await pilot.pause()
        app.screen.query_one("#url-input", Input).value = (
            "https://github.com/example/preserve-me"
        )
        _press(app, "#next")
        await pilot.pause()
        _press(app, "#prev")
        await pilot.pause()
        url_value = app.screen.query_one("#url-input", Input).value
        assert url_value == "https://github.com/example/preserve-me"


@pytest.mark.asyncio
async def test_remove_deck_cancel_keeps_deck(make_app) -> None:
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        starting_count = len(app.app_state.decks)
        # Open the remove modal for the first deck via the DeckCard's button.
        first_card_remove = app.screen.query("DeckCard Button#remove").first(Button)
        first_card_remove.press()
        await pilot.pause()
        assert isinstance(app.screen, RemoveDeckModal)
        # Cancel
        app.screen.query_one("#cancel", Button).press()
        await pilot.pause()
        assert isinstance(app.screen, DashboardScreen)
        assert len(app.app_state.decks) == starting_count


@pytest.mark.asyncio
async def test_remove_deck_confirm_drops_from_list(make_app) -> None:
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        starting_count = len(app.app_state.decks)
        first_card_remove = app.screen.query("DeckCard Button#remove").first(Button)
        first_card_remove.press()
        await pilot.pause()
        # Confirm without checking "delete files".
        app.screen.query_one("#remove", Button).press()
        await pilot.pause()
        assert isinstance(app.screen, DashboardScreen)
        assert len(app.app_state.decks) == starting_count - 1
