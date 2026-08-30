from __future__ import annotations

import json

from game_control_plane.domain.models import ErrorKind, Run, RunState
from game_control_plane.ui.diagnostics import format_run_diagnostic, persisted_diagnostic_code
from game_control_plane.ui.i18n import LanguageManager


def make_run(
    *,
    state: RunState,
    error_kind: str | None,
    error_summary: str = "raw upstream detail",
    exit_code: int | None = 1,
    snapshot: dict[str, object] | None = None,
) -> Run:
    return Run(
        id="run-1",
        job_id=1,
        trigger_type="manual",
        state=state,
        started_at_utc=None,
        finished_at_utc=None,
        exit_code=exit_code,
        exit_status="normal",
        error_kind=error_kind,
        error_summary=error_summary,
        stdout_path=None,
        stderr_path=None,
        launch_snapshot_json=json.dumps(snapshot or {}),
        created_at_utc="2026-08-30T00:00:00+00:00",
    )


def test_external_history_uses_persisted_snapshot_after_job_mode_changes():
    run = make_run(
        state=RunState.NEEDS_ATTENTION,
        error_kind=ErrorKind.AUTOMATION_INCOMPLETE.value,
        exit_code=0,
        snapshot={
            "runner_type": "maa_cli",
            "runner_config": {"task_mode": "external"},
        },
    )

    assert persisted_diagnostic_code(run) == ErrorKind.MAA_EXTERNAL_UNVERIFIED.value
    display = format_run_diagnostic(LanguageManager("en_US", persist=False), run)
    assert display.summary.startswith("The external MAA task exited normally")
    assert display.technical_detail == "raw upstream detail"


def test_managed_reasons_are_localized_and_raw_detail_is_separate():
    run = make_run(
        state=RunState.NEEDS_ATTENTION,
        error_kind=ErrorKind.MAA_MANAGED_INCOMPLETE.value,
        error_summary="raw MAA audit",
        exit_code=0,
        snapshot={
            "diagnostic_params": {
                "missing": ["领取奖励"],
                "incomplete": ["理智作战: Unstarted"],
                "zero_battles": True,
                "task_chain_error": True,
            }
        },
    )
    display = format_run_diagnostic(LanguageManager("zh_CN", persist=False), run)
    assert "MAA 日常任务未完成" in display.summary
    assert "缺少完成摘要" in display.summary
    assert "raw MAA audit" == display.technical_detail


def test_cleanup_reason_and_unknown_code_have_safe_localized_summaries():
    cleanup = make_run(
        state=RunState.EXITED,
        error_kind=ErrorKind.POST_RUN_ACTION_FAILED.value,
        snapshot={"diagnostic_params": {"reason": "timeout"}},
        exit_code=0,
    )
    unknown = make_run(
        state=RunState.FAILED,
        error_kind="future_diagnostic_code",
        error_summary="future upstream text",
    )
    manager = LanguageManager("en_US", persist=False)
    assert "cleanup action timed out" in format_run_diagnostic(manager, cleanup).summary
    unknown_display = format_run_diagnostic(manager, unknown)
    assert unknown_display.summary.startswith("The run result needs review")
    assert unknown_display.technical_detail == "future upstream text"
