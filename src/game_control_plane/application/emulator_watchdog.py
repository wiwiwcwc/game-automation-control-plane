from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, QTimer, Signal

from ..domain.models import Job
from ..integrations.maa_cli import MAA_CLI_RUNNER_TYPE, MUMU_EMULATOR_TYPE
from ..integrations.maa_punish import MAA_PUNISH_RUNNER_TYPE


DEFAULT_EMULATOR_WATCH_INTERVAL_MS = 2_000
DEFAULT_LOST_CONFIRMATION_COUNT = 2


@dataclass(frozen=True)
class MuMuWatchSpec:
    executable: str
    instance_index: int


class EmulatorWatchdog(QObject):
    """Poll one associated MuMu instance without blocking the Qt UI thread."""

    lost = Signal(str)

    def __init__(
        self,
        spec: MuMuWatchSpec,
        parent: QObject | None = None,
        *,
        interval_ms: int = DEFAULT_EMULATOR_WATCH_INTERVAL_MS,
        lost_confirmation_count: int = DEFAULT_LOST_CONFIRMATION_COUNT,
    ):
        super().__init__(parent)
        self.spec = spec
        self.lost_confirmation_count = max(1, lost_confirmation_count)
        self._consecutive_failures = 0
        self._consecutive_lost = 0
        self._last_lost_reason = ""
        self._lost = False
        self._timer = QTimer(self)
        self._timer.setInterval(max(250, interval_ms))
        self._timer.timeout.connect(self._poll)
        self._probe = QProcess(self)
        self._probe.setProgram(spec.executable)
        self._probe.setArguments(("info", "--vmindex", str(spec.instance_index)))
        self._probe.setStandardInputFile(QProcess.nullDevice())
        self._probe.finished.connect(self._probe_finished)
        self._probe.errorOccurred.connect(self._probe_error)

    def start(self) -> None:
        if self._lost:
            return
        self._timer.start()
        QTimer.singleShot(0, self._poll)

    def stop(self) -> None:
        self._timer.stop()
        if self._probe.state() != QProcess.ProcessState.NotRunning:
            self._probe.kill()

    def _poll(self) -> None:
        if self._lost or self._probe.state() != QProcess.ProcessState.NotRunning:
            return
        self._probe.start()

    def _probe_finished(
        self,
        exit_code: int,
        exit_status: QProcess.ExitStatus,
    ) -> None:
        if self._lost:
            return
        stdout = bytes(self._probe.readAllStandardOutput()).decode("utf-8", errors="replace")
        stderr = bytes(self._probe.readAllStandardError()).decode("utf-8", errors="replace")
        if exit_status == QProcess.ExitStatus.CrashExit or exit_code != 0:
            self._record_probe_failure(stderr.strip() or f"mumu-cli exited with code {exit_code}")
            return
        ready, reason = interpret_mumu_info(stdout, self.spec.instance_index)
        if ready is True:
            self._consecutive_failures = 0
            self._consecutive_lost = 0
            self._last_lost_reason = ""
        elif ready is False:
            self._record_lost(reason)
        else:
            self._record_probe_failure(reason)

    def _probe_error(self, error: QProcess.ProcessError) -> None:
        if self._lost or error != QProcess.ProcessError.FailedToStart:
            return
        self._record_probe_failure(self._probe.errorString() or "mumu-cli could not be started")

    def _record_probe_failure(self, _detail: str) -> None:
        self._consecutive_failures += 1
        self._consecutive_lost = 0
        self._last_lost_reason = ""

    def _record_lost(self, reason: str) -> None:
        self._consecutive_failures = 0
        self._consecutive_lost += 1
        self._last_lost_reason = reason
        if self._consecutive_lost < self.lost_confirmation_count:
            return
        self._report_lost(self._last_lost_reason)

    def _report_lost(self, reason: str) -> None:
        if self._lost:
            return
        self._lost = True
        self._timer.stop()
        self.lost.emit(reason)


def interpret_mumu_info(output: str, instance_index: int) -> tuple[bool | None, str]:
    """Return ready, lost, or unknown for one mumu-cli JSON response."""

    try:
        payload = json.loads(output)
    except (json.JSONDecodeError, TypeError):
        return None, "mumu-cli returned an unreadable status response."
    if not isinstance(payload, dict):
        return None, "mumu-cli returned an unexpected status response."
    error_code = payload.get("error_code", payload.get("errcode", 0))
    if isinstance(error_code, bool) or not isinstance(error_code, int) or error_code != 0:
        return None, f"mumu-cli reported error code {error_code}."
    if payload.get("is_process_started") is not True:
        return (
            False,
            f"MuMu instance {instance_index} was closed. The associated automation was stopped.",
        )
    if payload.get("is_android_started") is not True:
        return (
            False,
            f"Android stopped in MuMu instance {instance_index}. The associated automation was stopped.",
        )
    return True, ""


def create_emulator_watchdog(job: Job, parent: QObject) -> EmulatorWatchdog | None:
    """Create a watcher for supported jobs with an explicit MuMu association."""

    if job.runner_type not in {MAA_CLI_RUNNER_TYPE, MAA_PUNISH_RUNNER_TYPE}:
        return None
    config = job.runner_config
    if not bool(config.get("auto_start_emulator", False)):
        return None
    if config.get("emulator_type", MUMU_EMULATOR_TYPE) != MUMU_EMULATOR_TYPE:
        return None
    executable = config.get("emulator_executable_path")
    instance = config.get("emulator_instance_index")
    if not isinstance(executable, str) or not Path(executable).is_file():
        return None
    if isinstance(instance, bool) or not isinstance(instance, int) or instance < 0:
        return None
    return EmulatorWatchdog(MuMuWatchSpec(executable, instance), parent)


__all__ = [
    "EmulatorWatchdog",
    "MuMuWatchSpec",
    "create_emulator_watchdog",
    "interpret_mumu_info",
]
