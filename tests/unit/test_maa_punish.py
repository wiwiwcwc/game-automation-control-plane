from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from game_control_plane.domain.models import Job
from game_control_plane.integrations.maa_punish import (
    INTERNAL_FOS_RUNNER_ARG,
    MaaPunishIntegration,
    discover_fos_configurations,
    find_fos_configuration,
    read_fos_controller,
)
from game_control_plane.integrations.registry import default_registry


def make_fos(tmp_path: Path) -> tuple[Path, str]:
    fos = tmp_path / "MPA" / "FOS.exe"
    fos.parent.mkdir()
    fos.touch()
    config_id = "c_daily"
    config_dir = fos.parent / "config" / "configs"
    config_dir.mkdir(parents=True)
    (config_dir / f"{config_id}.json").write_text(
        json.dumps(
            {
                "name": "每日任务",
                "item_id": config_id,
                "tasks": [
                    {
                        "name": "Controller",
                        "item_id": "Controller",
                        "task_option": {
                            "controller_type": "Android",
                            "Android": {
                                "adb_path": "C:/MuMu/adb.exe",
                                "address": "127.0.0.1:16384",
                                "config": {
                                    "extras": {
                                        "mumu": {
                                            "enable": True,
                                            "index": 0,
                                            "path": "C:/MuMu",
                                        }
                                    }
                                },
                            },
                        },
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return fos, config_id


def make_job(fos: Path, config_id: str) -> Job:
    return Job(
        id=1,
        game_id=1,
        game_name="Punishing: Gray Raven",
        name="Daily",
        runner_type="maa_punish",
        runner_config_version=1,
        runner_config_json=json.dumps(
            {
                "config_version": 1,
                "executable_path": str(fos),
                "config_id": config_id,
            }
        ),
        enabled=True,
        queue_order=1,
        timezone_id="Asia/Shanghai",
        reset_minute=240,
    )


def test_fos_configuration_discovery_and_controller_mapping(tmp_path: Path):
    fos, config_id = make_fos(tmp_path)

    configurations = discover_fos_configurations(fos)
    assert [(value.config_id, value.name) for value in configurations] == [
        (config_id, "每日任务")
    ]
    controller = read_fos_controller(configurations[0])
    assert controller is not None
    assert controller.controller_type == "Android"
    assert controller.address == "127.0.0.1:16384"
    assert controller.mumu_index == 0


def test_maa_punish_builds_internal_monitored_launch(tmp_path: Path):
    fos, config_id = make_fos(tmp_path)
    integration = MaaPunishIntegration()
    job = make_job(fos, config_id)

    assert integration.validate_config(job.runner_config).valid
    spec = integration.build_launch_spec(job)

    assert INTERNAL_FOS_RUNNER_ARG in spec.arguments
    assert str(fos) in spec.arguments
    assert config_id in spec.arguments
    assert spec.working_directory == str(fos.parent)
    assert "--direct-run" in spec.display_command
    assert "--reuse-existing" in spec.display_command
    assert "--close-fos-after-run" in spec.arguments


def test_maa_punish_rejects_missing_configuration(tmp_path: Path):
    fos, _ = make_fos(tmp_path)
    result = MaaPunishIntegration().validate_config(
        {
            "config_version": 1,
            "executable_path": str(fos),
            "config_id": "c_missing",
        }
    )
    assert not result.valid
    assert any("configuration was not found" in error for error in result.errors)


def test_maa_punish_can_leave_fos_open_and_rejects_invalid_close_setting(tmp_path: Path):
    fos, config_id = make_fos(tmp_path)
    integration = MaaPunishIntegration()
    job = make_job(fos, config_id)
    config = dict(job.runner_config)
    config["close_fos_after_run"] = False
    job = replace(job, runner_config_json=json.dumps(config))

    assert "--close-fos-after-run" not in integration.build_launch_spec(job).arguments
    config["close_fos_after_run"] = "yes"
    assert not integration.validate_config(config).valid


def test_maa_punish_rejects_mumu_instance_that_differs_from_fos_config(tmp_path: Path):
    fos, config_id = make_fos(tmp_path)
    mumu = tmp_path / "mumu-cli.exe"
    mumu.touch()
    result = MaaPunishIntegration().validate_config(
        {
            "config_version": 1,
            "executable_path": str(fos),
            "config_id": config_id,
            "auto_start_emulator": True,
            "emulator_type": "mumu",
            "emulator_executable_path": str(mumu),
            "emulator_instance_index": 1,
            "emulator_start_timeout_seconds": 120,
        }
    )
    assert not result.valid
    assert any("does not match" in error for error in result.errors)


def test_registry_registers_maa_punish():
    assert default_registry().get("maa_punish").display_name == "MAA_Punish"
