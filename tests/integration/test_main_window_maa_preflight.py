from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication, QDialog

from game_control_plane.integrations.maa_preflight import (
    CheckState,
    CheckStep,
    MaaPreflightReport,
)
from game_control_plane.platform.paths import app_paths
from game_control_plane.ui import main_window
from game_control_plane.ui.main_window import MainWindow


_APP: QApplication | None = None


def app_instance() -> QApplication:
    global _APP
    _APP = QApplication.instance() or QApplication([])
    return _APP


def blocked_report() -> MaaPreflightReport:
    return MaaPreflightReport(
        (
            CheckStep("executable", "MAA program", CheckState.PASSED, "Ready"),
            CheckStep("task", "MAA task", CheckState.PASSED, "Ready"),
            CheckStep("dry_run", "Task configuration", CheckState.PASSED, "Ready"),
            CheckStep(
                "adb",
                "Emulator connection",
                CheckState.FAILED,
                "No emulator",
                "Start it and retry.",
            ),
        )
    )


class RejectingGuide:
    DialogCode = QDialog.DialogCode

    def __init__(self, report, check_again, parent=None, i18n=None):
        self.report = report
        self.edit_requested = False

    def exec(self):
        return QDialog.DialogCode.Rejected


def add_maa_job(window: MainWindow) -> int:
    return window.store.save_job(
        game_name="Arknights",
        name="Daily",
        runner_type="maa_cli",
        runner_config_version=1,
        runner_config={
            "config_version": 1,
            "executable_path": sys.executable,
            "task_name": "daily",
        },
        timezone_id="UTC",
        reset_minute=240,
    )


def test_failed_preflight_blocks_manual_run_without_creating_history(tmp_path, monkeypatch):
    app_instance()
    window = MainWindow(app_paths(tmp_path / "app"))
    job_id = add_maa_job(window)
    monkeypatch.setattr(
        main_window,
        "run_preflight_with_progress",
        lambda config, parent=None, i18n=None: (blocked_report(), None),
    )
    monkeypatch.setattr(main_window, "MaaPreflightDialog", RejectingGuide)

    window.run_job(job_id)

    assert not window.execution.is_running
    assert window.store.latest_run(job_id) is None
    window.database.close()


def test_failed_preflight_blocks_daily_queue_before_any_item_starts(tmp_path, monkeypatch):
    app_instance()
    window = MainWindow(app_paths(tmp_path / "app"))
    job_id = add_maa_job(window)
    monkeypatch.setattr(
        main_window,
        "run_preflight_with_progress",
        lambda config, parent=None, i18n=None: (blocked_report(), None),
    )
    monkeypatch.setattr(main_window, "MaaPreflightDialog", RejectingGuide)

    window.run_today_dailies()

    assert not window.queue.active
    assert window.store.latest_run(job_id) is None
    window.database.close()


def test_queue_moves_emulator_ownership_to_last_same_instance_consumer(tmp_path):
    app_instance()
    window = MainWindow(app_paths(tmp_path / "app"))
    common = {
        "config_version": 1,
        "executable_path": sys.executable,
        "task_name": "daily",
        "auto_start_emulator": True,
        "emulator_type": "mumu",
        "emulator_executable_path": "C:/MuMu/mumu-cli.exe",
        "emulator_instance_index": 1,
        "emulator_start_timeout_seconds": 120,
        "close_emulator_after_run": True,
    }
    jobs = []
    for name in ("First", "Last"):
        identifier = window.store.save_job(
            game_name="Arknights",
            name=name,
            runner_type="maa_cli",
            runner_config_version=1,
            runner_config=common,
            timezone_id="UTC",
            reset_minute=240,
        )
        jobs.append(window.store.get_job(identifier))
    contexts = {
        int(jobs[0].id): {"emulator_started_by_control_plane": True},
        int(jobs[1].id): {"emulator_started_by_control_plane": False},
    }

    window._transfer_queue_emulator_ownership(jobs, contexts)

    assert not contexts[int(jobs[0].id)]["emulator_started_by_control_plane"]
    assert contexts[int(jobs[1].id)]["emulator_started_by_control_plane"]
    window.database.close()
