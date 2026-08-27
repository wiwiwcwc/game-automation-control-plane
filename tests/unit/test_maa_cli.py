import json
import sys
from pathlib import Path

from game_control_plane.domain.models import Job
from game_control_plane.integrations import maa_cli
from game_control_plane.integrations.maa_cli import (
    MaaCliIntegration,
    discover_maa_cli,
    discover_mumu_cli,
)
from game_control_plane.integrations.registry import default_registry


def make_job(executable: Path, task_name: str = "daily") -> Job:
    return Job(
        id=1,
        game_id=1,
        game_name="Arknights",
        name="Daily",
        runner_type="maa_cli",
        runner_config_version=1,
        runner_config_json=json.dumps(
            {
                "config_version": 1,
                "executable_path": str(executable),
                "task_name": task_name,
            }
        ),
        enabled=True,
        queue_order=1,
        timezone_id="Asia/Shanghai",
        reset_minute=240,
    )


def test_maa_cli_builds_documented_batch_launch_spec(tmp_path: Path):
    executable = tmp_path / "maa-cli.exe"
    executable.write_text("fixture", encoding="utf-8")
    integration = MaaCliIntegration()

    result = integration.validate_config(make_job(executable).runner_config)
    assert result.valid
    spec = integration.build_launch_spec(make_job(executable))

    assert spec.executable == str(executable)
    assert spec.arguments == ("run", "daily", "--batch")
    assert spec.working_directory is None
    assert spec.display_command.endswith('run daily --batch')
    assert spec.handoff_process_names == ()


def test_maa_cli_rejects_missing_executable_and_task(tmp_path: Path):
    result = MaaCliIntegration().validate_config(
        {
            "config_version": 1,
            "executable_path": str(tmp_path / "missing-maa-cli.exe"),
            "task_name": "",
        }
    )

    assert not result.valid
    assert any("not found" in error for error in result.errors)
    assert any("task name is required" in error for error in result.errors)


def test_maa_cli_validates_optional_mumu_auto_start_fields(tmp_path: Path):
    maa = tmp_path / "maa-cli.exe"
    mumu = tmp_path / "mumu-cli.exe"
    maa.touch()
    mumu.touch()
    config = {
        "config_version": 1,
        "executable_path": str(maa),
        "task_name": "daily",
        "auto_start_emulator": True,
        "emulator_type": "mumu",
        "emulator_executable_path": str(mumu),
        "emulator_instance_index": 1,
        "emulator_start_timeout_seconds": 120,
    }

    assert MaaCliIntegration().validate_config(config).valid
    config["emulator_instance_index"] = -1
    config["emulator_start_timeout_seconds"] = 10
    result = MaaCliIntegration().validate_config(config)
    assert not result.valid
    assert any("instance number" in error for error in result.errors)
    assert any("between 30 and 600" in error for error in result.errors)


def test_discovery_prefers_path_then_uses_winget_package(monkeypatch, tmp_path: Path):
    on_path = tmp_path / "on-path" / "maa-cli.exe"
    monkeypatch.setattr(maa_cli.shutil, "which", lambda name: str(on_path))
    assert discover_maa_cli() == str(on_path)

    monkeypatch.setattr(maa_cli.shutil, "which", lambda name: None)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    fallback = (
        tmp_path
        / "Microsoft"
        / "WinGet"
        / "Packages"
        / maa_cli.MAA_CLI_WINGET_PACKAGE_DIR
        / "maa-cli.exe"
    )
    fallback.parent.mkdir(parents=True)
    fallback.write_text("fixture", encoding="utf-8")
    assert discover_maa_cli() == str(fallback)


def test_mumu_discovery_uses_supported_cli(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(maa_cli.shutil, "which", lambda name: None)
    monkeypatch.setenv("ProgramFiles", str(tmp_path))
    mumu = tmp_path / "Netease" / "MuMuPlayerGlobal-12.0" / "nx_main" / "mumu-cli.exe"
    mumu.parent.mkdir(parents=True)
    mumu.touch()
    assert discover_mumu_cli() == str(mumu)


def test_default_registry_registers_maa_cli():
    registry = default_registry()
    assert registry.get("maa_cli").display_name == "MAA"
    assert registry.types() == ("custom_cli", "maa_cli", "maa_punish", "ok_ww")
