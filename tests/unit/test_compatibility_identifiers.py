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
    assert "install_inno_setup.ps1" in workflow
    assert "build_installer.ps1" in workflow
    assert "installer_smoke_test.ps1" in workflow
    assert "dist/Hsiesta-*-Setup.exe" in workflow
    assert "dist/Hsiesta-*-Setup.exe.sha256" in workflow


def test_hsiesta_installer_preserves_legacy_payload_and_user_data_contract():
    installer = (PROJECT_ROOT / "packaging" / "hsiesta.iss").read_text(
        encoding="utf-8"
    )
    build_script = (PROJECT_ROOT / "packaging" / "build_installer.ps1").read_text(
        encoding="utf-8"
    )
    inno_bootstrap = (
        PROJECT_ROOT / "packaging" / "install_inno_setup.ps1"
    ).read_text(encoding="utf-8")
    smoke_script = (
        PROJECT_ROOT / "packaging" / "installer_smoke_test.ps1"
    ).read_text(encoding="utf-8")

    assert "AppId={{57c41fc3-082e-4bf2-98ed-c6ac900d7211}" in installer
    assert '#define HsiestaAppName "休汐 Hsiesta"' in installer
    assert r"DefaultDirName={localappdata}\Programs\Hsiesta" in installer
    assert "PrivilegesRequired=lowest" in installer
    assert "DisableProgramGroupPage=no" in installer
    assert r'Source: "..\dist\GameAutomationControlPlane\*"' in installer
    assert 'Hsiesta-{#AppVersion}-Setup' in installer
    assert "GameAutomationControlPlane.exe" in installer
    assert not any(
        line.strip() == "[UninstallDelete]" for line in installer.splitlines()
    )

    assert '"/DAppVersion=$version"' in build_script
    assert "OutputDirectory" in build_script
    assert "('/O' + $dist)" in build_script
    assert 'Hsiesta-$version-Setup.exe' in build_script
    assert 'ProductVersion' in build_script
    assert '"build", "dist", "tests", "codex-runtimes"' in build_script

    assert '$installerName = "innosetup-$innoVersion-x64.exe"' in inno_bootstrap
    assert "0362a383ed217d4c4239b5933866dd96d3eb2102737da92f80f6057a4b40df2f" in inno_bootstrap
    assert '"Pyrsys B.V."' in inno_bootstrap
    assert '"/VERYSILENT"' in inno_bootstrap

    assert "SkipPackagedSmoke" in smoke_script
    assert '"Hsiesta Smoke "' in smoke_script
    assert "'/GROUP=\"' + $groupName + '\"'" in smoke_script
    assert "HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall" in smoke_script
    assert "installer-smoke-sentinel.txt" in smoke_script
    assert "Data sentinel survived" in smoke_script
