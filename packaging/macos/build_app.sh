#!/bin/bash
# Build a macOS .app bundle around the PyInstaller binary.
#
# Run AFTER `pyinstaller pyinstaller.spec` has produced packaging/dist/anki-git-ui-bin.
# Output: packaging/dist/AnkiGitUI.app

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PACKAGING="$PROJECT_ROOT/packaging"
DIST="$PACKAGING/dist"

BIN="$DIST/anki-git-ui-bin"
APP="$DIST/AnkiGitUI.app"
VERSION="${1:-0.1.0}"

if [ ! -x "$BIN" ]; then
    echo "Build the PyInstaller binary first:" >&2
    echo "  cd packaging && pyinstaller pyinstaller.spec" >&2
    exit 1
fi

rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

# Bundled binary
cp "$BIN" "$APP/Contents/MacOS/anki-git-ui-bin"

# CFBundleExecutable shim
cp "$PACKAGING/macos/AnkiGitUI.command" "$APP/Contents/MacOS/AnkiGitUI"
chmod +x "$APP/Contents/MacOS/AnkiGitUI"

# Info.plist with version substituted
sed "s/__VERSION__/$VERSION/g" "$PACKAGING/macos/Info.plist.template" \
    > "$APP/Contents/Info.plist"

# Icon (optional — silently skip if not present)
if [ -f "$PACKAGING/icons/icon.icns" ]; then
    cp "$PACKAGING/icons/icon.icns" "$APP/Contents/Resources/icon.icns"
fi

# Ad-hoc codesign so Gatekeeper allows local execution.
# (Without an Apple Developer ID, first launch still requires right-click → Open.)
codesign --force --deep --sign - "$APP"

echo "Built $APP"
echo "Test it with:  open '$APP'"
echo
echo "First-time launch on another Mac without Developer ID needs"
echo "right-click → Open (Gatekeeper). Notarization is out of scope."
