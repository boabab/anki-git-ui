"""Config persistence — TOML at ``platformdirs.user_config_dir("anki-git-ui")``.

The on-disk schema includes ``config_version`` so we can do forward
migrations as fields are added or renamed. Each ``[[decks]]`` entry tracks
``branch`` plus ``last_pulled_commit`` and ``last_built_commit`` so the
dashboard can distinguish "up to date — already prepared" from "up to date
— but not yet prepared" without re-running git.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import platformdirs
import tomlkit
from tomlkit import TOMLDocument

from .domain.models import AnkiProfileChoice, DeckEntry, DeckStatus


CURRENT_VERSION = 1


def config_path() -> Path:
    return Path(platformdirs.user_config_dir("anki-git-ui", "anki-git-ui")) / "config.toml"


def config_exists() -> bool:
    return config_path().is_file()


@dataclass
class Config:
    config_version: int = CURRENT_VERSION
    default_save_folder: Path = field(default_factory=lambda: Path.home() / "AnkiDecks")
    theme: str = "system"
    anki: AnkiProfileChoice = field(default_factory=AnkiProfileChoice)
    decks: list[DeckEntry] = field(default_factory=list)

    @classmethod
    def load(cls, path: Path | None = None) -> "Config":
        path = path or config_path()
        if not path.is_file():
            return cls()
        text = path.read_text(encoding="utf-8")
        data: dict[str, Any] = tomlkit.parse(text).unwrap()
        data = _migrate(data)
        return _from_dict(data)

    def save(self, path: Path | None = None) -> None:
        path = path or config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        doc = _to_doc(self)
        path.write_text(tomlkit.dumps(doc), encoding="utf-8")


def _migrate(data: dict[str, Any]) -> dict[str, Any]:
    version = int(data.get("config_version", 0))
    if version > CURRENT_VERSION:
        raise ValueError(
            f"This config was written by a newer version of Anki Community Deck Sync "
            f"(config_version={version}, this app understands {CURRENT_VERSION}). "
            "Please update the app."
        )
    # No migrations to run yet — this is the first version. Future bumps add
    # an `if version < N: data = _migrate_N_minus_1_to_N(data)` ladder here.
    data["config_version"] = CURRENT_VERSION
    return data


def _from_dict(data: dict[str, Any]) -> Config:
    anki_section = data.get("anki", {}) or {}
    anki = AnkiProfileChoice(
        profile=anki_section.get("profile") or None,
        collection_override=_path_or_none(anki_section.get("collection_override")),
    )

    decks_data = data.get("decks", []) or []
    decks = [_deck_from_dict(d) for d in decks_data]

    save = data.get("default_save_folder", "")
    return Config(
        config_version=int(data.get("config_version", CURRENT_VERSION)),
        default_save_folder=Path(save).expanduser() if save else Path.home() / "AnkiDecks",
        theme=str(data.get("theme", "system")),
        anki=anki,
        decks=decks,
    )


def _deck_from_dict(d: dict[str, Any]) -> DeckEntry:
    last_pulled_commit = d.get("last_pulled_commit") or None
    # We don't auto-check against the remote on launch (would block startup on
    # every restart). If we've pulled the deck before, assume it's still UP_TO_DATE
    # until the user explicitly hits "Check for updates".
    status = DeckStatus.UP_TO_DATE if last_pulled_commit else DeckStatus.NOT_DOWNLOADED
    return DeckEntry(
        nickname=d["nickname"],
        url=d["url"],
        local_path=Path(d["local_path"]).expanduser(),
        branch=d.get("branch") or "main",
        last_pulled_commit=last_pulled_commit,
        last_pulled_at=_dt_or_none(d.get("last_pulled_at")),
        last_built_commit=d.get("last_built_commit") or None,
        last_built_apkg=_path_or_none(d.get("last_built_apkg")),
        last_built_at=_dt_or_none(d.get("last_built_at")),
        status=status,
    )


def _to_doc(cfg: Config) -> TOMLDocument:
    doc = tomlkit.document()
    doc.add("config_version", cfg.config_version)
    doc.add("default_save_folder", _stringify_path(cfg.default_save_folder))
    doc.add("theme", cfg.theme)

    anki_table = tomlkit.table()
    anki_table.add("profile", cfg.anki.profile or "")
    anki_table.add(
        "collection_override",
        _stringify_path(cfg.anki.collection_override) if cfg.anki.collection_override else "",
    )
    doc.add("anki", anki_table)

    decks_array = tomlkit.aot()
    for deck in cfg.decks:
        decks_array.append(_deck_to_table(deck))
    doc.add("decks", decks_array)
    return doc


def _deck_to_table(deck: DeckEntry):
    t = tomlkit.table()
    t.add("nickname", deck.nickname)
    t.add("url", deck.url)
    t.add("local_path", _stringify_path(deck.local_path))
    t.add("branch", deck.branch)
    t.add("last_pulled_commit", deck.last_pulled_commit or "")
    t.add("last_pulled_at", _stringify_dt(deck.last_pulled_at))
    t.add("last_built_commit", deck.last_built_commit or "")
    t.add(
        "last_built_apkg",
        _stringify_path(deck.last_built_apkg) if deck.last_built_apkg else "",
    )
    t.add("last_built_at", _stringify_dt(deck.last_built_at))
    return t


# ---------- helpers ---------- #


def _stringify_path(p: Path) -> str:
    home = Path.home()
    try:
        rel = p.relative_to(home)
        return str(Path("~") / rel)
    except ValueError:
        return str(p)


def _path_or_none(value: Any) -> Path | None:
    if not value:
        return None
    return Path(str(value)).expanduser()


def _stringify_dt(dt: datetime | None) -> str:
    if dt is None:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _dt_or_none(value: Any) -> datetime | None:
    if not value:
        return None
    s = str(value)
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return datetime.fromisoformat(s)
