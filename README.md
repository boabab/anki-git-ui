# Anki-Git-UI

<p align="center">
  <img src="docs/images/thumbnail.svg" alt="Anki-Git-UI" width="640"/>
</p>

A friendly terminal UI for [`anki-gitify`](https://github.com/boabab/anki-gitify): subscribe to Anki deck repositories on GitHub, prepare them as `.apkg` files, and import them into your local Anki collection.

Built with [Textual](https://textual.textualize.io/) — runs in any modern terminal, mouse and keyboard.

> **Status:** early development (v0.1.0). Expect rough edges.

## Download

Pre-built binaries for the latest release are on the [Releases page](https://github.com/boabab/anki-git-ui/releases/latest). No Python needed — download, unzip, run.

| Platform | File |
|---|---|
| macOS (Apple Silicon) | `AnkiGitUI-macos-arm64.zip` |
| macOS (Intel) | `AnkiGitUI-macos-x86_64.zip` |
| Linux (x86_64) | `AnkiGitUI-linux-x86_64.AppImage` |
| Windows (x86_64) | `AnkiGitUI-windows-x86_64.zip` |

On macOS, the first launch may warn that the app is from an unidentified developer — right-click the app and choose "Open" once, then it remembers. Windows SmartScreen has a similar one-time prompt.

## Install from source

Requires Python 3.11–3.13 and a local Anki installation (Anki must be closed during imports).

```bash
pip install -e .
```

Or, with [uv](https://docs.astral.sh/uv/):

```bash
uv sync
```

## Run

```bash
python -m anki_git_ui
# or, after install:
anki-git-ui
```

On first launch you'll be guided through picking your Anki profile and subscribing to your first deck repository.

## Development

```bash
pip install -e ".[dev]"
pytest                       # full suite, including Textual snapshot tests
pytest --snapshot-update     # accept new snapshots after intentional UI changes
ruff check . && ruff format .
```

See [CLAUDE.md](CLAUDE.md) for the full command list, repo conventions, and known gotchas.

## Docs

- [CLAUDE.md](CLAUDE.md) — agent / contributor context
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — module map and data flow
- [docs/PACKAGING.md](docs/PACKAGING.md) — PyInstaller notes
- [docs/RELEASE-VERIFICATION.md](docs/RELEASE-VERIFICATION.md) — manual QA checklist for releases

## License

[MIT](LICENSE) © 2026 Robin
