from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QApplication, QDialog

from game_control_plane.application.process_supervisor import (
    ProcessIdentity,
    ProcessTerminationResult,
)
from game_control_plane.domain.models import RunState

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


class CloseTestProcessSupervisor:
    def __init__(self):
        self.terminated: list[ProcessIdentity] = []

    def capture(self, pid: int, expected_executable: str):
        return ProcessIdentity(pid, expected_executable, f"close-test-{pid}")

    def verify(self, _identity: ProcessIdentity):
        return True

    def terminate_tree(self, identity: ProcessIdentity):
        self.terminated.append(identity)
        return ProcessTerminationResult(success=True, attempted_pids=(identity.pid,))


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


def add_onedragon_job(window: MainWindow, launcher: Path, name="OneDragon") -> int:
    launcher.touch(exist_ok=True)
    (launcher.parent / ".runtime").mkdir(exist_ok=True)
    (launcher.parent / "src").mkdir(exist_ok=True)
    return window.store.save_job(
        game_name="Zenless Zone Zero",
        name=name,
        runner_type="zzz_onedragon",
        runner_config_version=1,
        runner_config={
            "config_version": 1,
            "executable_path": str(launcher),
            "instance_indices": "1,2",
            "close_game_after_run": True,
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


def test_normal_close_stops_owned_run_before_closing_database(tmp_path, monkeypatch):
    app_instance()
    window = MainWindow(app_paths(tmp_path / "app"))
    fixture_path = Path(__file__).parents[1] / "fixtures" / "fixture_cli.py"
    job_id = window.store.save_job(
        game_name="Test game",
        name="Long fixture",
        runner_type="custom_cli",
        runner_config_version=1,
        runner_config={
            "config_version": 1,
            "executable_path": sys.executable,
            "arguments": [
                str(fixture_path),
                "--mode",
                "sleep",
                "--seconds",
                "5",
            ],
            "working_directory": str(fixture_path.parent),
        },
        timezone_id="UTC",
        reset_minute=240,
    )
    job = window.store.get_job(job_id)
    assert job is not None
    supervisor = CloseTestProcessSupervisor()
    window.execution.process_supervisor = supervisor
    window.execution.stop_grace_ms = 25
    run = window.execution.start(job)

    monkeypatch.setattr(
        main_window.QMessageBox,
        "question",
        lambda *args, **kwargs: main_window.QMessageBox.StandardButton.Close,
    )
    finished_states: list[RunState] = []
    window.execution.run_finished.connect(
        lambda identifier: finished_states.append(window.store.get_run(identifier).state)
    )
    loop = QEventLoop()
    close_calls: list[bool] = []
    original_close = window.database.close

    def close_database():
        close_calls.append(window.execution.is_running)
        original_close()
        loop.quit()

    monkeypatch.setattr(window.database, "close", close_database)
    window.close()
    QTimer.singleShot(10_000, loop.quit)
    loop.exec()

    assert close_calls == [False]
    assert finished_states == [RunState.INTERRUPTED]
    assert supervisor.terminated and supervisor.terminated[0].pid > 0
    # The terminal-state callback was able to write while SQLite was still open.
    assert run.id not in {active.id for active in window.execution.active_runs}


def test_open_onedragon_gui_uses_no_args_and_creates_no_run(tmp_path, monkeypatch):
    app_instance()
    window = MainWindow(app_paths(tmp_path / "app"))
    launcher = tmp_path / "OneDragon-RuntimeLauncher.exe"
    launcher.touch()
    (tmp_path / ".runtime").mkdir()
    (tmp_path / "src").mkdir()
    job_id = window.store.save_job(
        game_name="Zenless Zone Zero",
        name="OneDragon GUI",
        runner_type="zzz_onedragon",
        runner_config_version=1,
        runner_config={
            "config_version": 1,
            "executable_path": str(launcher),
            "instance_indices": "1,2",
            "close_game_after_run": True,
        },
        timezone_id="UTC",
        reset_minute=240,
    )
    calls = []

    class DetachedProcess:
        @staticmethod
        def startDetached(*args):
            calls.append(args)
            return True

    monkeypatch.setattr(main_window, "QProcess", DetachedProcess)
    monkeypatch.setattr(
        window,
        "_onedragon_preflight_report",
        lambda _job: SimpleNamespace(ready=True),
    )
    monkeypatch.setattr(main_window.QMessageBox, "information", lambda *args: None)

    window.open_onedragon_gui(job_id)

    assert calls == [(str(launcher), [], str(tmp_path))]
    assert window.store.latest_run(job_id) is None
    window.database.close()


def test_open_onedragon_gui_is_blocked_while_automatic_run_is_active(tmp_path, monkeypatch):
    app_instance()
    window = MainWindow(app_paths(tmp_path / "app"))
    job_id = window.store.save_job(
        game_name="Zenless Zone Zero",
        name="OneDragon GUI blocked",
        runner_type="zzz_onedragon",
        runner_config_version=1,
        runner_config={"config_version": 1, "executable_path": str(tmp_path / "missing.exe")},
        timezone_id="UTC",
        reset_minute=240,
    )
    messages: list[str] = []
    monkeypatch.setattr(window.execution, "is_job_running", lambda _job_id: True)
    monkeypatch.setattr(
        main_window.QMessageBox,
        "information",
        lambda _parent, _title, body: messages.append(body),
    )

    window.open_onedragon_gui(job_id)

    assert messages and "不能附着" in messages[0]
    window.database.close()


def test_open_onedragon_gui_is_disabled_while_queued(tmp_path):
    app_instance()
    window = MainWindow(app_paths(tmp_path / "app"))
    job_id = add_onedragon_job(window, tmp_path / "OneDragon-RuntimeLauncher.exe")
    window.dashboard.set_jobs(
        [
            (
                window.store.get_job(job_id),
                window.store.daily_status(window.store.get_job(job_id)),
                None,
                False,
            )
        ],
        queue_active=True,
        queued_job_ids={job_id},
    )
    card = window.dashboard.cards_layout.itemAt(0).widget()

    assert not card.open_gui_button.isHidden()
    assert not card.open_gui_button.isEnabled()
    window.database.close()


def test_stop_button_uses_exact_onedragon_job_and_run_id(tmp_path, monkeypatch):
    app_instance()
    window = MainWindow(app_paths(tmp_path / "app"))
    job_id = add_onedragon_job(window, tmp_path / "OneDragon-RuntimeLauncher.exe")
    active = SimpleNamespace(id="exact-run-id", job_id=job_id)
    monkeypatch.setattr(
        type(window.execution),
        "active_runs",
        property(lambda _execution: (active,)),
    )
    calls: list[tuple[str, str | None]] = []
    monkeypatch.setattr(
        window.execution,
        "stop",
        lambda run_id, reason=None: calls.append((run_id, reason)) or True,
    )
    monkeypatch.setattr(window, "refresh", lambda: None)

    window.stop_job(job_id)

    assert calls == [("exact-run-id", window.i18n.text("run.stop_requested"))]
    window.database.close()


def test_open_onedragon_gui_failure_is_reported_without_creating_run(tmp_path, monkeypatch):
    app_instance()
    window = MainWindow(app_paths(tmp_path / "app"))
    launcher = tmp_path / "OneDragon-RuntimeLauncher.exe"
    job_id = add_onedragon_job(window, launcher)

    class FailedDetachedProcess:
        @staticmethod
        def startDetached(*_args):
            return False

    messages: list[str] = []
    monkeypatch.setattr(main_window, "QProcess", FailedDetachedProcess)
    monkeypatch.setattr(
        window,
        "_onedragon_preflight_report",
        lambda _job: SimpleNamespace(ready=True),
    )
    monkeypatch.setattr(
        main_window.QMessageBox,
        "critical",
        lambda _parent, _title, body: messages.append(body),
    )

    window.open_onedragon_gui(job_id)

    assert messages and str(launcher) in messages[0]
    assert window.store.latest_run(job_id) is None
    window.database.close()


def test_close_cancel_keeps_database_and_runtime_open(tmp_path, monkeypatch):
    app_instance()
    window = MainWindow(app_paths(tmp_path / "app"))
    active = SimpleNamespace(id="active", job_id=1)
    monkeypatch.setattr(
        type(window.execution),
        "is_running",
        property(lambda _execution: True),
    )
    monkeypatch.setattr(
        type(window.execution),
        "active_runs",
        property(lambda _execution: (active,)),
    )
    monkeypatch.setattr(
        main_window.QMessageBox,
        "question",
        lambda *_args, **_kwargs: main_window.QMessageBox.StandardButton.Cancel,
    )
    event = QCloseEvent()

    window.closeEvent(event)

    assert not event.isAccepted()
    assert not window._closing_requested
    assert not window._database_closed
    window.database.close()


def test_close_timeout_recomputes_remaining_runs_and_warns_only_for_finalized(tmp_path, monkeypatch):
    app_instance()
    window = MainWindow(app_paths(tmp_path / "app"))
    window._closing_requested = True
    window._closing_run_ids = {"timed-out", "already-gone"}
    finalized: list[str] = []
    monkeypatch.setattr(
        window.execution,
        "force_finalize_stop_timeout",
        lambda run_id: finalized.append(run_id) or run_id == "timed-out",
    )
    warnings: list[str] = []
    monkeypatch.setattr(
        main_window.QMessageBox,
        "warning",
        lambda _parent, _title, body: warnings.append(body),
    )
    ready_calls: list[bool] = []
    monkeypatch.setattr(
        window,
        "_request_close_if_ready",
        lambda: ready_calls.append(True),
    )

    window._close_stop_timeout()

    assert set(finalized) == {"timed-out", "already-gone"}
    assert window._closing_run_ids == set()
    assert len(warnings) == 1
    assert "1" in warnings[0]
    assert ready_calls == [True]
    window.database.close()


def test_late_run_finished_after_database_close_is_ignored_and_repeated_close_is_safe(
    tmp_path, monkeypatch
):
    app_instance()
    window = MainWindow(app_paths(tmp_path / "app"))
    close_calls: list[bool] = []
    original_close = window.database.close

    def close_database():
        close_calls.append(True)
        original_close()

    monkeypatch.setattr(window.database, "close", close_database)
    window.close()
    deadline = QEventLoop()
    QTimer.singleShot(250, deadline.quit)
    deadline.exec()
    assert window._database_closed

    monkeypatch.setattr(window, "refresh", lambda: (_ for _ in ()).throw(AssertionError()))
    monkeypatch.setattr(window.store, "get_run", lambda _run_id: (_ for _ in ()).throw(AssertionError()))
    window._run_finished("late-run")
    window._run_started("late-start")
    window._queue_state_changed()
    window.execution.run_finished.emit("late-single-shot")
    window.close()

    assert close_calls == [True]
