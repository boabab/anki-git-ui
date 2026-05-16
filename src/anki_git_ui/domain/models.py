"""Plain dataclasses shared across the app — no Textual imports."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path


class DeckStatus(Enum):
    NOT_DOWNLOADED = "not_downloaded"
    UP_TO_DATE = "up_to_date"
    UPDATES_AVAILABLE = "updates_available"
    LOCALLY_MODIFIED = "locally_modified"
    DIVERGED = "diverged"
    UNKNOWN = "unknown"


_FRIENDLY = {
    DeckStatus.NOT_DOWNLOADED: "Not downloaded yet",
    DeckStatus.UP_TO_DATE: "Up to date",
    DeckStatus.UPDATES_AVAILABLE: "{n} updates available",
    DeckStatus.LOCALLY_MODIFIED: "Local changes detected — please re-download",
    DeckStatus.DIVERGED: "Couldn't update — please re-download",
    DeckStatus.UNKNOWN: "Checking…",
}


def status_label(status: DeckStatus, *, count: int = 0) -> str:
    template = _FRIENDLY[status]
    return template.format(n=count) if "{n}" in template else template


@dataclass
class DeckEntry:
    """One tracked deck. Persisted to ``config.toml`` in M3+."""

    nickname: str
    url: str
    local_path: Path
    branch: str = "main"
    last_pulled_commit: str | None = None
    last_pulled_at: datetime | None = None
    last_built_commit: str | None = None
    last_built_apkg: Path | None = None
    last_built_at: datetime | None = None

    # Runtime status (not persisted).
    status: DeckStatus = DeckStatus.UNKNOWN
    updates_available: int = 0


@dataclass
class AnkiProfileChoice:
    """Selected Anki profile — either by name (auto-detected) or explicit path override."""

    profile: str | None = None
    collection_override: Path | None = None


@dataclass
class WelcomeChecks:
    """Result of the three first-run checks. Each entry is one row in the wizard."""

    python_ok: bool
    python_version: str
    anki_found: bool
    anki_profiles: list[str] = field(default_factory=list)
    git_ok: bool = False
    git_version: str | None = None

    @property
    def can_continue(self) -> bool:
        return self.python_ok and self.git_ok
