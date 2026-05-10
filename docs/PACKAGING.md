# Packaging notes

This file records the M1 packaging-feasibility decision and any per-OS
gotchas worth remembering when M8 (full release pipeline) lands.

## M1 decision: stay on `--onefile`

Status as of 2026-05-10:

| OS / arch | `--onefile` works? | Verified by |
|---|---|---|
| macOS arm64 | **Yes** | Local build on M1 Mac, `ANKI_GIT_UI_SMOKE=1 anki-git-ui-bin` prints expected output. `_rsbridge.so` resolves under `_MEIPASS` automatically. |
| macOS x86_64 | Untested | Build via GitHub Actions `macos-13` runner before M8. |
| Linux x86_64 | Untested | Build inside `manylinux_2_28` (or `ubuntu-latest`) before M8. |
| Windows x86_64 | Untested | Build via GitHub Actions `windows-latest` before M8. |

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
  matching the build host. Universal2 is possible (`target_arch=universal2`
  in the spec) but the `anki` wheel ships separate arm64 and x86_64
  binaries, so the easier path is two CI matrix entries — `macos-13` for
  Intel and `macos-14` (or newer) for Apple Silicon.
* **macOS Gatekeeper:** ad-hoc-signed `.app` bundles require right-click →
  Open on first launch. Notarization (which would bypass that) needs an
  Apple Developer ID and is M8+ scope.
