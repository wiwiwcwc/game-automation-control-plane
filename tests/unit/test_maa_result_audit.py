from __future__ import annotations

import json

from game_control_plane.application.maa_result_audit import (
    assess_external_maa_output,
    assess_managed_maa_output,
    assess_onedragon_output,
    assess_run_result,
)
from game_control_plane.domain.models import ErrorKind, Job

from game_control_plane.integrations.maa_managed_task import default_managed_daily


def managed_config() -> dict[str, object]:
    return {
        "task_mode": "managed",
        "task_name": "control_plane_test",
        "managed_daily": default_managed_daily(),
    }


def maa_job(config: dict[str, object]) -> Job:
    return Job(
        id=1,
        game_id=1,
        game_name="Arknights",
        name="Daily",
        runner_type="maa_cli",
        runner_config_version=1,
        runner_config_json=json.dumps(config),
        enabled=True,
        queue_order=1,
        timezone_id="UTC",
        reset_minute=240,
    )


def successful_summary() -> str:
    return """Summary
----------------------------------------
[开始唤醒] 10:00:00 - 10:01:00 Completed
[自动公招] 10:01:00 - 10:02:00 Completed
[基建换班] 10:02:00 - 10:03:00 Completed
[信用与购物] 10:03:00 - 10:04:00 Completed
[理智作战] 10:04:00 - 10:10:00 Completed
Fight 1-7 6 times, drops:
1. 固源岩 × 1
[领取奖励] 10:10:00 - 10:11:00 Completed
"""


def test_managed_maa_success_requires_all_summaries_and_a_real_battle():
    result = assess_managed_maa_output(managed_config(), successful_summary())
    assert not result.needs_attention


def test_external_maa_exit_zero_requires_manual_review():
    result = assess_external_maa_output("Summary\n", "")

    assert result.needs_attention
    assert result.localization_key == "run.maa_external_unverified"
    assert result.diagnostic_code == ErrorKind.MAA_EXTERNAL_UNVERIFIED.value
    assert "cannot verify" in result.summary
    assert "manually" in result.summary


def test_external_maa_dispatch_does_not_treat_exit_zero_as_verified(tmp_path):
    stdout = tmp_path / "stdout.txt"
    stderr = tmp_path / "stderr.txt"
    stdout.write_text(successful_summary(), encoding="utf-8")
    stderr.write_text("", encoding="utf-8")

    result = assess_run_result(
        maa_job(
            {
                "config_version": 1,
                "task_mode": "external",
                "task_name": "daily",
            }
        ),
        stdout,
        stderr,
    )

    assert result.needs_attention


def test_managed_maa_dispatch_keeps_strict_completion_audit(tmp_path):
    stdout = tmp_path / "stdout.txt"
    stderr = tmp_path / "stderr.txt"
    stdout.write_text(
        successful_summary().replace(
            "[领取奖励] 10:10:00 - 10:11:00 Completed\n",
            "",
        ),
        encoding="utf-8",
    )
    stderr.write_text("", encoding="utf-8")

    result = assess_run_result(maa_job(managed_config()), stdout, stderr)

    assert result.needs_attention
    assert "领取奖励" in result.summary


def test_managed_maa_dispatch_preserves_verified_success(tmp_path):
    stdout = tmp_path / "stdout.txt"
    stderr = tmp_path / "stderr.txt"
    stdout.write_text(successful_summary(), encoding="utf-8")
    stderr.write_text("", encoding="utf-8")

    result = assess_run_result(maa_job(managed_config()), stdout, stderr)

    assert not result.needs_attention


def test_zero_battle_is_partial_even_when_maa_labels_fight_completed():
    stdout = successful_summary().replace("Fight 1-7 6 times, drops:\n1. 固源岩 × 1\n", "")
    result = assess_managed_maa_output(managed_config(), stdout)

    assert result.needs_attention
    assert "zero battles" in result.summary
    assert "left open" in result.summary


def test_missing_or_unstarted_task_is_partial():
    stdout = successful_summary().replace(
        "[信用与购物] 10:03:00 - 10:04:00 Completed\n",
        "[信用与购物] Unstarted\n",
    )
    result = assess_managed_maa_output(managed_config(), stdout)

    assert result.needs_attention
    assert "unfinished task" in result.summary


def test_task_chain_error_is_partial_even_with_a_complete_summary():
    result = assess_managed_maa_output(
        managed_config(), successful_summary(), "TaskChainError: Fight"
    )
    assert result.needs_attention
    assert "task-chain error" in result.summary


def test_onedragon_exit_is_always_manual_review(tmp_path):
    stdout = tmp_path / "stdout.txt"
    stderr = tmp_path / "stderr.txt"
    stdout.write_text("OneDragon finished", encoding="utf-8")
    stderr.write_text("", encoding="utf-8")

    result = assess_onedragon_output(stdout, stderr)

    assert result.needs_attention
    assert "cannot verify" in result.summary
    assert "mark the daily complete manually" in result.summary
