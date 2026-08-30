from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from ..domain.models import ErrorKind, Job, Run, RunState
from ..integrations.maa_cli import MAA_CLI_RUNNER_TYPE
from ..integrations.maa_managed_task import is_managed_maa_config
from ..integrations.onedragon import ZZZ_ONEDRAGON_RUNNER_TYPE
from .i18n import LanguageManager, state_text


@dataclass(frozen=True)
class DiagnosticDisplay:
    """The localized primary message and untouched persisted technical detail."""

    summary: str
    technical_detail: str = ""


def _snapshot(run: Run) -> dict[str, Any]:
    try:
        value = json.loads(run.launch_snapshot_json)
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def persisted_runner_type(run: Run, job: Job | None = None) -> str | None:
    snapshot = _snapshot(run)
    value = snapshot.get("runner_type")
    if isinstance(value, str) and value:
        return value
    # If a snapshot already contains runner-owned configuration but predates
    # the runner_type field, do not reinterpret it through today's edited Job.
    if isinstance(snapshot.get("runner_config"), dict):
        return None
    return job.runner_type if job is not None else None


def diagnostic_params(run: Run) -> dict[str, object]:
    value = _snapshot(run).get("diagnostic_params")
    return dict(value) if isinstance(value, dict) else {}


def persisted_diagnostic_code(run: Run, job: Job | None = None) -> str | None:
    """Resolve a run's code from persisted evidence, never current job settings."""

    snapshot = _snapshot(run)
    snapshot_code = snapshot.get("diagnostic_code")
    code = str(run.error_kind or snapshot_code or "") or None
    runner_type = persisted_runner_type(run, job)
    if code is None and run.state == RunState.NEEDS_ATTENTION:
        if runner_type == ZZZ_ONEDRAGON_RUNNER_TYPE and run.exit_code == 0:
            return ErrorKind.ONEDRAGON_UNVERIFIED.value
        config = snapshot.get("runner_config")
        if runner_type == MAA_CLI_RUNNER_TYPE and isinstance(config, dict):
            return (
                ErrorKind.MAA_MANAGED_INCOMPLETE.value
                if is_managed_maa_config(config)
                else ErrorKind.MAA_EXTERNAL_UNVERIFIED.value
            )
    if code != ErrorKind.AUTOMATION_INCOMPLETE.value:
        return code
    if isinstance(snapshot_code, str) and snapshot_code:
        return snapshot_code

    config = snapshot.get("runner_config")
    if runner_type == ZZZ_ONEDRAGON_RUNNER_TYPE and run.state == RunState.NEEDS_ATTENTION:
        return ErrorKind.ONEDRAGON_UNVERIFIED.value
    if runner_type == MAA_CLI_RUNNER_TYPE and isinstance(config, dict):
        return (
            ErrorKind.MAA_MANAGED_INCOMPLETE.value
            if is_managed_maa_config(config)
            else ErrorKind.MAA_EXTERNAL_UNVERIFIED.value
        )
    return code


def run_state_text(
    manager: LanguageManager,
    run: Run,
    job: Job | None = None,
) -> str:
    code = persisted_diagnostic_code(run, job)
    if run.state == RunState.NEEDS_ATTENTION and code == ErrorKind.MAA_EXTERNAL_UNVERIFIED.value:
        return manager.text("state.maa_external_unverified")
    if run.state == RunState.NEEDS_ATTENTION and code == ErrorKind.ONEDRAGON_UNVERIFIED.value:
        return manager.text("state.onedragon_unverified")
    return state_text(manager, run.state.value)


def _join_values(values: object) -> str:
    if isinstance(values, (list, tuple)):
        return ", ".join(str(item) for item in values)
    return str(values)


def format_run_diagnostic(
    manager: LanguageManager,
    run: Run,
    job: Job | None = None,
) -> DiagnosticDisplay:
    """Format a run from stable persisted fields while preserving raw details."""

    code = persisted_diagnostic_code(run, job)
    params = diagnostic_params(run)
    if code == ErrorKind.INVALID_CONFIGURATION.value:
        summary = manager.text("diagnostic.invalid_configuration")
    elif code == ErrorKind.EXECUTABLE_MISSING.value:
        summary = manager.text("diagnostic.executable_missing")
    elif code == ErrorKind.PERMISSION_DENIED.value:
        summary = manager.text("diagnostic.permission_denied")
    elif code == ErrorKind.FAILED_TO_START.value:
        summary = manager.text("diagnostic.failed_to_start")
    elif code == ErrorKind.PROCESS_CRASHED.value:
        summary = manager.text("diagnostic.process_crashed")
    elif code == ErrorKind.NONZERO_EXIT.value:
        summary = manager.text(
            "diagnostic.nonzero_exit",
            code="—" if run.exit_code is None else run.exit_code,
        )
    elif code == ErrorKind.EMULATOR_DISCONNECTED.value:
        instance = params.get("instance")
        if instance is None:
            snapshot_config = _snapshot(run).get("runner_config")
            if isinstance(snapshot_config, dict):
                instance = snapshot_config.get("emulator_instance_index")
        summary = manager.text("diagnostic.emulator_disconnected")
        if instance is not None:
            summary += f" ({instance})"
    elif code == ErrorKind.POST_RUN_ACTION_FAILED.value:
        cleanup_reason = str(params.get("reason", ""))
        cleanup_key = {
            "timeout": "diagnostic.cleanup_timeout",
            "start": "diagnostic.cleanup_start_failed",
            "nonzero": "diagnostic.cleanup_nonzero",
            "crash": "diagnostic.cleanup_crashed",
        }.get(cleanup_reason)
        if cleanup_key == "diagnostic.cleanup_nonzero":
            summary = manager.text(
                cleanup_key,
                code=params.get(
                    "exit_code", run.exit_code if run.exit_code is not None else "—"
                ),
            )
        else:
            summary = (
                manager.text(cleanup_key)
                if cleanup_key
                else manager.text("diagnostic.post_run_action_failed")
            )
    elif code == ErrorKind.MAA_EXTERNAL_UNVERIFIED.value:
        summary = manager.text("run.maa_external_unverified")
    elif code == ErrorKind.MAA_MANAGED_INCOMPLETE.value:
        fragments = [manager.text("diagnostic.maa_managed_incomplete")]
        missing = params.get("missing")
        incomplete = params.get("incomplete")
        if missing:
            fragments.append(manager.text("diagnostic.maa_missing_summary", tasks=_join_values(missing)))
        if incomplete:
            fragments.append(manager.text("diagnostic.maa_unfinished_tasks", tasks=_join_values(incomplete)))
        if params.get("zero_battles"):
            fragments.append(manager.text("diagnostic.maa_zero_battles"))
        if params.get("task_chain_error"):
            fragments.append(manager.text("diagnostic.maa_task_chain_error"))
        summary = " ".join(fragments)
    elif code == ErrorKind.ONEDRAGON_UNVERIFIED.value:
        summary = manager.text("diagnostic.onedragon_unverified")
    elif code == ErrorKind.AUTOMATION_INCOMPLETE.value:
        summary = manager.text("diagnostic.automation_incomplete")
    elif code == ErrorKind.INTERRUPTED.value:
        summary = manager.text("diagnostic.interrupted")
    elif code == ErrorKind.STOP_FAILED.value:
        summary = manager.text("diagnostic.stop_failed")
    elif code == ErrorKind.INTERNAL_ERROR.value:
        summary = manager.text("diagnostic.internal_error")
    elif code:
        summary = manager.text("diagnostic.unknown")
    elif run.state == RunState.NEEDS_ATTENTION:
        summary = manager.text("diagnostic.unknown")
    else:
        summary = ""
    return DiagnosticDisplay(summary=summary, technical_detail=run.error_summary or "")


__all__ = [
    "DiagnosticDisplay",
    "diagnostic_params",
    "format_run_diagnostic",
    "persisted_diagnostic_code",
    "persisted_runner_type",
    "run_state_text",
]
