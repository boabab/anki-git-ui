# PyInstaller spec for anki-git-ui — single dynamic spec, console mode.
#
# Build (M1: local feasibility):
#   .venv/bin/pyinstaller packaging/pyinstaller.spec
#
# Output: dist/anki-git-ui-bin (macOS/Linux) or dist/anki-git-ui-bin.exe.
# On macOS, packaging/macos/build_app.sh wraps this binary in a .app bundle
# (M8). On Linux, packaging/linux/build_appimage.sh wraps it as an AppImage.

# ruff: noqa
from __future__ import annotations

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

# `anki` ships exactly one native extension (anki/_rsbridge.so) plus a tree of
# pure-Python protobuf modules and a vendored stringcase. collect_all picks up
# binaries + datas + submodules + dynamic imports under one call.
anki_datas, anki_binaries, anki_hiddenimports = collect_all("anki")

# `genanki` ships SQL schema and template files; we need its data, not its
# binaries (it has none).
genanki_datas, _, genanki_hiddenimports = collect_all("genanki")

datas = anki_datas + genanki_datas
binaries = anki_binaries
hiddenimports = anki_hiddenimports + genanki_hiddenimports + [
    # anki-gitify's lazy imports
    "anki_gitify.api",
    "anki_gitify.cli",
    "anki_gitify.collection_io",
    "anki_gitify.export.exporter",
    "anki_gitify.importer.importer",
    "anki_gitify.importer.apply_filtered",
    "anki_gitify.importer.loader",
    "anki_gitify.importer.verify",
    "anki_gitify.profile",
    # textual lazy widgets
    "textual.widgets",
]

block_cipher = None

a = Analysis(
    ["../src/anki_git_ui/__main__.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=["runtime_hooks/_anki_runtime_hook.py"],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="anki-git-ui-bin",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
