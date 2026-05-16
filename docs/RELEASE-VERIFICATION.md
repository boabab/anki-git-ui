# Release verification checklist

After [release.yml](../.github/workflows/release.yml) produces artifacts for a
new tag, run through this checklist on each OS before announcing the release.
Each platform is ~10 minutes.

The `release.yml` workflow runs `pytest` itself before building, so the
artifacts you download are already known to pass tests on the build runner.
This list is for things tests can't check — does it actually launch when
double-clicked, does the TTY come up, does the icon look right.

## macOS (Apple Silicon)

We ship arm64 only. Intel-Mac users install from source — see the
[README](../README.md#install-from-source).

1. Download `AnkiGitUI-macos-arm64.zip`.
2. Unzip in Finder. You should see `AnkiGitUI.app`.
3. Right-click → Open. Gatekeeper warns "from an unidentified developer";
   click Open. (Subsequent launches don't ask.)
4. Terminal.app should pop up showing the welcome screen.
5. Walk through the smoke flow:
   - Click Get started.
   - On the dashboard, click "+ Add a new deck".
   - Paste a small public deck repo URL (the project's example fixture
     works). Click Next, then Add and download.
   - The download should stream into the activity log; final status:
     "Download complete."
   - Click Make Anki file. The success modal should appear with the path.
6. Quit (q). Re-launch from Finder; confirm the deck list is preserved.

If Terminal doesn't open, the `AnkiGitUI` shim isn't being executed — check
`Info.plist` `CFBundleExecutable` matches the script name (`AnkiGitUI`).

## Linux (x86_64)

1. Download `AnkiGitUI-linux-x86_64.AppImage`. Mark executable: `chmod +x`.
2. Optional: install [`AnkiGitUI.desktop`](../packaging/linux/AnkiGitUI.desktop)
   into `~/.local/share/applications/` so the file manager can launch via
   double-click. (Otherwise: run from a terminal.)
3. Double-click. Your default terminal emulator should open running the TUI.
   Tested terminals (any one is enough): GNOME Terminal, Konsole, xfce4-terminal,
   alacritty, kitty, foot. Falls back to xterm.
4. Run the same smoke flow as macOS step 5.
5. Quit, re-launch, confirm persistence.

If no terminal opens, the system has none of the supported emulators —
document this on the Releases page.

## Windows (x86_64)

1. Download `AnkiGitUI-windows-x86_64.zip`. Right-click → Extract All.
2. Double-click `AnkiGitUI.exe`. A `cmd.exe` window opens with the TUI.
3. Same smoke flow.
4. SmartScreen warning may appear — "Run anyway." (We don't currently sign
   Windows builds.)

## Common issues to watch for

- **`_rsbridge.so` resolution failure** would surface as an `ImportError`
  in the activity log on first action. If this happens, the
  `_anki_runtime_hook.py` runtime hook isn't being applied — check
  `pyinstaller.spec` `runtime_hooks=[...]` is still present.
- **Frozen UI on download** — git is missing on the target machine. The
  Welcome screen should have already flagged this; if it didn't, the
  `detect_git()` path is broken on that OS.
- **Anki collection lock errors that don't show the friendly modal** —
  upstream `anki-gitify` changed the locked-error message wording. Update
  `_is_locked_error()` in `domain/anki_interop.py` to match.
