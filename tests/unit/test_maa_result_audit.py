from __future__ import annotations

from game_control_plane.application.maa_result_audit import assess_managed_maa_output
from game_control_plane.integrations.maa_managed_task import default_managed_daily


def managed_config() -> dict[str, object]:
    return {
        "task_mode": "managed",
        "task_name": "control_plane_test",
        "managed_daily": default_managed_daily(),
    }


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
