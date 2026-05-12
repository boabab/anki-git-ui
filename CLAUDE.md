# CLAUDE.md

Friendly Textual TUI wrapping [`anki-gitify`](https://github.com/boabab/anki-gitify): subscribe to deck repos on GitHub, build `.apkg` files, import into Anki.

## Commands

```bash
pip install -e ".[dev]"          # dev setup
pytest                           # all tests (incl. Textual snapshots)
pytest --snapshot-update         # accept new snapshots after intentional UI changes
pytest tests/test_<name>.py -k <pattern>   # focused run
ruff check . && ruff format .    # lint + format
python -m anki_git_ui            # run the app
ANKI_GIT_UI_SMOKE=1 anki-git-ui  # non-interactive smoke (for packaging checks)
```

## Layout

Source under [src/anki_git_ui/](src/anki_git_ui/):

- `app.py` — `AnkiGitUIApp`, screen registration, global CSS and key bindings
- `config.py` — TOML persistence via `platformdirs` (subscribed decks, settings)
- `state.py` — in-memory `AppState` (current profile, loaded decks, runtime flags)
- `screens/` — Textual screens, one user flow each (`dashboard`, `add_deck`, `deck_detail`, `settings`, `welcome`, `help`, `modals`)
- `workers/` — async background tasks (download, make_apkg, update_deck, check_updates, filtered_decks)
- `widgets/` — reusable Textual widgets (`deck_card`, `log_panel`, `updates_panel`)
- `domain/` — UI-free logic: `models`, `git_ops`, `deck_ops`, `apkg_paths`, `profile_ops`, `theme`, `text_utils`

Tests in [tests/](tests/), snapshots in `tests/__snapshots__/`.

## Conventions

- **Layering:** screens own UI and orchestration; workers own async I/O; domain stays UI-free and pure (easy to unit-test).
- **Persistence vs session:** anything that should survive a restart lives in `config.py`; ephemeral runtime state lives in `state.py`.
- **Snapshot tests:** changing UI rendering breaks snapshots. Run `pytest --snapshot-update` only when the visual change is intentional; review the diff in `snapshot_report.html`.
- **Anki interop:** the local Anki app must be closed during `.apkg` import. Worker code surfaces lock errors gracefully — preserve that.
- **Custom Button CSS in `app.py`:** the no-border style is deliberate; see the comment block there before changing.

## Gotchas

- **PyInstaller bundling:** native extensions (`anki/_rsbridge.so`) and relative imports have specific requirements — read [docs/PACKAGING.md](docs/PACKAGING.md) before touching the packaging story.
- **Cross-platform release QA:** [docs/RELEASE-VERIFICATION.md](docs/RELEASE-VERIFICATION.md) lists the manual checks across macOS arm64/x86, Linux, Windows.
- **`anki-gitify` dependency:** `pyproject.toml` has a uv path-source for local dev (`../anki-gitify`); pip falls back to PyPI. Don't remove either without checking the other still works.

## Doc-sync rule

If you change module structure or major data flow, update [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). If you change dev commands or repo conventions, update this file.
