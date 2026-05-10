"""PyInstaller runtime hook: ensure the bundled ``anki/_rsbridge.so`` resolves.

PyInstaller normally handles native extensions correctly under ``_MEIPASS``,
but the ``anki`` package's ``_rsbridge`` is loaded via implicit relative
import from inside ``anki._backend``. If the bundle layout puts the module
somewhere unexpected, this hook makes sure ``anki/`` is on ``sys.path`` so
the import resolves before any user code runs.
"""

from __future__ import annotations

import os
import sys


def _ensure_anki_on_path() -> None:
    meipass = getattr(sys, "_MEIPASS", None)
    if not meipass:
        return
    candidate = os.path.join(meipass, "anki")
    if os.path.isdir(candidate) and meipass not in sys.path:
        sys.path.insert(0, meipass)


_ensure_anki_on_path()
