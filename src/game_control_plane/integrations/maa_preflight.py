from __future__ import annotations

import os
import json
import math
import shutil
import subprocess
import time
import tomllib
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Callable, Protocol, Sequence

from .maa_cli import DEFAULT_EMULATOR_START_TIMEOUT_SECONDS, MUMU_EMULATOR_TYPE
from .maa_managed_task import is_managed_maa_config, write_managed_task


class CheckState(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    PENDING = "pending"


@dataclass(frozen=True)
class CheckStep:
    key: str
    title: str
    state: CheckState
    summary: str
    next_action: str = ""
    details: str = ""


@dataclass(frozen=True)
class MaaPreflightReport:
    steps: tuple[CheckStep, ...]
    emulator_started: bool = False
    kind: str = "maa"

    @property
    def ready(self) -> bool:
        return bool(self.steps) and all(step.state == CheckState.PASSED for step in self.steps)

    @property
    def failed_step(self) -> CheckStep | None:
        return next((step for step in self.steps if step.state == CheckState.FAILED), None)


@dataclass(frozen=True)
class CommandResult:
    exit_code: int | None
    stdout: str = ""
    stderr: str = ""
    error: str | None = None


class CommandRunner(Protocol):
    def run(self, command: Sequence[str], timeout_seconds: float) -> CommandResult:
        ...


class SubprocessCommandRunner:
    def run(self, command: Sequence[str], timeout_seconds: float) -> CommandResult:
        try:
            completed = subprocess.run(
                list(command),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_seconds,
                check=False,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
        except subprocess.TimeoutExpired:
            return CommandResult(None, error=f"The check timed out after {timeout_seconds:g} seconds.")
        except OSError as exc:
            return CommandResult(None, error=str(exc))
        return CommandResult(completed.returncode, completed.stdout, completed.stderr)


_STEP_TITLES = (
    ("executable", "MAA program"),
    ("task", "MAA task"),
    ("dry_run", "Task configuration"),
    ("adb", "Emulator connection"),
)


def run_maa_preflight(
    config: dict[str, object],
    runner: CommandRunner | None = None,
    sleeper: Callable[[float], None] = time.sleep,
    progress: Callable[[str], None] | None = None,
    poll_interval_seconds: float = 2.0,
) -> MaaPreflightReport:
    """Check a MAA job without starting the game or its automation tasks."""

    command_runner = runner or SubprocessCommandRunner()
    steps: list[CheckStep] = []
    executable_value = config.get("executable_path")
    executable = str(executable_value).strip() if isinstance(executable_value, str) else ""
    task_value = config.get("task_name")
    task_name = str(task_value).strip() if isinstance(task_value, str) else ""

    executable_path = Path(executable).expanduser() if executable else None
    if executable_path is None or not executable_path.is_absolute() or not executable_path.is_file():
        return _failed_report(
            steps,
            "executable",
            "MAA program",
            "maa-cli.exe could not be found.",
            "Open Edit, choose the installed maa-cli.exe, save, and try Run again.",
            executable,
        )
    _notify(progress, "Checking the MAA program…")
    version_result = command_runner.run((executable, "--version"), 10)
    if version_result.exit_code != 0:
        return _failed_report(
            steps,
            "executable",
            "MAA program",
            "maa-cli.exe could not be started.",
            "Open Edit and choose a working maa-cli.exe, then try again.",
            _result_details(version_result),
        )
    steps.append(
        CheckStep(
            "executable",
            "MAA program",
            CheckState.PASSED,
            _first_line(version_result.stdout) or "maa-cli.exe is ready.",
        )
    )

    if not task_name:
        return _failed_report(
            steps,
            "task",
            "MAA task",
            "No MAA task is selected.",
            "Open Edit and enter the task name shown by `maa list`.",
        )
    if is_managed_maa_config(config):
        _notify(progress, "Preparing the Control Plane MAA task…")
        config_dir_result = command_runner.run((executable, "dir", "config"), 10)
        config_dir_text = _last_line(config_dir_result.stdout)
        config_dir = Path(config_dir_text) if config_dir_text else None
        if (
            config_dir_result.exit_code != 0
            or config_dir is None
            or not config_dir.is_absolute()
            or not config_dir.is_dir()
        ):
            return _failed_report(
                steps,
                "task",
                "MAA task",
                "MAA's configuration directory could not be prepared.",
                "Run `maa init` once, then select Check again.",
                _result_details(config_dir_result) or config_dir_text,
            )
        try:
            managed_path = write_managed_task(config_dir, config)
        except (OSError, TypeError, ValueError) as exc:
            return _failed_report(
                steps,
                "task",
                "MAA task",
                "Control Plane could not write the managed MAA task.",
                "Check access to MAA's config/tasks directory, then select Check again.",
                str(exc),
            )
    _notify(progress, "Checking the selected MAA task…")
    list_result = command_runner.run((executable, "list"), 15)
    if list_result.exit_code != 0:
        return _failed_report(
            steps,
            "task",
            "MAA task",
            "MAA could not read its task list.",
            "Run `maa init` once, then create or import a task and try again.",
            _result_details(list_result),
        )
    available_tasks = _parse_task_list(list_result.stdout)
    if task_name not in available_tasks:
        available = ", ".join(available_tasks) if available_tasks else "none"
        return _failed_report(
            steps,
            "task",
            "MAA task",
            f"Task '{task_name}' does not exist.",
            f"Open Edit and choose an available task: {available}.",
            list_result.stdout.strip(),
        )
    task_summary = (
        f"Prepared managed task '{task_name}'."
        if is_managed_maa_config(config)
        else f"Task '{task_name}' exists."
    )
    task_details = str(managed_path) if is_managed_maa_config(config) else ""
    steps.append(
        CheckStep(
            "task",
            "MAA task",
            CheckState.PASSED,
            task_summary,
            details=task_details,
        )
    )

    _notify(progress, "Validating the task configuration safely…")
    dry_run_result = command_runner.run(
        (executable, "run", task_name, "--batch", "--dry-run"),
        90,
    )
    if dry_run_result.exit_code != 0:
        return _failed_report(
            steps,
            "dry_run",
            "Task configuration",
            "The task file contains an invalid or incomplete setting.",
            "Fix the first error shown in Details, then select Check again.",
            _result_details(dry_run_result),
        )
    steps.append(
        CheckStep(
            "dry_run",
            "Task configuration",
            CheckState.PASSED,
            "The task file passed MAA's safe dry-run.",
            details=_result_details(dry_run_result),
        )
    )

    _notify(progress, "Checking the emulator connection…")
    adb_step, emulator_started = _check_connection(
        executable,
        command_runner,
        config,
        sleeper,
        progress,
        poll_interval_seconds,
    )
    steps.append(adb_step)
    return MaaPreflightReport(tuple(steps), emulator_started=emulator_started)


def _check_connection(
    executable: str,
    runner: CommandRunner,
    config: dict[str, object],
    sleeper: Callable[[float], None],
    progress: Callable[[str], None] | None,
    poll_interval_seconds: float,
) -> tuple[CheckStep, bool]:
    config_result = runner.run((executable, "dir", "config"), 10)
    if config_result.exit_code != 0:
        return CheckStep(
            "adb",
            "Emulator connection",
            CheckState.FAILED,
            "MAA's connection profile could not be located.",
            "Run `maa init`, finish the connection setup, and select Check again.",
            _result_details(config_result),
        ), False
    config_dir_text = _last_line(config_result.stdout)
    profile_path = Path(config_dir_text) / "profiles" / "default.toml"
    if not profile_path.is_file():
        return CheckStep(
            "adb",
            "Emulator connection",
            CheckState.FAILED,
            "The default MAA connection profile is missing.",
            "Run `maa init` and select your emulator, then select Check again.",
            str(profile_path),
        ), False
    try:
        with profile_path.open("rb") as profile_file:
            profile = tomllib.load(profile_file)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        return CheckStep(
            "adb",
            "Emulator connection",
            CheckState.FAILED,
            "The default MAA connection profile cannot be read.",
            "Correct profiles/default.toml or run `maa init` to recreate it.",
            str(exc),
        ), False
    connection = profile.get("connection")
    if not isinstance(connection, dict):
        return CheckStep(
            "adb",
            "Emulator connection",
            CheckState.FAILED,
            "The MAA profile has no connection settings.",
            "Run `maa init`, select your emulator, and select Check again.",
            str(profile_path),
        ), False
    connection_kind = str(connection.get("type") or connection.get("preset") or "")
    if "playcover" in connection_kind.casefold():
        return CheckStep(
            "adb",
            "Emulator connection",
            CheckState.PASSED,
            "This PlayCover connection will be checked by MAA when the task starts.",
        ), False

    adb_value = connection.get("adb_path") or "adb"
    adb_text = os.path.expandvars(os.path.expanduser(str(adb_value)))
    adb_path = Path(adb_text)
    adb_executable = str(adb_path) if adb_path.is_file() else shutil.which(adb_text)
    if not adb_executable:
        return CheckStep(
            "adb",
            "Emulator connection",
            CheckState.FAILED,
            "The ADB program in the MAA profile could not be found.",
            "Run `maa init` again or correct adb_path in profiles/default.toml.",
            adb_text,
        ), False
    address = str(connection.get("address") or connection.get("device") or "emulator-5554").strip()
    status, connect_details, devices_result, devices = _probe_adb(
        adb_executable,
        address,
        runner,
    )
    if devices_result.exit_code != 0:
        return CheckStep(
            "adb",
            "Emulator connection",
            CheckState.FAILED,
            "ADB could not check the emulator.",
            "Start the emulator, confirm its ADB setting, and select Check again.",
            _join_details(connect_details, _result_details(devices_result)),
        ), False
    if status == "device":
        return CheckStep(
            "adb",
            "Emulator connection",
            CheckState.PASSED,
            f"Emulator connected at {address}.",
            details=_join_details(connect_details, devices_result.stdout.strip()),
        ), False
    if bool(config.get("auto_start_emulator", False)) and status != "unauthorized":
        return _start_mumu_and_wait(
            config,
            runner,
            sleeper,
            progress,
            poll_interval_seconds,
            adb_executable,
            address,
            connect_details,
        )
    if status == "unauthorized":
        summary = f"The emulator at {address} has not authorized ADB."
        action = "Approve the ADB prompt inside the emulator, then select Check again."
    elif status == "offline":
        summary = f"The emulator at {address} is offline."
        action = "Restart the emulator or its ADB option, then select Check again."
    elif devices:
        connected = ", ".join(f"{serial} ({state})" for serial, state in devices.items())
        summary = f"The configured emulator {address} is not connected."
        action = "Correct the address in profiles/default.toml or start the configured instance."
        connect_details = _join_details(connect_details, f"Detected: {connected}")
    else:
        summary = "No emulator is connected to ADB."
        action = "Start the emulator, enable its ADB connection, and select Check again."
    return CheckStep(
        "adb",
        "Emulator connection",
        CheckState.FAILED,
        summary,
        action,
        _join_details(connect_details, devices_result.stdout.strip()),
    ), False


def _start_mumu_and_wait(
    config: dict[str, object],
    runner: CommandRunner,
    sleeper: Callable[[float], None],
    progress: Callable[[str], None] | None,
    poll_interval_seconds: float,
    adb_executable: str,
    address: str,
    initial_details: str,
) -> tuple[CheckStep, bool]:
    emulator_type = config.get("emulator_type", MUMU_EMULATOR_TYPE)
    executable_value = config.get("emulator_executable_path")
    emulator_executable = str(executable_value).strip() if isinstance(executable_value, str) else ""
    instance = config.get("emulator_instance_index")
    timeout = config.get(
        "emulator_start_timeout_seconds",
        DEFAULT_EMULATOR_START_TIMEOUT_SECONDS,
    )
    if emulator_type != MUMU_EMULATOR_TYPE:
        return _emulator_start_failure(
            "This emulator type cannot be started automatically yet.",
            "Open Edit and choose a supported MuMu startup configuration.",
            str(emulator_type),
        ), False
    emulator_path = Path(emulator_executable).expanduser() if emulator_executable else None
    if emulator_path is None or not emulator_path.is_absolute() or not emulator_path.is_file():
        return _emulator_start_failure(
            "The MuMu command tool could not be found.",
            "Open Edit and choose mumu-cli.exe, then select Check again.",
            emulator_executable,
        ), False
    if isinstance(instance, bool) or not isinstance(instance, int) or instance < 0:
        return _emulator_start_failure(
            "The MuMu instance number is invalid.",
            "Open Edit and enter the instance number shown in MuMu's multi-instance manager.",
            str(instance),
        ), False
    if isinstance(timeout, bool) or not isinstance(timeout, int):
        timeout = DEFAULT_EMULATOR_START_TIMEOUT_SECONDS
    timeout = max(1, min(timeout, 600))
    poll_interval_seconds = max(0.1, poll_interval_seconds)

    _notify(progress, f"Checking MuMu instance {instance}…")
    info_result = runner.run(
        (emulator_executable, "info", "--vmindex", str(instance)),
        15,
    )
    if info_result.exit_code != 0:
        return _emulator_start_failure(
            f"MuMu instance {instance} could not be found.",
            "Open Edit and enter the correct MuMu instance number.",
            _result_details(info_result),
        ), False
    info = _json_object(info_result.stdout)
    if info is None or _json_error_code(info) != 0:
        return _emulator_start_failure(
            f"MuMu could not read instance {instance}.",
            "Open MuMu's multi-instance manager and confirm that the instance exists.",
            _result_details(info_result),
        ), False

    details = _join_details(initial_details, info_result.stdout.strip())
    launched_here = False
    if not bool(info.get("is_process_started", False)):
        _notify(progress, f"Starting MuMu instance {instance}…")
        launch_result = runner.run(
            (
                emulator_executable,
                "control",
                "--vmindex",
                str(instance),
                "launch",
            ),
            20,
        )
        launch_payload = _json_object(launch_result.stdout)
        launch_error = _json_error_code(launch_payload) if launch_payload is not None else 0
        details = _join_details(details, _result_details(launch_result))
        if launch_result.exit_code != 0 or launch_error != 0:
            return _emulator_start_failure(
                f"MuMu rejected the request to start instance {instance}.",
                "Open MuMu once manually, check the instance, and try again.",
                details,
            ), False
        launched_here = True

    attempts = max(1, math.ceil(timeout / poll_interval_seconds))
    for attempt in range(1, attempts + 1):
        elapsed = min(timeout, round(attempt * poll_interval_seconds))
        _notify(
            progress,
            f"Waiting for MuMu instance {instance} to connect to ADB… {elapsed}/{timeout} seconds",
        )
        sleeper(poll_interval_seconds)
        status, connect_text, devices_result, _ = _probe_adb(
            adb_executable,
            address,
            runner,
        )
        details = _join_details(details, connect_text, devices_result.stdout.strip())
        if status == "device":
            summary = (
                f"Started MuMu instance {instance} and connected at {address}."
                if launched_here
                else f"MuMu instance {instance} was already running and connected at {address}."
            )
            return CheckStep(
                "adb",
                "Emulator connection",
                CheckState.PASSED,
                summary,
                details=details,
            ), launched_here
        if status == "unauthorized":
            return _emulator_start_failure(
                f"MuMu started, but {address} has not authorized ADB.",
                "Approve the ADB prompt inside MuMu, then select Check again.",
                details,
            ), False
    return _emulator_start_failure(
        f"MuMu instance {instance} did not connect within {timeout} seconds.",
        "Check the instance number, MuMu ADB setting, and MAA profile address, then try again.",
        details,
    ), False


def _probe_adb(
    adb_executable: str,
    address: str,
    runner: CommandRunner,
) -> tuple[str | None, str, CommandResult, dict[str, str]]:
    connect_details = ""
    if ":" in address:
        connect_result = runner.run((adb_executable, "connect", address), 15)
        connect_details = _result_details(connect_result)
    devices_result = runner.run((adb_executable, "devices", "-l"), 15)
    devices = _parse_adb_devices(devices_result.stdout) if devices_result.exit_code == 0 else {}
    return devices.get(address), connect_details, devices_result, devices


def _emulator_start_failure(summary: str, action: str, details: str) -> CheckStep:
    return CheckStep(
        "adb",
        "Emulator connection",
        CheckState.FAILED,
        summary,
        action,
        details,
    )


def _json_object(value: str) -> dict[str, object] | None:
    try:
        parsed = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _json_error_code(value: dict[str, object]) -> int:
    error_value = value.get("errcode", value.get("error_code", 0))
    return int(error_value) if isinstance(error_value, int) and not isinstance(error_value, bool) else -1


def _notify(progress: Callable[[str], None] | None, message: str) -> None:
    if progress is not None:
        progress(message)


def _failed_report(
    completed: list[CheckStep],
    key: str,
    title: str,
    summary: str,
    next_action: str,
    details: str = "",
) -> MaaPreflightReport:
    steps = [*completed, CheckStep(key, title, CheckState.FAILED, summary, next_action, details)]
    completed_keys = {step.key for step in steps}
    for pending_key, pending_title in _STEP_TITLES:
        if pending_key not in completed_keys:
            steps.append(CheckStep(pending_key, pending_title, CheckState.PENDING, "Waiting for the previous step."))
    return MaaPreflightReport(tuple(steps))


def _parse_task_list(output: str) -> tuple[str, ...]:
    return tuple(line.strip() for line in output.splitlines() if line.strip() and not line.lstrip().startswith("["))


def _parse_adb_devices(output: str) -> dict[str, str]:
    devices: dict[str, str] = {}
    for line in output.splitlines():
        fields = line.strip().split()
        if len(fields) >= 2 and fields[0] != "List" and not fields[0].startswith("*"):
            devices[fields[0]] = fields[1]
    return devices


def _result_details(result: CommandResult) -> str:
    return _join_details(result.error or "", result.stderr.strip(), result.stdout.strip())


def _join_details(*values: str) -> str:
    return "\n".join(value for value in values if value)


def _first_line(value: str) -> str:
    return next((line.strip() for line in value.splitlines() if line.strip()), "")


def _last_line(value: str) -> str:
    lines = [line.strip() for line in value.splitlines() if line.strip()]
    return lines[-1] if lines else ""


__all__ = [
    "CheckState",
    "CheckStep",
    "CommandResult",
    "CommandRunner",
    "MaaPreflightReport",
    "SubprocessCommandRunner",
    "run_maa_preflight",
]
