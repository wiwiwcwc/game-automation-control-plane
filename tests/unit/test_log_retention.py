from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from game_control_plane.domain.models import RunState
from game_control_plane.persistence.database import Database
from game_control_plane.persistence.store import Store
from game_control_plane.platform.log_retention import prune_run_logs


def make_store(tmp_path: Path) -> Store:
    return Store(Database(tmp_path / "control.sqlite3"))


def make_job(store: Store, name: str):
    job_id = store.save_job(
        game_name="Game",
        name=name,
        runner_type="custom_cli",
        runner_config_version=1,
        runner_config={"config_version": 1, "executable_path": "x", "arguments": []},
        timezone_id="UTC",
        reset_minute=240,
    )
    return store.get_job(job_id)


def add_run(store: Store, job_id: int, root: Path, identifier: str, stamp: str, state: RunState):
    run_dir = root / identifier
    run_dir.mkdir(parents=True)
    stdout = run_dir / "stdout.log"
    stderr = run_dir / "stderr.log"
    stdout.write_text(identifier, encoding="utf-8")
    stderr.write_text(identifier, encoding="utf-8")
    return store.create_run(
        run_id=identifier,
        job_id=job_id,
        trigger_type="manual",
        state=state,
        started_at_utc=stamp,
        finished_at_utc=stamp,
        exit_code=0 if state == RunState.EXITED else 1,
        stdout_path=str(stdout),
        stderr_path=str(stderr),
        launch_snapshot={"job_id": job_id},
    )


def test_retention_prunes_old_logs_preserves_latest_failure_and_metadata(tmp_path: Path):
    store = make_store(tmp_path)
    root = tmp_path / "runs"
    root.mkdir()
    job = make_job(store, "Daily")
    assert job
    old_success = add_run(
        store, job.id, root, "old-success", "2026-07-01T00:00:00+00:00", RunState.EXITED
    )
    old_failed = add_run(
        store, job.id, root, "old-failed", "2026-07-02T00:00:00+00:00", RunState.FAILED
    )
    latest_failed = add_run(
        store, job.id, root, "latest-failed", "2026-07-03T00:00:00+00:00", RunState.FAILED
    )
    boundary = add_run(
        store, job.id, root, "boundary", "2026-07-25T00:00:00+00:00", RunState.EXITED
    )

    result = prune_run_logs(
        root,
        store,
        now=datetime(2026, 8, 24, tzinfo=timezone.utc),
    )
    assert old_success.id in result.removed_run_ids
    assert old_failed.id in result.removed_run_ids
    assert latest_failed.id not in result.removed_run_ids
    assert boundary.id not in result.removed_run_ids
    assert not (root / "old-success").exists()
    assert not (root / "old-failed").exists()
    assert (root / "latest-failed").is_dir()
    assert (root / "boundary").is_dir()
    assert store.get_run(old_success.id) is not None
    assert store.get_run(latest_failed.id) is not None


def test_retention_confines_paths_to_direct_run_children(tmp_path: Path):
    store = make_store(tmp_path)
    root = tmp_path / "runs"
    root.mkdir()
    job = make_job(store, "Daily")
    assert job
    outside = tmp_path / "outside"
    outside.mkdir()
    outside_log = outside / "stdout.log"
    outside_err = outside / "stderr.log"
    outside_log.write_text("outside", encoding="utf-8")
    outside_err.write_text("outside", encoding="utf-8")
    outside_run = store.create_run(
        run_id="outside-run",
        job_id=job.id,
        trigger_type="manual",
        state=RunState.EXITED,
        started_at_utc="2026-07-01T00:00:00+00:00",
        finished_at_utc="2026-07-01T00:00:00+00:00",
        stdout_path=str(outside_log),
        stderr_path=str(outside_err),
        launch_snapshot={"job_id": job.id},
    )
    nested = root / "nested" / "run"
    nested.mkdir(parents=True)
    nested_log = nested / "stdout.log"
    nested_err = nested / "stderr.log"
    nested_log.write_text("nested", encoding="utf-8")
    nested_err.write_text("nested", encoding="utf-8")
    nested_run = store.create_run(
        run_id="nested-run",
        job_id=job.id,
        trigger_type="manual",
        state=RunState.EXITED,
        started_at_utc="2026-07-01T00:00:00+00:00",
        finished_at_utc="2026-07-01T00:00:00+00:00",
        stdout_path=str(nested_log),
        stderr_path=str(nested_err),
        launch_snapshot={"job_id": job.id},
    )
    mismatched = root / "different-run-id"
    mismatched.mkdir()
    mismatched_log = mismatched / "stdout.log"
    mismatched_err = mismatched / "stderr.log"
    mismatched_log.write_text("mismatched", encoding="utf-8")
    mismatched_err.write_text("mismatched", encoding="utf-8")
    mismatched_run = store.create_run(
        run_id="database-run-id",
        job_id=job.id,
        trigger_type="manual",
        state=RunState.EXITED,
        started_at_utc="2026-07-01T00:00:00+00:00",
        finished_at_utc="2026-07-01T00:00:00+00:00",
        stdout_path=str(mismatched_log),
        stderr_path=str(mismatched_err),
        launch_snapshot={"job_id": job.id},
    )

    result = prune_run_logs(
        root,
        store,
        now=datetime(2026, 8, 24, tzinfo=timezone.utc),
    )
    assert outside_run.id not in result.removed_run_ids
    assert nested_run.id not in result.removed_run_ids
    assert mismatched_run.id not in result.removed_run_ids
    assert outside_log.exists() and outside_err.exists()
    assert nested_log.exists() and nested_err.exists()
    assert mismatched_log.exists() and mismatched_err.exists()
    assert result.skipped_paths
