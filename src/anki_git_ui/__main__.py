"""Entry point: ``python -m anki_git_ui`` and the ``anki-git-ui`` console script."""

from __future__ import annotations

import os
import platform
import sys

from anki_git_ui.app import AnkiGitUIApp


def _smoke() -> int:
    """Non-interactive smoke for the M1 packaging-feasibility check.

    Triggered by ``ANKI_GIT_UI_SMOKE=1``. Imports :mod:`anki_gitify.api`
    eagerly so that any PyInstaller bundling problem with
    ``anki/_rsbridge.so`` surfaces here, before the Textual event loop.
    """
    from anki_gitify import api

    from anki_git_ui.domain.theme import resolve_theme

    base = api.default_anki_base()
    profiles = api.list_profiles(base)
    print("anki-git-ui smoke OK")
    print(f"  python:    {sys.version.split()[0]} on {platform.system()} ({platform.machine()})")
    print(f"  api ver:   {api.API_VERSION}")
    print(f"  anki base: {base} (exists={base.is_dir()})")
    print(f"  profiles:  {profiles}")
    print(f"  os theme:  {resolve_theme('system')}")
    return 0


def main() -> None:
    if os.environ.get("ANKI_GIT_UI_SMOKE") == "1":
        sys.exit(_smoke())
    AnkiGitUIApp().run()


if __name__ == "__main__":
    main()
