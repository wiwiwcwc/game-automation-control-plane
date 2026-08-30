from __future__ import annotations

import json
from pathlib import Path

from game_control_plane.domain.models import Job
from game_control_plane.application.post_run_actions import create_post_run_action


def make_job(mumu: Path, *, close_after: bool = True, runner_type: str = "maa_cli") -> Job:
    return Job(
        id=1,
        game_id=1,
        game_name="Arknights",
        name="Daily",
        runner_type=runner_type,
        runner_config_version=1,
        runner_config_json=json.dumps(
            {
                "config_version": 1,
                "auto_start_emulator": True,
                "close_emulator_after_run": close_after,
                "emulator_executable_path": str(mumu),
                "emulator_instance_index": 3,
            }
        ),
        enabled=True,
        queue_order=1,
        timezone_id="UTC",
        reset_minute=240,
    )


def test_mumu_shutdown_requires_run_scoped_start_ownership(tmp_path: Path):
    job = make_job(tmp_path / "mumu-cli.exe")

    assert create_post_run_action(job, None) is None
    assert create_post_run_action(
        job, {"emulator_started_by_control_plane": False}
    ) is None

    action = create_post_run_action(
        job, {"emulator_started_by_control_plane": True}
    )
    assert action is not None
    assert action.executable == str(tmp_path / "mumu-cli.exe")
    assert action.arguments == ("control", "--vmindex", "3", "shutdown")


def test_mumu_shutdown_respects_disabled_option(tmp_path: Path):
    job = make_job(tmp_path / "mumu-cli.exe", close_after=False)
    assert create_post_run_action(
        job, {"emulator_started_by_control_plane": True}
    ) is None


def test_fos_uses_the_same_run_scoped_mumu_shutdown_contract(tmp_path: Path):
    job = make_job(tmp_path / "mumu-cli.exe", runner_type="maa_punish")
    action = create_post_run_action(
        job, {"emulator_started_by_control_plane": True}
    )
    assert action is not None
    assert action.arguments == ("control", "--vmindex", "3", "shutdown")


def test_onedragon_close_game_option_does_not_create_hsiesta_shutdown_action(tmp_path: Path):
    job = make_job(tmp_path / "mumu-cli.exe", runner_type="zzz_onedragon")
    assert create_post_run_action(
        job, {"emulator_started_by_control_plane": True}
    ) is None
