from __future__ import annotations

import json

from PySide6.QtWidgets import QApplication

from game_control_plane.domain.models import DailyStatus, ErrorKind, Job, Run, RunState
from game_control_plane.ui.dashboard import JobCard
from game_control_plane.ui.i18n import LanguageManager
from game_control_plane.integrations.onedragon import ZZZ_ONEDRAGON_RUNNER_TYPE


_APP: QApplication | None = None


def app_instance() -> QApplication:
    global _APP
    _APP = QApplication.instance() or QApplication([])
    return _APP


def make_job() -> Job:
    return Job(
        id=1,
        game_id=1,
        game_name="Wuthering Waves",
        name="Daily",
        runner_type="ok_ww",
        runner_config_version=1,
        runner_config_json=json.dumps({"config_version": 1}),
        enabled=True,
        queue_order=1,
        timezone_id="UTC",
        reset_minute=240,
    )


def test_queue_only_locks_cards_that_are_part_of_that_queue():
    app = app_instance()
    card = JobCard()
    job = make_job()

    card.set_job(job, DailyStatus.PENDING, None, False, None, queue_active=True)
    assert card.run_button.isEnabled()

    card.set_job(job, DailyStatus.PENDING, None, False, "queued", queue_active=True)
    assert not card.run_button.isEnabled()


def test_onedragon_card_exposes_gui_and_stop_actions_only_for_the_matching_state():
    app = app_instance()
    card = JobCard()
    job = Job(
        id=2,
        game_id=2,
        game_name="Zenless Zone Zero",
        name="OneDragon daily",
        runner_type=ZZZ_ONEDRAGON_RUNNER_TYPE,
        runner_config_version=1,
        runner_config_json=json.dumps({"config_version": 1}),
        enabled=True,
        queue_order=1,
        timezone_id="UTC",
        reset_minute=240,
    )

    card.show()
    card.set_job(job, DailyStatus.PENDING, None, False)
    app.processEvents()
    assert card.run_button.text() == "自动运行"
    assert card.open_gui_button.isVisible()
    assert card.open_gui_button.isEnabled()
    assert not card.stop_button.isVisible()

    running = Run(
        id="run-1",
        job_id=2,
        trigger_type="manual",
        state=RunState.RUNNING,
        started_at_utc=None,
        finished_at_utc=None,
        exit_code=None,
        exit_status=None,
        error_kind=None,
        error_summary=None,
        stdout_path=None,
        stderr_path=None,
        launch_snapshot_json="{}",
        created_at_utc="2026-08-29T00:00:00+00:00",
    )
    card.set_job(job, DailyStatus.PENDING, running, True)
    assert not card.open_gui_button.isEnabled()
    assert card.stop_button.isVisible()
    assert card.stop_button.isEnabled()


def test_non_onedragon_card_keeps_gui_and_stop_actions_hidden():
    app = app_instance()
    card = JobCard()
    card.set_job(make_job(), DailyStatus.PENDING, None, False)
    card.show()
    app.processEvents()
    assert not card.open_gui_button.isVisible()
    assert not card.stop_button.isVisible()
    assert card.run_button.text() == "运行"


def test_external_maa_card_shows_unverified_review_state_in_both_languages():
    app_instance()
    manager = LanguageManager("zh_CN", persist=False)
    card = JobCard(manager)
    job = Job(
        id=3,
        game_id=3,
        game_name="Arknights",
        name="External daily",
        runner_type="maa_cli",
        runner_config_version=1,
        runner_config_json=json.dumps(
            {
                "config_version": 1,
                "task_mode": "managed",
                "task_name": "control_plane_daily",
            }
        ),
        enabled=True,
        queue_order=1,
        timezone_id="UTC",
        reset_minute=240,
    )
    run = Run(
        id="run-3",
        job_id=3,
        trigger_type="manual",
        state=RunState.NEEDS_ATTENTION,
        started_at_utc=None,
        finished_at_utc=None,
        exit_code=0,
        exit_status="normal",
        error_kind=ErrorKind.AUTOMATION_INCOMPLETE.value,
        error_summary="External MAA needs review.",
        stdout_path=None,
        stderr_path=None,
        launch_snapshot_json=json.dumps(
            {
                "runner_type": "maa_cli",
                "runner_config": {
                    "config_version": 1,
                    "task_mode": "external",
                    "task_name": "daily",
                },
            }
        ),
        created_at_utc="2026-08-30T00:00:00+00:00",
    )

    card.set_job(job, DailyStatus.PENDING, run, False)
    assert card.execution_metric.value.text().startswith("未验证 · 需要检查")
    assert card.status_pill.text() == "未验证"

    manager.set_language("en_US")

    assert card.execution_metric.value.text().startswith("Unverified · needs review")
    assert card.status_pill.text() == "Unverified"


def test_dashboard_does_not_relabel_managed_or_onedragon_attention_runs():
    app_instance()
    manager = LanguageManager("zh_CN", persist=False)
    card = JobCard(manager)
    managed_job = Job(
        id=4,
        game_id=4,
        game_name="Arknights",
        name="Managed daily",
        runner_type="maa_cli",
        runner_config_version=1,
        runner_config_json=json.dumps(
            {"config_version": 1, "task_mode": "managed", "task_name": "control_plane_daily"}
        ),
        enabled=True,
        queue_order=1,
        timezone_id="UTC",
        reset_minute=240,
    )
    managed_run = Run(
        id="run-4",
        job_id=4,
        trigger_type="manual",
        state=RunState.NEEDS_ATTENTION,
        started_at_utc=None,
        finished_at_utc=None,
        exit_code=0,
        exit_status="normal",
        error_kind=ErrorKind.AUTOMATION_INCOMPLETE.value,
        error_summary="Managed MAA needs review.",
        stdout_path=None,
        stderr_path=None,
        launch_snapshot_json=json.dumps(
            {
                "runner_type": "maa_cli",
                "runner_config": {
                    "config_version": 1,
                    "task_mode": "managed",
                    "task_name": "control_plane_daily",
                },
            }
        ),
        created_at_utc="2026-08-30T00:00:00+00:00",
    )

    card.set_job(managed_job, DailyStatus.PENDING, managed_run, False)
    assert card.execution_metric.value.text().startswith("部分完成 · 需要检查")

    onedragon_job = Job(
        id=5,
        game_id=5,
        game_name="Zenless Zone Zero",
        name="OneDragon daily",
        runner_type=ZZZ_ONEDRAGON_RUNNER_TYPE,
        runner_config_version=1,
        runner_config_json=json.dumps({"config_version": 1}),
        enabled=True,
        queue_order=1,
        timezone_id="UTC",
        reset_minute=240,
    )
    onedragon_run = Run(
        id="run-5",
        job_id=5,
        trigger_type="manual",
        state=RunState.NEEDS_ATTENTION,
        started_at_utc=None,
        finished_at_utc=None,
        exit_code=0,
        exit_status="normal",
        error_kind=ErrorKind.AUTOMATION_INCOMPLETE.value,
        error_summary="OneDragon needs review.",
        stdout_path=None,
        stderr_path=None,
        launch_snapshot_json="{}",
        created_at_utc="2026-08-30T00:00:00+00:00",
    )

    card.set_job(onedragon_job, DailyStatus.PENDING, onedragon_run, False)
    assert card.execution_metric.value.text().startswith("进程已正常结束 · 结果未验证")

    manager.set_language("en_US")
    assert card.execution_metric.value.text().startswith(
        "Process ended normally · result unverified"
    )
