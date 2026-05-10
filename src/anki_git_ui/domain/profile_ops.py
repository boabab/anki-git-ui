"""Wrappers around ``anki_gitify.api`` profile helpers.

Keeping the wrapper thin lets us swap implementations or stub them in tests
without monkey-patching the upstream package.
"""

from __future__ import annotations

from pathlib import Path

from anki_gitify import api


def detect_profiles() -> tuple[Path, list[str]]:
    """Return the Anki base directory and the list of profile names found there."""
    base = api.default_anki_base()
    if not base.is_dir():
        return base, []
    return base, api.list_profiles(base)


def collection_path_for(profile: str | None, override: Path | None) -> Path:
    """Resolve the ``collection.anki2`` path for the given profile or override.

    Raises ``FileNotFoundError`` / ``ValueError`` from ``resolve_profile_paths``
    if the resolution fails — callers should surface those as friendly error
    modals.
    """
    paths = api.resolve_profile_paths(profile=profile, collection_override=override)
    return paths.collection
