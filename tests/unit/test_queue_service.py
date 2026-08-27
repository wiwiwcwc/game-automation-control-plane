from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QObject, Signal

from game_control_plane.application.queue_service import QueueService, QueueState
from game_control_plane.domain.models import DailyStatus
from game_control_plane.persistence.database import Database
from game_control_plane.persistence.store import Store


_APP: QCoreApplication | None = None


class FakeRun:
    def __init__(self, identifier: str, job_id: int):
        self.id = identifier
        self.job_id = job_id


class FakeExecutor(QObject):
    run_finished = Signal(str)

    def __init__(self, fail_to_start: set[int] | None = None):
        super().__init__()
        self.fail_to_start = fail_to_start or set()
        self.attempts: list[tuple[int, str]] = []
        self.contexts: list[dict[str, object] | None] = []
        self.runs: dict[str, FakeRun] = {}
        self.outcomes: dict[str, str] = {}
        self.active_run: FakeRun | None = None
        self._next_id = 1

    def start(self, job, trigger_type="manual", runtime_context=None):
        self.attempts.append((job.id, trigger_type))
        self.contexts.append(runtime_context)
        if job.id in self.fail_to_start:
            raise RuntimeError(f"failed to start {job.name}")
        run = FakeRun(f"fake-run-{self._next_id}", job.id)
        self._next_id += 1
        self.runs[run.id] = run
        self.active_run = run
        return run

    def finish(self, outcome: str = "exited"):
        assert self.active_run is not None
        run = self.active_run
        self.active_run = None
        self.outcomes[run.id] = outcome
        self.run_finished.emit(run.id)


class Clock:
    def __call__(self):
        return datetime(2026, 8, 24, 8, tzinfo=timezone.utc)


def make_store(tmp_path: Path) -> Store:
    return Store(Database(tmp_path / "control.sqlite3"), clock=Clock())


def add_job(store: Store, name: str, enabled: bool = True):
    job_id = store.save_job(
        game_name="Game",
        name=name,
        runner_type="custom_cli",
        runner_config_version=1,
        runner_config={"config_version": 1, "executable_path": "not-used", "arguments": []},
        timezone_id="UTC",
        reset_minute=240,
        enabled=enabled,
    )
    if not enabled:
        store.set_job_enabled(job_id, False)
    return store.get_job(job_id)


def pump_events() -> None:
    global _APP
    _APP = QCoreApplication.instance() or QCoreApplication([])
    for _ in range(3):
        _APP.processEvents()


def test_queue_snapshots_order_and_excludes_disabled_or_completed(tmp_path: Path):
    store = make_store(tmp_path)
    first = add_job(store, "First")
    second = add_job(store, "Second")
    disabled = add_job(store, "Disabled", enabled=False)
    completed = add_job(store, "Completed")
    assert first and second and disabled and completed
    store.connection.execute("UPDATE jobs SET queue_order = 20 WHERE id = ?", (first.id,))
    store.connection.execute("UPDATE jobs SET queue_order = 10 WHERE id = ?", (second.id,))
    store.connection.commit()
    store.mark_completed(completed)

    executor = FakeExecutor()
    queue = QueueService(store, executor)
    finished = []
    queue.queue_finished.connect(lambda: finished.append(True))

    assert queue.start()
    assert queue.state == QueueState.ACTIVE
    assert executor.attempts == [(second.id, "queue")]
    assert queue.current_job_id == second.id
    assert queue.queued_job_ids == (first.id,)

    executor.finish("exited")
    pump_events()
    assert executor.attempts == [(second.id, "queue"), (first.id, "queue")]
    assert queue.current_job_id == first.id

    executor.finish("exited")
    pump_events()
    assert queue.state == QueueState.IDLE
    assert queue.current_job_id is None
    assert queue.queued_job_ids == ()
    assert finished == [True]
    assert store.daily_status(first) == DailyStatus.PENDING
    assert store.daily_status(second) == DailyStatus.PENDING
    assert store.daily_status(completed) == DailyStatus.COMPLETED


def test_queue_continues_after_start_failure_and_process_failure(tmp_path: Path):
    store = make_store(tmp_path)
    cannot_start = add_job(store, "Cannot start")
    failed = add_job(store, "Nonzero exit")
    last = add_job(store, "Last job")
    assert cannot_start and failed and last
    executor = FakeExecutor(fail_to_start={cannot_start.id})
    queue = QueueService(store, executor)
    start_failures = []
    queue.item_failed_to_start.connect(lambda job_id, message: start_failures.append((job_id, message)))

    assert queue.start()
    pump_events()
    assert executor.attempts == [
        (cannot_start.id, "queue"),
        (failed.id, "queue"),
    ]
    assert start_failures and start_failures[0][0] == cannot_start.id

    executor.finish("failed")
    pump_events()
    assert executor.attempts[-1] == (last.id, "queue")
    executor.finish("exited")
    pump_events()
    assert queue.state == QueueState.IDLE
    assert queue.current_run_id is None
    assert all(store.daily_status(job) == DailyStatus.PENDING for job in (cannot_start, failed, last))


def test_empty_queue_stays_idle(tmp_path: Path):
    store = make_store(tmp_path)
    completed = add_job(store, "Completed")
    disabled = add_job(store, "Disabled", enabled=False)
    assert completed and disabled
    store.mark_completed(completed)
    executor = FakeExecutor()
    queue = QueueService(store, executor)
    empty = []
    queue.queue_empty.connect(lambda: empty.append(True))

    assert not queue.start()
    assert queue.state == QueueState.IDLE
    assert empty == [True]
    assert executor.attempts == []


def test_queue_excludes_active_jobs_and_passes_per_run_context(tmp_path: Path):
    store = make_store(tmp_path)
    active = add_job(store, "Already active")
    queued = add_job(store, "Queued")
    assert active and queued
    executor = FakeExecutor()
    queue = QueueService(store, executor)
    context = {"emulator_started_by_control_plane": True}

    assert queue.start(
        excluded_job_ids={int(active.id)},
        runtime_contexts={int(queued.id): context},
    )

    assert executor.attempts == [(queued.id, "queue")]
    assert executor.contexts == [context]
