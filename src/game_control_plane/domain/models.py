from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class RunState(StrEnum):
    STARTING = "starting"
    RUNNING = "running"
    EXITED = "exited"
    FAILED = "failed"
    NEEDS_ATTENTION = "needs_attention"
    INTERRUPTED = "interrupted"


class TriggerType(StrEnum):
    MANUAL = "manual"
    QUEUE = "queue"


class ExitStatus(StrEnum):
    NORMAL = "normal"
    CRASH = "crash"


class ErrorKind(StrEnum):
    INVALID_CONFIGURATION = "invalid_configuration"
    EXECUTABLE_MISSING = "executable_missing"
    FAILED_TO_START = "failed_to_start"
    PERMISSION_DENIED = "permission_denied"
    PROCESS_CRASHED = "process_crashed"
    NONZERO_EXIT = "nonzero_exit"
    EMULATOR_DISCONNECTED = "emulator_disconnected"
    POST_RUN_ACTION_FAILED = "post_run_action_failed"
    AUTOMATION_INCOMPLETE = "automation_incomplete"
    MAA_EXTERNAL_UNVERIFIED = "maa_external_unverified"
    INTERRUPTED = "interrupted"
    STOP_FAILED = "stop_failed"
    INTERNAL_ERROR = "internal_error"


class CompletionSource(StrEnum):
    MANUAL = "manual"


class DailyStatus(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"


@dataclass(frozen=True)
class Game:
    id: int | None
    name: str
    created_at_utc: str | None = None
    updated_at_utc: str | None = None


@dataclass(frozen=True)
class Job:
    id: int | None
    game_id: int | None
    game_name: str
    name: str
    runner_type: str
    runner_config_version: int
    runner_config_json: str
    enabled: bool
    queue_order: int
    timezone_id: str
    reset_minute: int
    created_at_utc: str | None = None
    updated_at_utc: str | None = None

    @property
    def runner_config(self) -> dict[str, Any]:
        import json

        value = json.loads(self.runner_config_json)
        return value if isinstance(value, dict) else {}


@dataclass(frozen=True)
class Run:
    id: str
    job_id: int
    trigger_type: str
    state: RunState
    started_at_utc: str | None
    finished_at_utc: str | None
    exit_code: int | None
    exit_status: str | None
    error_kind: str | None
    error_summary: str | None
    stdout_path: str | None
    stderr_path: str | None
    launch_snapshot_json: str
    created_at_utc: str

    @property
    def duration_seconds(self) -> float | None:
        if not self.started_at_utc or not self.finished_at_utc:
            return None
        from datetime import datetime

        try:
            start = datetime.fromisoformat(self.started_at_utc)
            finish = datetime.fromisoformat(self.finished_at_utc)
        except ValueError:
            return None
        return max(0.0, (finish - start).total_seconds())
