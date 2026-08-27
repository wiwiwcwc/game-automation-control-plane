from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

from game_control_plane.application.execution_service import ExecutionService
from game_control_plane.domain.models import RunState
from game_control_plane.integrations.base import LaunchSpec, ValidationResult
from game_control_plane.integrations.registry import IntegrationRegistry
from game_control_plane.persistence.database import Database
from game_control_plane.persistence.store import Store


_APP: QApplication | None = None


def app_instance() -> QApplication:
    global _APP
    _APP = QApplication.instance() or QApplication([])
    return _APP


class FakeWorker:
    pid = 45700

    def __init__(self, exit_code: int):
        self.exit_code = exit_code
        self.closed = False

    def poll_exit_code(self) -> int | None:
        return self.exit_code

    def close(self) -> None:
        self.closed = True


class FakeLocator:
    def __init__(self, worker: FakeWorker | None, race: bool = False):
        self.worker = worker
        self.race = race
        self.calls = 0

    def find_worker(self, launcher_pid, launcher_executable, process_names):
        self.calls += 1
        if self.race and self.calls == 1:
            return None
        return self.worker


class HandoffFixtureIntegration:
    runner_type = "ok_ww_test"
    display_name = "OK-WW test"
    config_version = 1

    def __init__(self, fixture: Path, mode: str):
        self.fixture = fixture
        self.mode = mode

    def validate_config(self, _config):
        return ValidationResult.ok()

    def build_launch_spec(self, _job):
        return LaunchSpec(
            executable=sys.executable,
            arguments=(str(self.fixture), "--mode", self.mode),
            working_directory=str(self.fixture.parent),
            display_command="fixture handoff",
            handoff_process_names=("pythonw.exe", "python.exe"),
        )


def make_job(store: Store):
    job_id = store.save_job(
        game_name="Wuthering Waves",
        name="OK-WW handoff test",
        runner_type="ok_ww_test",
        runner_config_version=1,
        runner_config={"config_version": 1},
        timezone_id="UTC",
        reset_minute=240,
    )
    return store.get_job(job_id)


def run_case(tmp_path: Path, worker: FakeWorker | None, *, race: bool = False):
    fixture = Path(__file__).parents[1] / "fixtures" / "fixture_cli.py"
    database = Database(tmp_path / "control.sqlite3")
    store = Store(database)
    job = make_job(store)
    assert job
    registry = IntegrationRegistry(
        [HandoffFixtureIntegration(fixture, "failure")]
    )
    locator = FakeLocator(worker, race=race)
    execution = ExecutionService(
        store,
        tmp_path / "runs",
        registry=registry,
        handoff_locator=locator,
        handoff_grace_seconds=0.2,
        handoff_poll_interval_ms=20,
    )
    app_instance()
    loop = QEventLoop()
    result = {}
    execution.run_finished.connect(
        lambda run_id: (result.setdefault("run", store.get_run(run_id)), loop.quit())
    )
    run = execution.start(job)
    QTimer.singleShot(5000, loop.quit)
    loop.exec()
    database.close()
    return result.get("run"), locator


def test_execution_waits_for_worker_found_after_launcher_exit(tmp_path: Path):
    run, locator = run_case(tmp_path, FakeWorker(0), race=True)
    assert run and run.state == RunState.EXITED
    assert run.exit_code == 0
    assert locator.calls >= 2


def test_execution_uses_worker_nonzero_exit(tmp_path: Path):
    run, _ = run_case(tmp_path, FakeWorker(9))
    assert run and run.state == RunState.FAILED
    assert run.exit_code == 9
    assert run.error_summary == "OK-WW worker exited with code 9."


def test_execution_falls_back_when_worker_is_not_found(tmp_path: Path):
    run, locator = run_case(tmp_path, None)
    assert run and run.state == RunState.FAILED
    assert run.exit_code == 7
    assert run.error_summary == "The process exited with code 7."
    assert locator.calls >= 2
