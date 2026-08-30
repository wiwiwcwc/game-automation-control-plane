from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QEventLoop, QObject, QTimer, Signal
from PySide6.QtWidgets import QApplication

from game_control_plane.application.execution_service import ExecutionService
from game_control_plane.application.maa_result_audit import RunResultAssessment
from game_control_plane.application.post_run_actions import PostRunAction
from game_control_plane.application.process_supervisor import (
    ProcessIdentity,
    ProcessTerminationResult,
)
from game_control_plane.application.queue_service import QueueService, QueueState
from game_control_plane.domain.models import DailyStatus, ErrorKind, RunState
from game_control_plane.integrations.base import LaunchSpec, ValidationResult
from game_control_plane.integrations.custom_cli import CustomCliIntegration
from game_control_plane.integrations.registry import IntegrationRegistry
from game_control_plane.persistence.database import Database
from game_control_plane.persistence.store import Store
from game_control_plane.ui.i18n import LanguageManager


_APP: QApplication | None = None


def app_instance() -> QApplication:
    global _APP
    _APP = QApplication.instance() or QApplication([])
    return _APP


def create_job(store: Store, fixture: Path, mode: str):
    job_id = store.save_job(
        game_name="Fixture",
        name=f"Fixture {mode}",
        runner_type="custom_cli",
        runner_config_version=1,
        runner_config={
            "config_version": 1,
            "executable_path": sys.executable,
            "arguments": [str(fixture), "--mode", mode],
            "working_directory": str(fixture.parent),
        },
        timezone_id="UTC",
        reset_minute=240,
    )
    return store.get_job(job_id)


def test_qprocess_captures_streams_and_classifies_exit(tmp_path: Path):
    fixture = Path(__file__).parents[1] / "fixtures" / "fixture_cli.py"
    database = Database(tmp_path / "control.sqlite3")
    store = Store(database)
    service = ExecutionService(store, tmp_path / "runs")
    success_job = create_job(store, fixture, "success")
    failed_job = create_job(store, fixture, "failure")
    assert success_job and failed_job

    app_instance()
    loop = QEventLoop()
    finished_runs = {}

    def on_finished(identifier: str):
        finished_runs[identifier] = service.store.get_run(identifier)
        loop.quit()

    service.run_finished.connect(on_finished)
    success = service.start(success_job)
    QTimer.singleShot(5000, loop.quit)
    loop.exec()
    finished_success = finished_runs.get(success.id)
    assert finished_success is not None
    assert finished_success.state == RunState.EXITED
    assert finished_success.exit_code == 0
    assert store.daily_status(success_job) == DailyStatus.PENDING
    assert "fixture stdout" in Path(finished_success.stdout_path).read_text()
    assert "fixture stderr" in Path(finished_success.stderr_path).read_text()

    failed = service.start(failed_job)
    QTimer.singleShot(5000, loop.quit)
    loop.exec()
    finished_failed = finished_runs.get(failed.id)
    service.run_finished.disconnect(on_finished)
    assert finished_failed is not None
    assert finished_failed.state == RunState.FAILED
    assert finished_failed.exit_code == 7
    assert finished_failed.error_kind == "nonzero_exit"


def test_queue_runs_real_qprocesses_sequentially_after_failure(tmp_path: Path):
    fixture = Path(__file__).parents[1] / "fixtures" / "fixture_cli.py"
    database = Database(tmp_path / "control.sqlite3")
    store = Store(database)
    execution = ExecutionService(store, tmp_path / "runs")
    queue = QueueService(store, execution)
    failed_job = create_job(store, fixture, "failure")
    success_job = create_job(store, fixture, "success")
    assert failed_job and success_job
    store.connection.execute("UPDATE jobs SET queue_order = 1 WHERE id = ?", (failed_job.id,))
    store.connection.execute("UPDATE jobs SET queue_order = 2 WHERE id = ?", (success_job.id,))
    store.connection.commit()

    app_instance()
    loop = QEventLoop()
    queue.queue_finished.connect(loop.quit)
    assert queue.start()
    QTimer.singleShot(10000, loop.quit)
    loop.exec()

    assert queue.state == QueueState.IDLE
    failed_run = store.latest_run(failed_job.id)
    success_run = store.latest_run(success_job.id)
    assert failed_run and success_run
    assert failed_run.trigger_type == "queue"
    assert success_run.trigger_type == "queue"
    assert failed_run.state.value == "failed"
    assert failed_run.exit_code == 7
    assert success_run.state.value == "exited"
    assert success_run.exit_code == 0
    assert store.daily_status(failed_job) == DailyStatus.PENDING
    assert store.daily_status(success_job) == DailyStatus.PENDING


class MissingExecutableIntegration:
    runner_type = "missing_executable_test"
    config_version = 1

    def validate_config(self, _config):
        return ValidationResult.ok()

    def build_launch_spec(self, _job):
        return LaunchSpec(
            executable=str(Path(__file__).parent / "does-not-exist.exe"),
            arguments=(),
            working_directory=None,
            display_command="does-not-exist.exe",
        )


def test_queue_continues_after_qprocess_failed_to_start(tmp_path: Path):
    fixture = Path(__file__).parents[1] / "fixtures" / "fixture_cli.py"
    database = Database(tmp_path / "control.sqlite3")
    store = Store(database)
    registry = IntegrationRegistry(
        [MissingExecutableIntegration(), CustomCliIntegration()]
    )
    execution = ExecutionService(store, tmp_path / "runs", registry=registry)
    queue = QueueService(store, execution)
    missing_id = store.save_job(
        game_name="Missing",
        name="Cannot launch",
        runner_type="missing_executable_test",
        runner_config_version=1,
        runner_config={"config_version": 1},
        timezone_id="UTC",
        reset_minute=240,
    )
    missing_job = store.get_job(missing_id)
    success_job = create_job(store, fixture, "success")
    assert missing_job and success_job

    app_instance()
    loop = QEventLoop()
    queue.queue_finished.connect(loop.quit)
    assert queue.start()
    QTimer.singleShot(10000, loop.quit)
    loop.exec()

    assert queue.state == QueueState.IDLE
    missing_run = store.latest_run(missing_job.id)
    success_run = store.latest_run(success_job.id)
    assert missing_run and success_run
    assert missing_run.state == RunState.FAILED
    assert missing_run.error_kind == "failed_to_start"
    assert success_run.state == RunState.EXITED
    assert store.daily_status(missing_job) == DailyStatus.PENDING
    assert store.daily_status(success_job) == DailyStatus.PENDING


class SleepingMaaIntegration:
    runner_type = "maa_cli"
    display_name = "MAA test"
    config_version = 1

    def __init__(self, fixture: Path, seconds: float = 10):
        self.fixture = fixture
        self.seconds = seconds

    def validate_config(self, _config):
        return ValidationResult.ok()

    def build_launch_spec(self, _job):
        return LaunchSpec(
            executable=sys.executable,
            arguments=(
                str(self.fixture),
                "--mode",
                "sleep",
                "--seconds",
                str(self.seconds),
            ),
            working_directory=str(self.fixture.parent),
            display_command="fixture_cli.py --mode sleep --seconds 10",
        )


class FixtureOneDragonIntegration:
    runner_type = "zzz_onedragon"
    display_name = "ZZZ OneDragon fixture"
    config_version = 1

    def __init__(self, fixture: Path, seconds: float | None = None):
        self.fixture = fixture
        self.seconds = seconds

    def validate_config(self, _config):
        return ValidationResult.ok()

    def build_launch_spec(self, _job):
        arguments = (str(self.fixture), "--mode", "success")
        if self.seconds is not None:
            arguments = (
                str(self.fixture),
                "--mode",
                "sleep",
                "--seconds",
                str(self.seconds),
            )
        return LaunchSpec(
            executable=sys.executable,
            arguments=arguments,
            working_directory=str(self.fixture.parent),
            display_command="OneDragon-RuntimeLauncher.exe -o",
        )


class RecordingProcessSupervisor:
    """Test double that records exact identities without touching process names."""

    def __init__(self, *, verify_result: bool = True):
        self.verify_result = verify_result
        self.captured: list[ProcessIdentity] = []
        self.verified: list[ProcessIdentity] = []
        self.terminated: list[ProcessIdentity] = []

    def capture(self, pid: int, expected_executable: str) -> ProcessIdentity:
        identity = ProcessIdentity(
            pid=pid,
            executable=expected_executable,
            token=f"test-token-{pid}",
        )
        self.captured.append(identity)
        return identity

    def verify(self, identity: ProcessIdentity) -> bool:
        self.verified.append(identity)
        return self.verify_result

    def terminate_tree(self, identity: ProcessIdentity) -> ProcessTerminationResult:
        self.terminated.append(identity)
        return ProcessTerminationResult(
            success=True,
            attempted_pids=(identity.pid,),
        )


def _wait_for_run(service: ExecutionService, run_id: str, timeout_ms: int = 5_000):
    loop = QEventLoop()

    def on_finished(identifier: str):
        if identifier == run_id:
            loop.quit()

    service.run_finished.connect(on_finished)
    QTimer.singleShot(timeout_ms, loop.quit)
    loop.exec()
    service.run_finished.disconnect(on_finished)
    return service.store.get_run(run_id)


def create_onedragon_job(store: Store, name: str = "OneDragon daily"):
    job_id = store.save_job(
        game_name="Zenless Zone Zero",
        name=name,
        runner_type="zzz_onedragon",
        runner_config_version=1,
        runner_config={"config_version": 1},
        timezone_id="UTC",
        reset_minute=240,
    )
    return store.get_job(job_id)


def test_onedragon_stop_interrupts_only_exact_owned_run_and_persists_identity(tmp_path: Path):
    fixture = Path(__file__).parents[1] / "fixtures" / "fixture_cli.py"
    store = Store(Database(tmp_path / "control.sqlite3"))
    supervisor = RecordingProcessSupervisor()
    service = ExecutionService(
        store,
        tmp_path / "runs",
        registry=IntegrationRegistry([FixtureOneDragonIntegration(fixture, seconds=10)]),
        emulator_watchdog_factory=lambda _job, _parent: None,
        process_supervisor=supervisor,
        stop_grace_ms=25,
    )
    first = create_onedragon_job(store, "OneDragon first")
    second = create_onedragon_job(store, "OneDragon second")
    assert first and second
    app_instance()

    first_run = service.start(first)
    second_run = service.start(second)
    QTimer.singleShot(100, lambda: service.stop(first_run.id, reason="test stop"))
    finished_first = _wait_for_run(service, first_run.id)

    assert finished_first is not None
    assert finished_first.state == RunState.INTERRUPTED
    assert finished_first.error_kind == "interrupted"
    assert store.daily_status(first) == DailyStatus.PENDING
    assert len(supervisor.terminated) == 1
    assert supervisor.terminated[0].pid == supervisor.captured[0].pid
    snapshot = json.loads(finished_first.launch_snapshot_json)
    assert snapshot["owned_process"]["verified"] is True
    assert snapshot["root_process_token"] == supervisor.captured[0].token
    assert service.is_job_running(second.id)

    service.stop(second_run.id, reason="test cleanup")
    assert _wait_for_run(service, second_run.id) is not None
    assert len(supervisor.terminated) == 2


def test_onedragon_stop_refuses_pid_reuse_and_records_stop_failure(tmp_path: Path):
    fixture = Path(__file__).parents[1] / "fixtures" / "fixture_cli.py"
    store = Store(Database(tmp_path / "control.sqlite3"))
    supervisor = RecordingProcessSupervisor(verify_result=False)
    service = ExecutionService(
        store,
        tmp_path / "runs",
        registry=IntegrationRegistry([FixtureOneDragonIntegration(fixture, seconds=0.25)]),
        emulator_watchdog_factory=lambda _job, _parent: None,
        process_supervisor=supervisor,
        stop_grace_ms=25,
    )
    job = create_onedragon_job(store)
    assert job
    app_instance()
    run = service.start(job)
    # Keep the fixture alive until identity verification has happened. This
    # exercises the refusal path rather than a cooperative process exit.
    service._request_graceful_stop = lambda _active: None
    QTimer.singleShot(40, lambda: service.stop(run.id, reason="test pid reuse"))
    finished = _wait_for_run(service, run.id)

    assert finished is not None
    assert finished.state == RunState.FAILED
    assert finished.error_kind == "stop_failed"
    assert "changed" in (finished.error_summary or "")
    assert supervisor.verified
    assert not supervisor.terminated


def test_stop_is_idempotent_and_rejects_unverified_root_without_name_lookup(tmp_path: Path):
    fixture = Path(__file__).parents[1] / "fixtures" / "fixture_cli.py"
    store = Store(Database(tmp_path / "control.sqlite3"))
    supervisor = RecordingProcessSupervisor()
    supervisor.capture = lambda _pid, _expected: None
    service = ExecutionService(
        store,
        tmp_path / "runs",
        registry=IntegrationRegistry([FixtureOneDragonIntegration(fixture, seconds=0.25)]),
        emulator_watchdog_factory=lambda _job, _parent: None,
        process_supervisor=supervisor,
        stop_grace_ms=25,
    )
    job = create_onedragon_job(store)
    assert job
    app_instance()
    run = service.start(job)
    service._request_graceful_stop = lambda _active: None
    calls = []
    QTimer.singleShot(40, lambda: calls.extend((service.stop(run.id), service.stop(run.id))))
    finished = _wait_for_run(service, run.id)

    assert calls == [True, True]
    assert finished is not None
    assert finished.state == RunState.FAILED
    assert finished.error_kind == "stop_failed"
    assert not supervisor.terminated


def test_onedragon_clean_exit_needs_manual_completion_review(tmp_path: Path):
    fixture = Path(__file__).parents[1] / "fixtures" / "fixture_cli.py"
    store = Store(Database(tmp_path / "control.sqlite3"))
    service = ExecutionService(
        store,
        tmp_path / "runs",
        registry=IntegrationRegistry([FixtureOneDragonIntegration(fixture)]),
    )
    job_id = store.save_job(
        game_name="Zenless Zone Zero",
        name="ZZZ daily",
        runner_type="zzz_onedragon",
        runner_config_version=1,
        runner_config={"config_version": 1},
        timezone_id="UTC",
        reset_minute=240,
    )
    job = store.get_job(job_id)
    assert job is not None
    app_instance()
    loop = QEventLoop()
    service.run_finished.connect(loop.quit)

    run = service.start(job)
    QTimer.singleShot(5_000, loop.quit)
    loop.exec()

    finished = store.get_run(run.id)
    assert finished is not None
    assert finished.state == RunState.NEEDS_ATTENTION
    assert finished.exit_code == 0
    assert finished.error_kind == ErrorKind.AUTOMATION_INCOMPLETE.value
    assert "cannot verify" in (finished.error_summary or "")
    assert "manually" in (finished.error_summary or "")
    assert store.daily_status(job) == DailyStatus.PENDING
    assert "[Hsiesta]" in Path(finished.stderr_path).read_text(encoding="utf-8")


class FakeEmulatorWatchdog(QObject):
    lost = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.started = False
        self.stopped = False

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True


def test_maa_run_stops_and_fails_when_associated_emulator_closes(tmp_path: Path):
    fixture = Path(__file__).parents[1] / "fixtures" / "fixture_cli.py"
    database = Database(tmp_path / "control.sqlite3")
    store = Store(database)
    watchdogs: list[FakeEmulatorWatchdog] = []

    def make_watchdog(_job, parent):
        watchdog = FakeEmulatorWatchdog(parent)
        watchdogs.append(watchdog)
        return watchdog

    service = ExecutionService(
        store,
        tmp_path / "runs",
        registry=IntegrationRegistry([SleepingMaaIntegration(fixture)]),
        emulator_watchdog_factory=make_watchdog,
        emulator_stop_grace_ms=25,
    )
    job_id = store.save_job(
        game_name="Arknights",
        name="Daily",
        runner_type="maa_cli",
        runner_config_version=1,
        runner_config={"config_version": 1},
        timezone_id="UTC",
        reset_minute=240,
    )
    job = store.get_job(job_id)
    assert job is not None
    app_instance()
    loop = QEventLoop()
    service.run_finished.connect(loop.quit)

    run = service.start(job)
    QTimer.singleShot(
        100,
        lambda: watchdogs[0].lost.emit(
            "MuMu instance 1 was closed. The associated MAA run was stopped."
        ),
    )
    QTimer.singleShot(5_000, loop.quit)
    loop.exec()

    finished = store.get_run(run.id)
    assert finished is not None
    assert finished.state == RunState.FAILED
    assert finished.error_kind == "emulator_disconnected"
    assert "instance 1 was closed" in (finished.error_summary or "")
    assert watchdogs[0].started
    assert watchdogs[0].stopped
    assert not service.is_running


def test_different_jobs_run_concurrently_but_same_job_cannot_duplicate(tmp_path: Path):
    fixture = Path(__file__).parents[1] / "fixtures" / "fixture_cli.py"
    store = Store(Database(tmp_path / "control.sqlite3"))
    service = ExecutionService(store, tmp_path / "runs")
    first = create_job(store, fixture, "sleep")
    second = create_job(store, fixture, "sleep")
    assert first and second
    app_instance()

    first_run = service.start(first)
    second_run = service.start(second)
    assert {run.id for run in service.active_runs} == {first_run.id, second_run.id}
    assert service.active_job_ids == {first.id, second.id}
    with pytest.raises(RuntimeError, match="already running"):
        service.start(first)

    loop = QEventLoop()
    finished: set[str] = set()

    def on_finished(run_id: str):
        finished.add(run_id)
        if len(finished) == 2:
            loop.quit()

    service.run_finished.connect(on_finished)
    QTimer.singleShot(5_000, loop.quit)
    loop.exec()
    assert finished == {first_run.id, second_run.id}
    assert not service.is_running


def test_successful_run_waits_for_post_action_and_surfaces_cleanup_warning(tmp_path: Path):
    fixture = Path(__file__).parents[1] / "fixtures" / "fixture_cli.py"
    store = Store(Database(tmp_path / "control.sqlite3"))

    def failed_cleanup(_job, _context):
        return PostRunAction(
            executable=sys.executable,
            arguments=(str(fixture), "--mode", "failure"),
            display_command="fixture cleanup failure",
            description="Close MuMu instance 1",
        )

    service = ExecutionService(
        store,
        tmp_path / "runs",
        post_run_action_factory=failed_cleanup,
    )
    job = create_job(store, fixture, "success")
    assert job
    app_instance()
    loop = QEventLoop()
    service.run_finished.connect(loop.quit)

    run = service.start(job)
    QTimer.singleShot(5_000, loop.quit)
    loop.exec()

    finished = store.get_run(run.id)
    assert finished is not None
    assert finished.state == RunState.EXITED
    assert finished.exit_code == 0
    assert finished.error_kind == "post_run_action_failed"
    assert "automation succeeded" in (finished.error_summary or "").casefold()
    assert "fixture cleanup failure" in Path(finished.stdout_path).read_text()


def test_result_needing_attention_skips_post_run_cleanup(tmp_path: Path):
    fixture = Path(__file__).parents[1] / "fixtures" / "fixture_cli.py"
    store = Store(Database(tmp_path / "control.sqlite3"))
    cleanup_calls: list[str] = []

    def cleanup(_job, _context):
        cleanup_calls.append("created")
        return PostRunAction(
            executable=sys.executable,
            arguments=(str(fixture), "--mode", "success"),
            display_command="cleanup must not run",
            description="Close MuMu instance 1",
        )

    service = ExecutionService(
        store,
        tmp_path / "runs",
        post_run_action_factory=cleanup,
        result_auditor=lambda _job, _stdout, _stderr: RunResultAssessment(
            needs_attention=True,
            summary="MAA completed zero battles. The emulator was left open.",
        ),
    )
    job = create_job(store, fixture, "success")
    assert job
    app_instance()
    loop = QEventLoop()
    service.run_finished.connect(loop.quit)

    run = service.start(job)
    QTimer.singleShot(5_000, loop.quit)
    loop.exec()

    finished = store.get_run(run.id)
    assert cleanup_calls == ["created"]
    assert finished is not None
    assert finished.state == RunState.NEEDS_ATTENTION
    assert finished.error_kind == ErrorKind.AUTOMATION_INCOMPLETE.value
    assert "left open" in (finished.error_summary or "")
    assert "cleanup must not run" not in Path(finished.stdout_path).read_text()


def test_external_maa_clean_exit_needs_review_and_skips_cleanup(tmp_path: Path):
    fixture = Path(__file__).parents[1] / "fixtures" / "fixture_cli.py"
    store = Store(Database(tmp_path / "control.sqlite3"))
    cleanup_calls: list[str] = []

    def cleanup(_job, _context):
        cleanup_calls.append("created")
        return PostRunAction(
            executable=sys.executable,
            arguments=(str(fixture), "--mode", "success"),
            display_command="external MAA cleanup must not run",
            description="Close MuMu instance 1",
        )

    language = LanguageManager("zh_CN", persist=False)
    service = ExecutionService(
        store,
        tmp_path / "runs",
        registry=IntegrationRegistry([SleepingMaaIntegration(fixture, seconds=0)]),
        post_run_action_factory=cleanup,
        emulator_watchdog_factory=lambda _job, _parent: None,
        summary_text=language.text,
    )
    job_id = store.save_job(
        game_name="Arknights",
        name="External daily",
        runner_type="maa_cli",
        runner_config_version=1,
        runner_config={
            "config_version": 1,
            "task_mode": "external",
            "task_name": "daily",
            "auto_start_emulator": True,
            "emulator_executable_path": "C:/MuMu/mumu-cli.exe",
            "emulator_instance_index": 1,
            "close_emulator_after_run": True,
        },
        timezone_id="UTC",
        reset_minute=240,
    )
    job = store.get_job(job_id)
    assert job is not None
    app_instance()
    loop = QEventLoop()
    service.run_finished.connect(loop.quit)

    run = service.start(
        job,
        runtime_context={"emulator_started_by_control_plane": True},
    )
    QTimer.singleShot(5_000, loop.quit)
    loop.exec()

    finished = store.get_run(run.id)
    assert finished is not None
    assert finished.state == RunState.NEEDS_ATTENTION
    assert finished.exit_code == 0
    assert finished.error_kind == ErrorKind.MAA_EXTERNAL_UNVERIFIED.value
    assert "外部 MAA 任务已正常退出" in (finished.error_summary or "")
    assert "自动关闭模拟器已跳过" in (finished.error_summary or "")
    assert cleanup_calls == ["created"]
    assert "external MAA cleanup must not run" not in Path(finished.stdout_path).read_text()
    assert store.daily_status(job) == DailyStatus.PENDING


def test_external_maa_attention_advances_queue_by_exact_run_id(tmp_path: Path):
    fixture = Path(__file__).parents[1] / "fixtures" / "fixture_cli.py"
    store = Store(Database(tmp_path / "control.sqlite3"))
    service = ExecutionService(
        store,
        tmp_path / "runs",
        registry=IntegrationRegistry([SleepingMaaIntegration(fixture, seconds=0)]),
    )
    job_ids = [
        store.save_job(
            game_name="Arknights",
            name=name,
            runner_type="maa_cli",
            runner_config_version=1,
            runner_config={
                "config_version": 1,
                "task_mode": "external",
                "task_name": "daily",
            },
            timezone_id="UTC",
            reset_minute=240,
        )
        for name in ("First external", "Second external")
    ]
    jobs = [store.get_job(job_id) for job_id in job_ids]
    assert all(jobs)

    queue = QueueService(store, service)
    started_ids: list[int] = []
    queue.item_started.connect(started_ids.append)
    app_instance()
    loop = QEventLoop()
    queue.queue_finished.connect(loop.quit)

    assert queue.start()
    assert queue.current_job_id == jobs[0].id
    service.run_finished.emit("stale-run-id")
    assert queue.current_job_id == jobs[0].id

    QTimer.singleShot(5_000, loop.quit)
    loop.exec()

    assert started_ids == [jobs[0].id, jobs[1].id]
    assert queue.state == QueueState.IDLE
    assert queue.current_run_id is None
    for job in jobs:
        run = store.latest_run(job.id)
        assert run is not None
        assert run.state == RunState.NEEDS_ATTENTION
        assert run.exit_code == 0
        assert run.error_kind == ErrorKind.MAA_EXTERNAL_UNVERIFIED.value
        assert store.daily_status(job) == DailyStatus.PENDING


def test_same_mumu_instance_is_exclusive_while_other_jobs_may_run(tmp_path: Path):
    fixture = Path(__file__).parents[1] / "fixtures" / "fixture_cli.py"
    store = Store(Database(tmp_path / "control.sqlite3"))
    service = ExecutionService(
        store,
        tmp_path / "runs",
        registry=IntegrationRegistry([SleepingMaaIntegration(fixture, seconds=0.2)]),
        emulator_watchdog_factory=lambda _job, _parent: None,
    )
    config = {
        "config_version": 1,
        "auto_start_emulator": True,
        "emulator_executable_path": "C:/MuMu/mumu-cli.exe",
        "emulator_instance_index": 1,
    }
    job_ids = [
        store.save_job(
            game_name="Arknights",
            name=name,
            runner_type="maa_cli",
            runner_config_version=1,
            runner_config=config,
            timezone_id="UTC",
            reset_minute=240,
        )
        for name in ("First", "Second")
    ]
    first, second = (store.get_job(identifier) for identifier in job_ids)
    assert first and second
    app_instance()

    run = service.start(first)
    with pytest.raises(RuntimeError, match="MuMu instance"):
        service.start(second)

    loop = QEventLoop()
    service.run_finished.connect(loop.quit)
    QTimer.singleShot(5_000, loop.quit)
    loop.exec()
    assert store.get_run(run.id).state == RunState.NEEDS_ATTENTION


def test_failed_main_process_does_not_start_post_run_cleanup(tmp_path: Path):
    fixture = Path(__file__).parents[1] / "fixtures" / "fixture_cli.py"
    store = Store(Database(tmp_path / "control.sqlite3"))

    def cleanup(_job, _context):
        return PostRunAction(
            executable=sys.executable,
            arguments=(str(fixture), "--mode", "success"),
            display_command="cleanup should not run",
            description="Close MuMu instance 1",
        )

    service = ExecutionService(
        store,
        tmp_path / "runs",
        post_run_action_factory=cleanup,
    )
    job = create_job(store, fixture, "failure")
    assert job
    app_instance()
    loop = QEventLoop()
    service.run_finished.connect(loop.quit)

    run = service.start(job)
    QTimer.singleShot(5_000, loop.quit)
    loop.exec()

    finished = store.get_run(run.id)
    assert finished is not None and finished.state == RunState.FAILED
    assert "cleanup should not run" not in Path(finished.stdout_path).read_text()


def test_post_run_cleanup_timeout_does_not_hang_or_rewrite_success(tmp_path: Path):
    fixture = Path(__file__).parents[1] / "fixtures" / "fixture_cli.py"
    store = Store(Database(tmp_path / "control.sqlite3"))

    def slow_cleanup(_job, _context):
        return PostRunAction(
            executable=sys.executable,
            arguments=(str(fixture), "--mode", "sleep", "--seconds", "5"),
            display_command="slow cleanup",
            description="Close MuMu instance 1",
        )

    service = ExecutionService(
        store,
        tmp_path / "runs",
        post_run_action_factory=slow_cleanup,
        post_run_action_timeout_ms=25,
    )
    job = create_job(store, fixture, "success")
    assert job
    app_instance()
    loop = QEventLoop()
    service.run_finished.connect(loop.quit)

    run = service.start(job)
    QTimer.singleShot(5_000, loop.quit)
    loop.exec()

    finished = store.get_run(run.id)
    assert finished is not None
    assert finished.state == RunState.EXITED
    assert finished.exit_code == 0
    assert finished.error_kind == "post_run_action_failed"
    assert "timed out" in (finished.error_summary or "")
