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
async def test_add_deck_step_1_advances_to_step_2(
    make_app, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Pressing Next runs verify_gitify_repo in a worker thread; stub it so the
    # test doesn't hit the network or shell out to git.
    monkeypatch.setattr(
        "anki_git_ui.screens.add_deck.verify_gitify_repo", lambda url: None
    )
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        _press(app, "#add-deck")
        await pilot.pause()
        app.screen.query_one(
            "#url-input", Input
        ).value = "https://github.com/example/jlpt-n5-deck"
        _press(app, "#next")
        # Worker runs in a thread, then on success switches the screen.
        await pilot.pause(0.2)
        assert app.screen._step == 2
        nickname = app.screen.query_one("#nickname-input", Input).value
        assert "Jlpt" in nickname or "jlpt" in nickname.lower()


@pytest.mark.asyncio
async def test_add_deck_back_preserves_url(
    make_app, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "anki_git_ui.screens.add_deck.verify_gitify_repo", lambda url: None
    )
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        _press(app, "#add-deck")
        await pilot.pause()
        app.screen.query_one(
            "#url-input", Input
        ).value = "https://github.com/example/preserve-me"
        _press(app, "#next")
        await pilot.pause(0.2)
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
        # Open the deck detail screen, then click Remove there.
        app.screen.query("DeckCard Button#open").first(Button).press()
        await pilot.pause()
        app.screen.query_one("#remove-deck", Button).press()
        await pilot.pause()
        assert isinstance(app.screen, RemoveDeckModal)
        # Cancel
        app.screen.query_one("#cancel", Button).press()
        await pilot.pause()
        # Back on deck detail, deck still in the list.
        assert len(app.app_state.decks) == starting_count


@pytest.mark.asyncio
async def test_remove_deck_confirm_drops_from_list(make_app) -> None:
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        starting_count = len(app.app_state.decks)
        app.screen.query("DeckCard Button#open").first(Button).press()
        await pilot.pause()
        app.screen.query_one("#remove-deck", Button).press()
        await pilot.pause()
        # Confirm without checking "delete files".
        app.screen.query_one("#remove", Button).press()
        await pilot.pause()
        # Detail screen pops; we land back on the dashboard with one fewer deck.
        assert isinstance(app.screen, DashboardScreen)
        assert len(app.app_state.decks) == starting_count - 1


@pytest.mark.asyncio
async def test_dashboard_shows_decks_added_while_away(make_app) -> None:
    """Regression: adding a deck on another screen must show up on the
    dashboard when the user navigates back."""
    from anki_git_ui.domain.models import DeckEntry, DeckStatus
    from anki_git_ui.widgets.deck_card import DeckCard

    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        starting_count = len(app.app_state.decks)

        # Push a different screen — the dashboard goes into the background.
        _press(app, "#help")
        await pilot.pause()

        # Simulate a deck being added on another screen (this is what the
        # add-deck flow does in production via _submit). At this point the
        # dashboard's compose() has already run and won't auto-update.
        new_deck = DeckEntry(
            nickname="Newly Added",
            url="https://github.com/example/newly-added",
            local_path=app.config.default_save_folder / "newly-added",
            status=DeckStatus.NOT_DOWNLOADED,
        )
        app.app_state.decks.append(new_deck)
        app.config.decks.append(new_deck)

        # Pop back to dashboard — on_screen_resume should refresh the cards.
        _press(app, "#back")
        await pilot.pause()
        assert isinstance(app.screen, DashboardScreen)

        cards = list(app.screen.query(DeckCard))
        assert len(cards) == starting_count + 1, (
            f"expected {starting_count + 1} cards, got {len(cards)}"
        )
        # New deck visible by nickname
        nicknames = [card._deck.nickname for card in cards]
        assert "Newly Added" in nicknames
