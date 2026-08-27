from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Callable

from .maa_cli import DEFAULT_EMULATOR_START_TIMEOUT_SECONDS
from .maa_preflight import (
    CheckState,
    CheckStep,
    CommandRunner,
    MaaPreflightReport,
    SubprocessCommandRunner,
)
from .maa_punish import find_fos_configuration, read_fos_controller


_FOS_STEPS = (
    ("executable", "FOS program"),
    ("fos_config", "FOS configuration"),
    ("emulator", "Emulator"),
    ("launch", "Launch contract"),
)


def run_fos_preflight(
    config: dict[str, object],
    runner: CommandRunner | None = None,
    sleeper: Callable[[float], None] = time.sleep,
    progress: Callable[[str], None] | None = None,
    poll_interval_seconds: float = 2.0,
) -> MaaPreflightReport:
    command_runner = runner or SubprocessCommandRunner()
    steps: list[CheckStep] = []
    executable_value = config.get("executable_path")
    executable = str(executable_value).strip() if isinstance(executable_value, str) else ""
    fos_path = Path(executable).expanduser() if executable else None
    _notify(progress, "Checking the FOS program…")
    if fos_path is None or not fos_path.is_absolute() or not fos_path.is_file():
        return _failed(steps, "executable", "FOS.exe could not be found.", "Open Edit and choose FOS.exe.", executable)
    steps.append(CheckStep("executable", "FOS program", CheckState.PASSED, f"Found {fos_path.name}."))

    _notify(progress, "Reading the selected FOS configuration…")
    config_id_value = config.get("config_id")
    config_id = str(config_id_value).strip() if isinstance(config_id_value, str) else ""
    selected = find_fos_configuration(fos_path, config_id) if config_id else None
    if selected is None:
        return _failed(
            steps,
            "fos_config",
            "The selected FOS configuration no longer exists.",
            "Open Edit, refresh the configuration list, and choose one configuration.",
            config_id,
        )
    controller = read_fos_controller(selected)
    if controller is None or not controller.controller_type:
        return _failed(
            steps,
            "fos_config",
            "FOS has no usable controller in this configuration.",
            "Open FOS, finish the controller setup, save it, and check again.",
            str(selected.path),
        )
    details = f"{selected.path}\nController: {controller.controller_type}"
    if controller.address:
        details += f"\nAddress: {controller.address}"
    steps.append(
        CheckStep(
            "fos_config",
            "FOS configuration",
            CheckState.PASSED,
            f"Using “{selected.name}” with {controller.controller_type}.",
            details=details,
        )
    )

    emulator_started = False
    if bool(config.get("auto_start_emulator", False)):
        _notify(progress, "Checking the MuMu instance saved for FOS…")
        emulator_step, emulator_started = _prepare_mumu(
            config,
            command_runner,
            sleeper,
            progress,
            poll_interval_seconds,
        )
        steps.append(emulator_step)
        if emulator_step.state == CheckState.FAILED:
            return _with_pending(steps, emulator_started)
    else:
        steps.append(
            CheckStep(
                "emulator",
                "Emulator",
                CheckState.PASSED,
                "Automatic emulator startup is disabled; FOS will use its saved controller.",
            )
        )

    steps.append(
        CheckStep(
            "launch",
            "Launch contract",
            CheckState.PASSED,
            "FOS will run the selected configuration and Control Plane will wait for its task-flow result.",
            details=f"FOS.exe --direct-run --reuse-existing --config-id {config_id}",
        )
    )
    return MaaPreflightReport(tuple(steps), emulator_started=emulator_started, kind="fos")


def _prepare_mumu(
    config: dict[str, object],
    runner: CommandRunner,
    sleeper: Callable[[float], None],
    progress: Callable[[str], None] | None,
    poll_interval_seconds: float,
) -> tuple[CheckStep, bool]:
    executable = str(config.get("emulator_executable_path") or "").strip()
    instance = config.get("emulator_instance_index")
    timeout = config.get("emulator_start_timeout_seconds", DEFAULT_EMULATOR_START_TIMEOUT_SECONDS)
    path = Path(executable).expanduser() if executable else None
    if path is None or not path.is_absolute() or not path.is_file():
        return _emulator_failure("The MuMu command tool could not be found.", "Open Edit and choose mumu-cli.exe.", executable), False
    if isinstance(instance, bool) or not isinstance(instance, int) or instance < 0:
        return _emulator_failure("The MuMu instance number is invalid.", "Open Edit and choose the instance saved in FOS.", str(instance)), False
    if isinstance(timeout, bool) or not isinstance(timeout, int):
        timeout = DEFAULT_EMULATOR_START_TIMEOUT_SECONDS
    timeout = max(30, min(timeout, 600))
    poll_interval_seconds = max(0.1, poll_interval_seconds)

    info = runner.run((executable, "info", "--vmindex", str(instance)), 15)
    payload = _json_object(info.stdout)
    if info.exit_code != 0 or payload is None or _error_code(payload) != 0:
        return _emulator_failure(
            f"MuMu instance {instance} could not be read.",
            "Open MuMu's multi-instance manager and verify the instance number.",
            _result_details(info),
        ), False

    launched_here = False
    if payload.get("is_process_started") is not True:
        _notify(progress, f"Starting MuMu instance {instance}…")
        launch = runner.run((executable, "control", "--vmindex", str(instance), "launch"), 20)
        launch_payload = _json_object(launch.stdout)
        if launch.exit_code != 0 or (launch_payload is not None and _error_code(launch_payload) != 0):
            return _emulator_failure(
                f"MuMu rejected the request to start instance {instance}.",
                "Open this MuMu instance once manually, then check again.",
                _result_details(launch),
            ), False
        launched_here = True

    attempts = max(1, math.ceil(timeout / poll_interval_seconds))
    for attempt in range(1, attempts + 1):
        elapsed = min(timeout, round(attempt * poll_interval_seconds))
        _notify(progress, f"Waiting for MuMu instance {instance} to start Android… {elapsed}/{timeout} seconds")
        sleeper(poll_interval_seconds)
        status = runner.run((executable, "info", "--vmindex", str(instance)), 15)
        status_payload = _json_object(status.stdout)
        if status.exit_code == 0 and status_payload is not None:
            if status_payload.get("is_process_started") is True and status_payload.get("is_android_started") is True:
                summary = (
                    f"Started MuMu instance {instance}."
                    if launched_here
                    else f"MuMu instance {instance} is already running."
                )
                return CheckStep("emulator", "Emulator", CheckState.PASSED, summary, details=status.stdout.strip()), launched_here
    return _emulator_failure(
        f"MuMu instance {instance} did not become ready within {timeout} seconds.",
        "Check the MuMu instance and try again.",
        info.stdout.strip(),
    ), False


def _failed(
    completed: list[CheckStep],
    key: str,
    summary: str,
    action: str,
    details: str = "",
) -> MaaPreflightReport:
    steps = [*completed, CheckStep(key, key, CheckState.FAILED, summary, action, details)]
    return _with_pending(steps, False)


def _with_pending(steps: list[CheckStep], emulator_started: bool) -> MaaPreflightReport:
    completed_keys = {step.key for step in steps}
    values = list(steps)
    for key, title in _FOS_STEPS:
        if key not in completed_keys:
            values.append(CheckStep(key, title, CheckState.PENDING, "Waiting for the previous step."))
    return MaaPreflightReport(tuple(values), emulator_started=emulator_started, kind="fos")


def _emulator_failure(summary: str, action: str, details: str) -> CheckStep:
    return CheckStep("emulator", "Emulator", CheckState.FAILED, summary, action, details)


def _json_object(text: str) -> dict[str, object] | None:
    try:
        value = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None
    return value if isinstance(value, dict) else None


def _error_code(payload: dict[str, object]) -> int:
    value = payload.get("error_code", payload.get("errcode", 0))
    return int(value) if isinstance(value, int) and not isinstance(value, bool) else -1


def _result_details(result) -> str:
    return "\n".join(value for value in (result.error or "", result.stderr.strip(), result.stdout.strip()) if value)


def _notify(progress: Callable[[str], None] | None, message: str) -> None:
    if progress is not None:
        progress(message)


__all__ = ["run_fos_preflight"]
