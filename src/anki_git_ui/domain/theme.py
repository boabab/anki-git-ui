"""Custom Textual themes for Anki Deck Sync, plus a stored-pref resolver.

The Settings screen exposes ``system`` / ``light`` / ``dark`` to the user;
this module maps that to a concrete Textual theme name. We register two
custom themes (instead of using ``textual-light`` / ``textual-dark``) so we
can pick a brighter light-mode background and slightly tweak the surface
colors away from Textual's defaults.
"""

from __future__ import annotations

from typing import Literal

import darkdetect
from textual.theme import Theme


ThemePref = Literal["system", "light", "dark"]


# Bright, clean light theme. ``surface`` and ``background`` are nearly white
# (the user asked for "more white" than textual-light), ``panel`` is a faint
# gray so non-primary buttons keep visible against the surface.
ANKI_LIGHT = Theme(
    name="anki-deck-sync-light",
    primary="#1976d2",
    secondary="#5e35b1",
    accent="#ff9800",
    warning="#f57c00",
    error="#d32f2f",
    success="#2e7d32",
    foreground="#1a1a1a",
    background="#ffffff",
    surface="#ffffff",
    panel="#eeeeee",
    boost="#e0e0e0",
    dark=False,
)


ANKI_DARK = Theme(
    name="anki-deck-sync-dark",
    primary="#42a5f5",
    secondary="#9575cd",
    accent="#ffa726",
    warning="#ffb74d",
    error="#ef5350",
    success="#66bb6a",
    foreground="#e6e6e6",
    background="#1e1e1e",
    surface="#252525",
    panel="#333333",
    boost="#3d3d3d",
    dark=True,
)


CUSTOM_THEMES: tuple[Theme, ...] = (ANKI_LIGHT, ANKI_DARK)


def resolve_theme(pref: str) -> str:
    """Return the registered theme name for the user's stored preference.

    Falls back to dark when ``pref`` is ``"system"`` and the OS preference
    is unknown — matches what most users expect from a terminal app.
    """
    if pref == "light":
        return ANKI_LIGHT.name
    if pref == "dark":
        return ANKI_DARK.name
    # system
    detected = darkdetect.theme()  # "Light" | "Dark" | None
    if detected == "Light":
        return ANKI_LIGHT.name
    return ANKI_DARK.name
