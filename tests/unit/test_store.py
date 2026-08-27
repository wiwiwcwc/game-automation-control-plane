from datetime import datetime, timezone
import json

from game_control_plane.domain.models import DailyStatus, ErrorKind, RunState
from game_control_plane.persistence.database import Database
from game_control_plane.persistence.store import Store


class Clock:
    def __init__(self, value: datetime):
        self.value = value

    def __call__(self) -> datetime:
        return self.value


def make_store(tmp_path, clock=None):
    database = Database(tmp_path / "control.sqlite3")
    return Store(database, clock=clock or Clock(datetime(2026, 8, 24, 4, tzinfo=timezone.utc)))


def make_job(store: Store):
    job_id = store.save_job(
        game_name="Test game",
        name="Daily",
        runner_type="custom_cli",
        runner_config_version=1,
        runner_config={"config_version": 1, "executable_path": "x", "arguments": []},
        timezone_id="UTC",
        reset_minute=240,
    )
    return store.get_job(job_id)


def test_store_persists_job_and_manual_completion(tmp_path):
    clock = Clock(datetime(2026, 8, 24, 4, tzinfo=timezone.utc))
    store = make_store(tmp_path, clock)
    job = make_job(store)
    assert job is not None
    assert store.daily_status(job) == DailyStatus.PENDING
    store.mark_completed(job)
    assert store.daily_status(job) == DailyStatus.COMPLETED
    store.undo_completed(job)
    assert store.daily_status(job) == DailyStatus.PENDING


def test_completion_becomes_pending_after_reset(tmp_path):
    clock = Clock(datetime(2026, 8, 24, 5, tzinfo=timezone.utc))
    store = make_store(tmp_path, clock)
    job = make_job(store)
    assert job is not None
    store.mark_completed(job)
    assert store.daily_status(job) == DailyStatus.COMPLETED
    clock.value = datetime(2026, 8, 25, 3, 59, tzinfo=timezone.utc)
    assert store.daily_status(job) == DailyStatus.COMPLETED
    clock.value = datetime(2026, 8, 25, 4, tzinfo=timezone.utc)
    assert store.daily_status(job) == DailyStatus.PENDING


def test_recovery_marks_starting_and_running_interrupted(tmp_path):
    store = make_store(tmp_path)
    job = make_job(store)
    assert job is not None
    for state in (RunState.STARTING, RunState.RUNNING):
        run = store.create_run(
            job_id=job.id,
            trigger_type="manual",
            state=state,
            started_at_utc=store.now_iso(),
            stdout_path=None,
            stderr_path=None,
            launch_snapshot={"job_id": job.id},
        )
        assert store.get_run(run.id).state == state
    recovered = store.recover_incomplete_runs()
    assert len(recovered) == 2
    runs = store.list_runs(job.id)
    assert all(run.state == RunState.INTERRUPTED for run in runs)
    assert all(run.error_kind == ErrorKind.INTERRUPTED.value for run in runs)


def test_database_migration_is_applied_once_across_restarts(tmp_path):
    path = tmp_path / "control.sqlite3"
    first = Database(path)
    assert [
        row[0]
        for row in first.connection.execute(
            "SELECT version FROM schema_migrations"
        ).fetchall()
    ] == [1]
    first.close()

    second = Database(path)
    assert [
        row[0]
        for row in second.connection.execute(
            "SELECT version FROM schema_migrations"
        ).fetchall()
    ] == [1]
    assert second.connection.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name = 'jobs'"
    ).fetchone()[0] == 1
    second.close()


def test_job_order_moves_persist_and_respect_boundaries(tmp_path):
    database = Database(tmp_path / "control.sqlite3")
    store = Store(database)
    ids = [
        store.save_job(
            game_name="Game",
            name=name,
            runner_type="custom_cli",
            runner_config_version=1,
            runner_config={"config_version": 1, "executable_path": "x", "arguments": []},
            timezone_id="UTC",
            reset_minute=240,
        )
        for name in ("First", "Second", "Third")
    ]
    assert not store.move_job_up(ids[0])
    assert not store.move_job_down(ids[2])
    assert store.move_job_up(ids[1])
    assert [job.id for job in store.list_jobs()] == [ids[1], ids[0], ids[2]]
    assert store.move_job_down(ids[1])
    assert [job.id for job in store.list_jobs()] == ids
    assert not store.move_job_up(99999)
    database.close()

    reopened = Store(Database(tmp_path / "control.sqlite3"))
    assert [job.name for job in reopened.list_jobs()] == ["First", "Second", "Third"]
    reopened.database.close()
