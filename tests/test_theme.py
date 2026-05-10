"""Tests for the theme resolver."""

from __future__ import annotations

import pytest

from anki_git_ui.domain.theme import ANKI_DARK, ANKI_LIGHT, resolve_theme


def test_explicit_light_maps_to_anki_light() -> None:
    assert resolve_theme("light") == ANKI_LIGHT.name


def test_explicit_dark_maps_to_anki_dark() -> None:
    assert resolve_theme("dark") == ANKI_DARK.name


def test_system_follows_dark_detection_when_dark(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("anki_git_ui.domain.theme.darkdetect.theme", lambda: "Dark")
    assert resolve_theme("system") == ANKI_DARK.name


def test_system_follows_dark_detection_when_light(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("anki_git_ui.domain.theme.darkdetect.theme", lambda: "Light")
    assert resolve_theme("system") == ANKI_LIGHT.name


def test_system_falls_back_to_dark_when_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    """Some Linux setups (no GNOME, no env hints) return None."""
    monkeypatch.setattr("anki_git_ui.domain.theme.darkdetect.theme", lambda: None)
    assert resolve_theme("system") == ANKI_DARK.name


def test_unknown_pref_falls_through_to_system(monkeypatch: pytest.MonkeyPatch) -> None:
    """An unexpected value (e.g. from a hand-edited config) shouldn't crash."""
    monkeypatch.setattr("anki_git_ui.domain.theme.darkdetect.theme", lambda: "Light")
    assert resolve_theme("greenscreen") == ANKI_LIGHT.name


def test_custom_themes_are_registered_on_mount(make_app) -> None:
    """The app calls App.register_theme for each custom theme."""
    import asyncio

    async def _run() -> None:
        app = make_app()
        async with app.run_test():
            assert ANKI_LIGHT.name in app.available_themes
            assert ANKI_DARK.name in app.available_themes

    asyncio.run(_run())
