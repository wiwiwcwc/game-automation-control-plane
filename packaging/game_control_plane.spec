"""Windows onedir build definition for Game Automation Control Plane."""

from pathlib import Path


PROJECT_ROOT = Path(SPECPATH).resolve().parent
SRC_ROOT = PROJECT_ROOT / "src"
MIGRATIONS = SRC_ROOT / "game_control_plane" / "persistence" / "migrations"
ASSETS = SRC_ROOT / "game_control_plane" / "assets"
APP_ICON = ASSETS / "app_icon.ico"
THIRD_PARTY_NOTICE = PROJECT_ROOT / "THIRD_PARTY_NOTICES.md"
PROJECT_LICENSE = PROJECT_ROOT / "LICENSE"
LICENSES = PROJECT_ROOT / "licenses"
APP_NAME = "GameAutomationControlPlane"


a = Analysis(
    [str(PROJECT_ROOT / "packaging" / "entrypoint.py")],
    pathex=[str(SRC_ROOT)],
    binaries=[],
    datas=[
        (str(MIGRATIONS), "game_control_plane/persistence/migrations"),
        (str(ASSETS), "game_control_plane/assets"),
        (str(THIRD_PARTY_NOTICE), "."),
        (str(PROJECT_LICENSE), "."),
        (str(LICENSES), "licenses"),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "tests"],
    noarchive=False,
    optimize=0,
)
# Codex desktop exposes document/media runtimes on PATH. They are build-tool
# dependencies, not application dependencies, and can shadow Qt's own ICU
# libraries if PyInstaller collects them into the package root.
a.binaries = [
    entry
    for entry in a.binaries
    if "codex-runtimes" not in {part.casefold() for part in Path(entry[1]).parts}
]
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(APP_ICON),
    uac_admin=True,
    disable_windowed_traceback=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    a.zipfiles,
    strip=False,
    upx=False,
    name=APP_NAME,
)
