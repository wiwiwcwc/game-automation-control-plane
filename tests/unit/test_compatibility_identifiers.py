from __future__ import annotations

from pathlib import Path
import tomllib

from game_control_plane.ui import i18n


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_legacy_qsettings_keys_are_explicit_and_unchanged(monkeypatch):
    calls = []

    class RecordingSettings:
        def __init__(self, *arguments):
            calls.append(arguments)

        def value(self, _key, default, **_kwargs):
            return default

    monkeypatch.setattr(i18n, "QSettings", RecordingSettings)

    i18n.LanguageManager(persist=False)

    assert i18n.LEGACY_QSETTINGS_ORGANIZATION == "GameAutomationControlPlane"
    assert i18n.LEGACY_QSETTINGS_APPLICATION == "GameAutomationControlPlane"
    assert calls == [
        (
            "GameAutomationControlPlane",
            "GameAutomationControlPlane",
        )
    ]


def test_distribution_and_console_script_names_remain_compatible():
    metadata = tomllib.loads(
        (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )

    assert metadata["project"]["name"] == "game-automation-control-plane"
    assert metadata["project"]["scripts"]["game-control-plane"] == (
        "game_control_plane.app:main"
    )


def test_windows_package_output_names_remain_compatible():
    spec = (PROJECT_ROOT / "packaging" / "game_control_plane.spec").read_text(
        encoding="utf-8"
    )
    workflow = (
        PROJECT_ROOT / ".github" / "workflows" / "windows-package.yml"
    ).read_text(encoding="utf-8")

    assert 'APP_NAME = "GameAutomationControlPlane"' in spec
    assert "name=APP_NAME" in spec
    assert r"dist\GameAutomationControlPlane" in workflow
    assert "GameAutomationControlPlane.exe" in workflow
    assert "GameAutomationControlPlane-windows.zip" in workflow
