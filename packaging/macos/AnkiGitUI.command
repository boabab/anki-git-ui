#!/bin/bash
# CFBundleExecutable shim for the macOS .app bundle.
#
# When the user double-clicks the .app from Finder, macOS invokes this script
# with no controlling TTY. Textual needs a TTY, so we re-exec inside Terminal.app
# via osascript. When invoked from an existing terminal (e.g. by a developer),
# we exec the binary directly so we don't open a redundant Terminal window.

set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
BIN="$DIR/anki-git-ui-bin"

if [ ! -x "$BIN" ]; then
    echo "anki-git-ui-bin not found next to this script ($BIN)" >&2
    exit 1
fi

if [ -t 0 ]; then
    exec "$BIN" "$@"
fi

# Tell Terminal.app to open a new window running our binary, then bring
# Terminal to the front. The escaped quotes are necessary because osascript
# parses its argument as AppleScript source.
osascript \
    -e "tell application \"Terminal\" to do script \"clear; exec '$BIN'\"" \
    -e "tell application \"Terminal\" to activate"
