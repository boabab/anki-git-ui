# Packaging notes

This file records the M1 packaging-feasibility decision and any per-OS
gotchas worth remembering when M8 (full release pipeline) lands.

## M1 decision: stay on `--onefile`

Status as of 2026-05-10:

| OS / arch | `--onefile` works? | Verified by |
|---|---|---|
| macOS arm64 | **Yes** | GitHub Actions `macos-latest` runner; `ANKI_GIT_UI_SMOKE=1` smoke passes; `_rsbridge.so` resolves under `_MEIPASS` automatically. |
| macOS x86_64 | Not shipped | GitHub's free `macos-13` runner pool became unreliable in 2026; Intel users install from source. |
| Linux x86_64 | **Yes** | GitHub Actions `ubuntu-latest`, packaged as AppImage. |
| Windows x86_64 | **Yes** | GitHub Actions `windows-latest`, packaged as `.exe` in a zip. |

**No fallback to `--onedir` is currently needed.** If a future build fails
because `_rsbridge.so` isn't found at runtime, the runtime hook at
`packaging/runtime_hooks/_anki_runtime_hook.py` is the first thing to
suspect: it inserts `_MEIPASS` onto `sys.path` so the implicit relative
import inside `anki._backend` can find the extension. If that fails too,
switching the spec to `--onedir` is the documented escape hatch.

## How to reproduce locally

```bash
# from the project root, with the venv set up
cd packaging
../.venv/bin/pyinstaller --noconfirm pyinstaller.spec
ANKI_GIT_UI_SMOKE=1 ./dist/anki-git-ui-bin
```

The smoke hatch is gated by `ANKI_GIT_UI_SMOKE=1`. Without it, the binary
launches the Textual app interactively (which requires a TTY).

## Gotchas to remember

* **Relative imports in `__main__.py` break under PyInstaller.** The entry
  script is run as the top-level `__main__` module, which has no parent
  package, so `from .app import ...` raises `ImportError`. Always use
  absolute imports in `__main__.py` (`from anki_git_ui.app import ...`).
* **`anki` ships exactly one native extension** (`anki/_rsbridge.so`).
  `collect_all("anki")` in the spec picks it up correctly. No additional
  hooks are needed for the protobuf modules — they are pure Python.
* **`genanki` ships data files** (SQL schema, default templates).
  `collect_all("genanki")` is needed even though it has no native deps.
* **Apple Silicon vs Intel:** PyInstaller produces a single-arch binary
  matching the build host. We currently ship only arm64 because GitHub's
  free `macos-13` runner pool is unreliable in 2026 and Apple stopped
  selling Intel Macs in 2023. If demand returns, two paths exist: re-add
  `macos-13` to the matrix (and accept the queueing risk), or build a
  universal2 binary on arm64 — the `anki` wheel ships separate arm64 and
  x86_64 binaries, so universal2 requires installing both wheels and
  setting `target_arch=universal2` in the spec.
* **macOS Gatekeeper:** ad-hoc-signed `.app` bundles require right-click →
  Open on first launch. Notarization (which would bypass that) needs an
  Apple Developer ID and is M8+ scope.
