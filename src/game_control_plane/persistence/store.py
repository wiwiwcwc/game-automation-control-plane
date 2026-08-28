from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from ..domain.daily_cycle import period_start_iso
from ..domain.models import (
    CompletionSource,
    DailyStatus,
    ErrorKind,
    Job,
    Run,
    RunState,
)
from .database import Database


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_iso(value: datetime | None = None) -> str:
    current = value or utc_now()
    if current.tzinfo is None or current.utcoffset() is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc).isoformat(timespec="milliseconds")


class Store:
    def __init__(self, database: Database, clock: Callable[[], datetime] = utc_now):
        self.database = database
        self.connection = database.connection
        self.clock = clock

    def now_iso(self) -> str:
        return utc_iso(self.clock())

    def create_or_get_game(self, name: str) -> int:
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("game name is required")
        now = self.now_iso()
        row = self.connection.execute("SELECT id FROM games WHERE name = ?", (clean_name,)).fetchone()
        if row:
            self.connection.execute("UPDATE games SET updated_at_utc = ? WHERE id = ?", (now, row[0]))
            self.connection.commit()
            return int(row[0])
        cursor = self.connection.execute(
            "INSERT INTO games(name, created_at_utc, updated_at_utc) VALUES (?, ?, ?)",
            (clean_name, now, now),
        )
        self.connection.commit()
        return int(cursor.lastrowid)

    def list_jobs(self) -> list[Job]:
        rows = self.connection.execute(
            "SELECT j.*, g.name AS game_name FROM jobs j "
            "JOIN games g ON g.id = j.game_id "
            "ORDER BY j.queue_order, j.id"
        ).fetchall()
        return [_job_from_row(row) for row in rows]

    def get_job(self, job_id: int) -> Job | None:
        row = self.connection.execute(
            "SELECT j.*, g.name AS game_name FROM jobs j "
            "JOIN games g ON g.id = j.game_id WHERE j.id = ?",
            (job_id,),
        ).fetchone()
        return _job_from_row(row) if row else None

    def save_job(
        self,
        *,
        game_name: str,
        name: str,
        runner_type: str,
        runner_config_version: int,
        runner_config: dict[str, object],
        timezone_id: str,
        reset_minute: int,
        enabled: bool = True,
        job_id: int | None = None,
    ) -> int:
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("job name is required")
        game_id = self.create_or_get_game(game_name)
        config_json = json.dumps(runner_config, ensure_ascii=False, separators=(",", ":"))
        now = self.now_iso()
        if job_id is None:
            row = self.connection.execute("SELECT COALESCE(MAX(queue_order), 0) + 1 FROM jobs").fetchone()
            queue_order = int(row[0])
            cursor = self.connection.execute(
                "INSERT INTO jobs(game_id, name, runner_type, runner_config_version, "
                "runner_config_json, enabled, queue_order, timezone_id, reset_minute, "
                "created_at_utc, updated_at_utc) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    game_id,
                    clean_name,
                    runner_type,
                    runner_config_version,
                    config_json,
                    int(enabled),
                    queue_order,
                    timezone_id,
                    reset_minute,
                    now,
                    now,
                ),
            )
            self.connection.commit()
            return int(cursor.lastrowid)
        self.connection.execute(
            "UPDATE jobs SET game_id = ?, name = ?, runner_type = ?, runner_config_version = ?, "
            "runner_config_json = ?, enabled = ?, timezone_id = ?, reset_minute = ?, "
            "updated_at_utc = ? WHERE id = ?",
            (
                game_id,
                clean_name,
                runner_type,
                runner_config_version,
                config_json,
                int(enabled),
                timezone_id,
                reset_minute,
                now,
                job_id,
            ),
        )
        self.connection.commit()
        return job_id

    def set_job_enabled(self, job_id: int, enabled: bool) -> None:
        self.connection.execute(
            "UPDATE jobs SET enabled = ?, updated_at_utc = ? WHERE id = ?",
            (int(enabled), self.now_iso(), job_id),
        )
        self.connection.commit()

    def move_job_up(self, job_id: int) -> bool:
        return self._move_job(job_id, direction="up")

    def move_job_down(self, job_id: int) -> bool:
        return self._move_job(job_id, direction="down")

    def _move_job(self, job_id: int, *, direction: str) -> bool:
        row = self.connection.execute(
            "SELECT id, queue_order FROM jobs WHERE id = ?", (job_id,)
        ).fetchone()
        if row is None:
            return False
        current_order = int(row["queue_order"])
        if direction == "up":
            adjacent = self.connection.execute(
                "SELECT id, queue_order FROM jobs WHERE queue_order < ? "
                "ORDER BY queue_order DESC, id DESC LIMIT 1",
                (current_order,),
            ).fetchone()
        elif direction == "down":
            adjacent = self.connection.execute(
                "SELECT id, queue_order FROM jobs WHERE queue_order > ? "
                "ORDER BY queue_order, id LIMIT 1",
                (current_order,),
            ).fetchone()
        else:  # pragma: no cover - private method guard
            raise ValueError(f"unsupported move direction: {direction}")
        if adjacent is None:
            return False
        now = self.now_iso()
        with self.connection:
            self.connection.execute(
                "UPDATE jobs SET queue_order = ?, updated_at_utc = ? WHERE id = ?",
                (int(adjacent["queue_order"]), now, job_id),
            )
            self.connection.execute(
                "UPDATE jobs SET queue_order = ?, updated_at_utc = ? WHERE id = ?",
                (current_order, now, int(adjacent["id"])),
            )
        return True

    def delete_job(self, job_id: int) -> None:
        with self.connection:
            self.connection.execute(
                "DELETE FROM daily_completions WHERE job_id = ?", (job_id,)
            )
            self.connection.execute("DELETE FROM runs WHERE job_id = ?", (job_id,))
            self.connection.execute("DELETE FROM jobs WHERE id = ?", (job_id,))

    def create_run(
        self,
        *,
        job_id: int,
        trigger_type: str,
        state: RunState,
        started_at_utc: str | None,
        stdout_path: str | None,
        stderr_path: str | None,
        launch_snapshot: dict[str, object],
        run_id: str | None = None,
        error_kind: str | None = None,
        error_summary: str | None = None,
        finished_at_utc: str | None = None,
        exit_code: int | None = None,
        exit_status: str | None = None,
    ) -> Run:
        identifier = run_id or str(uuid.uuid4())
        created = self.now_iso()
        self.connection.execute(
            "INSERT INTO runs(id, job_id, trigger_type, state, started_at_utc, finished_at_utc, "
            "exit_code, exit_status, error_kind, error_summary, stdout_path, stderr_path, "
            "launch_snapshot_json, created_at_utc) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                identifier,
                job_id,
                trigger_type,
                state.value,
                started_at_utc,
                finished_at_utc,
                exit_code,
                exit_status,
                error_kind,
                error_summary,
                stdout_path,
                stderr_path,
                json.dumps(launch_snapshot, ensure_ascii=False, separators=(",", ":")),
                created,
            ),
        )
        self.connection.commit()
        result = self.get_run(identifier)
        assert result is not None
        return result

    def update_run(
        self,
        run_id: str,
        *,
        state: RunState,
        finished_at_utc: str | None = None,
        exit_code: int | None = None,
        exit_status: str | None = None,
        error_kind: str | None = None,
        error_summary: str | None = None,
    ) -> Run:
        self.connection.execute(
            "UPDATE runs SET state = ?, finished_at_utc = ?, exit_code = ?, exit_status = ?, "
            "error_kind = ?, error_summary = ? WHERE id = ?",
            (
                state.value,
                finished_at_utc,
                exit_code,
                exit_status,
                error_kind,
                error_summary,
                run_id,
            ),
        )
        self.connection.commit()
        result = self.get_run(run_id)
        if result is None:
            raise KeyError(run_id)
        return result

    def update_run_launch_snapshot(
        self,
        run_id: str,
        values: dict[str, object],
    ) -> Run:
        """Merge runtime-owned launch metadata into one durable run record."""

        row = self.connection.execute(
            "SELECT launch_snapshot_json FROM runs WHERE id = ?", (run_id,)
        ).fetchone()
        if row is None:
            raise KeyError(run_id)
        try:
            snapshot = json.loads(str(row[0]))
        except (TypeError, ValueError):
            snapshot = {}
        if not isinstance(snapshot, dict):
            snapshot = {}
        snapshot.update(values)
        self.connection.execute(
            "UPDATE runs SET launch_snapshot_json = ? WHERE id = ?",
            (json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")), run_id),
        )
        self.connection.commit()
        result = self.get_run(run_id)
        if result is None:
            raise KeyError(run_id)
        return result

    def get_run(self, run_id: str) -> Run | None:
        row = self.connection.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        return _run_from_row(row) if row else None

    def list_runs(self, job_id: int, limit: int = 50) -> list[Run]:
        rows = self.connection.execute(
            "SELECT * FROM runs WHERE job_id = ? ORDER BY COALESCE(started_at_utc, created_at_utc) DESC LIMIT ?",
            (job_id, limit),
        ).fetchall()
        return [_run_from_row(row) for row in rows]

    def latest_run(self, job_id: int) -> Run | None:
        row = self.connection.execute(
            "SELECT * FROM runs WHERE job_id = ? "
            "ORDER BY COALESCE(started_at_utc, created_at_utc) DESC LIMIT 1",
            (job_id,),
        ).fetchone()
        return _run_from_row(row) if row else None

    def list_all_runs(self) -> list[Run]:
        rows = self.connection.execute(
            "SELECT * FROM runs ORDER BY COALESCE(started_at_utc, created_at_utc) DESC"
        ).fetchall()
        return [_run_from_row(row) for row in rows]

    def recover_incomplete_runs(self) -> list[str]:
        now = self.now_iso()
        rows = self.connection.execute(
            "SELECT id FROM runs WHERE state IN (?, ?)",
            (RunState.STARTING.value, RunState.RUNNING.value),
        ).fetchall()
        if rows:
            self.connection.execute(
                "UPDATE runs SET state = ?, finished_at_utc = ?, error_kind = ?, "
                "error_summary = ? WHERE state IN (?, ?)",
                (
                    RunState.INTERRUPTED.value,
                    now,
                    ErrorKind.INTERRUPTED.value,
                    "Application closed while this run was active.",
                    RunState.STARTING.value,
                    RunState.RUNNING.value,
                ),
            )
            self.connection.commit()
        return [str(row[0]) for row in rows]

    def daily_status(self, job: Job, now: datetime | None = None) -> DailyStatus:
        current = now or self.clock()
        period = period_start_iso(current, job.timezone_id, job.reset_minute)
        row = self.connection.execute(
            "SELECT 1 FROM daily_completions WHERE job_id = ? AND period_start_utc = ?",
            (job.id, period),
        ).fetchone()
        return DailyStatus.COMPLETED if row else DailyStatus.PENDING

    def mark_completed(
        self,
        job: Job,
        *,
        now: datetime | None = None,
        source: str = CompletionSource.MANUAL.value,
        run_id: str | None = None,
    ) -> None:
        current = now or self.clock()
        period = period_start_iso(current, job.timezone_id, job.reset_minute)
        self.connection.execute(
            "INSERT INTO daily_completions(job_id, period_start_utc, completed_at_utc, source, run_id) "
            "VALUES (?, ?, ?, ?, ?) ON CONFLICT(job_id, period_start_utc) DO UPDATE SET "
            "completed_at_utc = excluded.completed_at_utc, source = excluded.source, run_id = excluded.run_id",
            (job.id, period, utc_iso(current), source, run_id),
        )
        self.connection.commit()

    def undo_completed(self, job: Job, *, now: datetime | None = None) -> None:
        current = now or self.clock()
        period = period_start_iso(current, job.timezone_id, job.reset_minute)
        self.connection.execute(
            "DELETE FROM daily_completions WHERE job_id = ? AND period_start_utc = ?",
            (job.id, period),
        )
        self.connection.commit()


def _job_from_row(row: sqlite3.Row) -> Job:
    return Job(
        id=int(row["id"]),
        game_id=int(row["game_id"]),
        game_name=str(row["game_name"]),
        name=str(row["name"]),
        runner_type=str(row["runner_type"]),
        runner_config_version=int(row["runner_config_version"]),
        runner_config_json=str(row["runner_config_json"]),
        enabled=bool(row["enabled"]),
        queue_order=int(row["queue_order"]),
        timezone_id=str(row["timezone_id"]),
        reset_minute=int(row["reset_minute"]),
        created_at_utc=str(row["created_at_utc"]),
        updated_at_utc=str(row["updated_at_utc"]),
    )


def _run_from_row(row: sqlite3.Row) -> Run:
    return Run(
        id=str(row["id"]),
        job_id=int(row["job_id"]),
        trigger_type=str(row["trigger_type"]),
        state=RunState(str(row["state"])),
        started_at_utc=row["started_at_utc"],
        finished_at_utc=row["finished_at_utc"],
        exit_code=row["exit_code"],
        exit_status=row["exit_status"],
        error_kind=row["error_kind"],
        error_summary=row["error_summary"],
        stdout_path=row["stdout_path"],
        stderr_path=row["stderr_path"],
        launch_snapshot_json=str(row["launch_snapshot_json"]),
        created_at_utc=str(row["created_at_utc"]),
    )
