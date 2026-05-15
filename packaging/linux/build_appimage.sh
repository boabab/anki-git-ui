#!/bin/bash
# Build a Linux AppImage around the PyInstaller binary.
#
# Run AFTER `pyinstaller pyinstaller.spec`. Requires `appimagetool` on PATH;
# the GitHub Actions release workflow downloads it before invoking this.
# Output: packaging/dist/AnkiGitUI-x86_64.AppImage

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PACKAGING="$PROJECT_ROOT/packaging"
DIST="$PACKAGING/dist"

BIN="$DIST/anki-git-ui-bin"

if [ ! -x "$BIN" ]; then
    echo "Build the PyInstaller binary first:" >&2
    echo "  cd packaging && pyinstaller pyinstaller.spec" >&2
    exit 1
fi

if ! command -v appimagetool >/dev/null 2>&1; then
    echo "appimagetool is required but not on PATH." >&2
    echo "Download it from https://github.com/AppImage/AppImageKit/releases" >&2
    exit 1
fi

APPDIR="$DIST/AnkiGitUI.AppDir"
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin"

# Bundled binary
cp "$BIN" "$APPDIR/usr/bin/anki-git-ui"
chmod +x "$APPDIR/usr/bin/anki-git-ui"

# Desktop entry
cp "$PACKAGING/linux/AnkiGitUI.desktop" "$APPDIR/anki-git-ui.desktop"

# Icon — required by appimagetool. Use a 1x1 placeholder if no PNG provided
# so the build still works locally without artwork.
if [ -f "$PACKAGING/icons/icon.png" ]; then
    cp "$PACKAGING/icons/icon.png" "$APPDIR/anki-git-ui.png"
else
    # 1x1 transparent PNG as a placeholder
    python3 -c "import base64,sys; sys.stdout.buffer.write(base64.b64decode(b'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkAAIAAAoAAv/lxKUAAAAASUVORK5CYII='))" \
        > "$APPDIR/anki-git-ui.png"
fi

# AppRun launcher — opens a terminal so the user gets a TTY.
cat > "$APPDIR/AppRun" <<'EOF'
#!/bin/bash
HERE="$(cd "$(dirname "$0")" && pwd)"
BIN="$HERE/usr/bin/anki-git-ui"
if [ -t 0 ]; then
    exec "$BIN" "$@"
fi
# No TTY (double-click from file manager). Try to launch in the user's
# preferred terminal emulator. Fall back to xterm if nothing else is found.
for term in x-terminal-emulator gnome-terminal konsole xfce4-terminal alacritty kitty foot xterm; do
    if command -v "$term" >/dev/null 2>&1; then
        exec "$term" -e "$BIN" "$@"
    fi
done
echo "Couldn't find a terminal emulator to launch Anki Deck Sync in." >&2
echo "Run from a terminal manually: $BIN" >&2
exit 1
EOF
chmod +x "$APPDIR/AppRun"

OUT="$DIST/AnkiGitUI-x86_64.AppImage"
# --appimage-extract-and-run lets appimagetool (itself an AppImage) work
# without libfuse2 installed. Ubuntu 24.04 runners no longer ship FUSE 2.
( cd "$DIST" && ARCH=x86_64 appimagetool --appimage-extract-and-run "$APPDIR" "$OUT" )
echo "Built $OUT"
