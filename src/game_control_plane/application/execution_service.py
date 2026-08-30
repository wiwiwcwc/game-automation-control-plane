from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, QProcess, QTimer, Signal

from ..domain.models import ErrorKind, ExitStatus, Job, Run, RunState, TriggerType
from ..integrations.base import LaunchSpec
from ..integrations.registry import IntegrationRegistry, default_registry
from ..persistence.store import Store
from .emulator_watchdog import EmulatorWatchdog, create_emulator_watchdog
from .maa_result_audit import RunResultAssessment, assess_run_result
from .process_handoff import (
    DEFAULT_HANDOFF_GRACE_SECONDS,
    DEFAULT_HANDOFF_POLL_INTERVAL_MS,
    HandoffCoordinator,
    HandoffTracker,
    ProcessOutcome,
    WorkerLocator,
    default_worker_locator,
)
from .process_supervisor import (
    ProcessIdentity,
    ProcessSupervisor,
    default_process_supervisor,
    process_identity_dict,
)
from .post_run_actions import PostRunAction, create_post_run_action, mumu_resource_key


@dataclass
class _ActiveProcess:
    job: Job
    run: Run
    process: QProcess
    stdout_file: object
    stderr_file: object
    started_monotonic: float
    handoff_spec: LaunchSpec | None = None
    handoff: HandoffCoordinator | None = None
    emulator_watchdog: EmulatorWatchdog | None = None
    post_run_action: PostRunAction | None = None
    post_run_action_started: bool = False
    resource_key: tuple[str, str, int] | None = None
    error_message: str | None = None
    forced_error_summary: str | None = None
    expected_executable: str | None = None
    process_identity: ProcessIdentity | None = None
    stop_requested: bool = False
    stop_reason: str | None = None
    stop_failure_summary: str | None = None
    finalized: bool = False


class ExecutionService(QObject):
    """Owns asynchronous job processes and persists every state transition."""

    run_started = Signal(str)
    output_received = Signal(str, str, bytes)
    run_finished = Signal(str)

    def __init__(
        self,
        store: Store,
        runs_dir: str | Path,
        registry: IntegrationRegistry | None = None,
        logger: logging.Logger | None = None,
        parent: QObject | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        handoff_locator: WorkerLocator | None = None,
        handoff_grace_seconds: float = DEFAULT_HANDOFF_GRACE_SECONDS,
        handoff_poll_interval_ms: int = DEFAULT_HANDOFF_POLL_INTERVAL_MS,
        emulator_watchdog_factory: Callable[
            [Job, QObject], EmulatorWatchdog | None
        ] = create_emulator_watchdog,
        emulator_stop_grace_ms: int = 3_000,
        post_run_action_factory: Callable[
            [Job, dict[str, object] | None], PostRunAction | None
        ] = create_post_run_action,
        post_run_action_timeout_ms: int = 20_000,
        result_auditor: Callable[
            [Job, str | Path, str | Path], RunResultAssessment
        ] = assess_run_result,
        process_supervisor: ProcessSupervisor | None = None,
        stop_grace_ms: int = 3_000,
        summary_text: Callable[..., str] | None = None,
    ):
        super().__init__(parent)
        self.store = store
        self.runs_dir = Path(runs_dir)
        self.registry = registry or default_registry()
        self.logger = logger or logging.getLogger("game_control_plane.execution")
        self.monotonic = monotonic
        self.handoff_locator = (
            handoff_locator if handoff_locator is not None else default_worker_locator()
        )
        self.handoff_grace_seconds = handoff_grace_seconds
        self.emulator_watchdog_factory = emulator_watchdog_factory
        self.emulator_stop_grace_ms = max(0, emulator_stop_grace_ms)
        self.post_run_action_factory = post_run_action_factory
        self.post_run_action_timeout_ms = max(1, post_run_action_timeout_ms)
        self.result_auditor = result_auditor
        self.process_supervisor = process_supervisor or default_process_supervisor()
        self.stop_grace_ms = max(0, stop_grace_ms)
        self.summary_text = summary_text
        self._accepting_runs = True
        self._handoff_timer = QTimer(self)
        self._handoff_timer.setInterval(handoff_poll_interval_ms)
        self._handoff_timer.timeout.connect(self._poll_handoff)
        self._active: dict[str, _ActiveProcess] = {}

    def _summary(self, key: str, **values: object) -> str:
        """Resolve user-visible lifecycle summaries through the UI locale."""

        if self.summary_text is None:
            return key
        try:
            return self.summary_text(key, **values)
        except Exception:
            self.logger.exception("Could not localize execution summary %s", key)
            return key

    def _localize_assessment(self, assessment: RunResultAssessment) -> RunResultAssessment:
        if assessment.localization_key is None or self.summary_text is None:
            return assessment
        return replace(
            assessment,
            summary=self._summary(assessment.localization_key),
        )

    def _localize_watchdog_summary(self, summary: str) -> str:
        """Translate the two built-in MuMu loss summaries for the UI locale."""

        if self.summary_text is None:
            return summary
        closed = re.fullmatch(
            r"MuMu instance (\d+) was closed\. The associated automation was stopped\.",
            summary,
        )
        if closed:
            return self._summary("run.emulator_closed", instance=closed.group(1))
        android = re.fullmatch(
            r"Android stopped in MuMu instance (\d+)\. The associated automation was stopped\.",
            summary,
        )
        if android:
            return self._summary("run.android_stopped", instance=android.group(1))
        return summary

    @property
    def active_run(self) -> Run | None:
        return next((active.run for active in self._active.values()), None)

    @property
    def active_runs(self) -> tuple[Run, ...]:
        return tuple(active.run for active in self._active.values())

    @property
    def active_job_ids(self) -> frozenset[int]:
        return frozenset(active.run.job_id for active in self._active.values())

    @property
    def is_running(self) -> bool:
        return bool(self._active)

    def is_job_running(self, job_id: int) -> bool:
        return job_id in self.active_job_ids

    @property
    def accepting_runs(self) -> bool:
        return self._accepting_runs

    def set_accepting_runs(self, accepting: bool) -> None:
        """Reject new starts while an orderly application shutdown is pending."""

        self._accepting_runs = bool(accepting)

    def start(
        self,
        job: Job,
        trigger_type: str = TriggerType.MANUAL.value,
        runtime_context: dict[str, object] | None = None,
    ) -> Run:
        if not self._accepting_runs:
            raise RuntimeError("the application is closing")
        if job.id is not None and self.is_job_running(int(job.id)):
            raise RuntimeError("this automation is already running")
        resource_key = mumu_resource_key(job)
        if resource_key is not None and any(
            active.resource_key == resource_key for active in self._active.values()
        ):
            raise RuntimeError("this MuMu instance is already being used by another automation")
        run_id = self._new_run_id()
        run_dir = self.runs_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        stdout_path = run_dir / "stdout.log"
        stderr_path = run_dir / "stderr.log"
        launch_snapshot: dict[str, object] = {
            "job_id": job.id,
            "job_name": job.name,
            "game_name": job.game_name,
            "runner_type": job.runner_type,
            "runner_config_version": job.runner_config_version,
            "runner_config": job.runner_config,
        }
        if runtime_context:
            launch_snapshot["runtime_context"] = dict(runtime_context)
        try:
            integration = self.registry.get(job.runner_type)
            validation = integration.validate_config(job.runner_config)
            if not validation.valid:
                summary = " ".join(validation.errors)
                run = self.store.create_run(
                    job_id=int(job.id),
                    trigger_type=trigger_type,
                    state=RunState.FAILED,
                    started_at_utc=self.store.now_iso(),
                    finished_at_utc=self.store.now_iso(),
                    error_kind=ErrorKind.INVALID_CONFIGURATION.value,
                    error_summary=summary,
                    stdout_path=str(stdout_path),
                    stderr_path=str(stderr_path),
                    launch_snapshot=launch_snapshot,
                    run_id=run_id,
                )
                stdout_path.touch(exist_ok=True)
                stderr_path.touch(exist_ok=True)
                self._write_metadata(run)
                QTimer.singleShot(0, lambda: self.run_finished.emit(run.id))
                return run
            spec = integration.build_launch_spec(job)
            emulator_watchdog = self.emulator_watchdog_factory(job, self)
            post_run_action = self.post_run_action_factory(job, runtime_context)
        except ValueError as exc:
            run = self.store.create_run(
                job_id=int(job.id),
                trigger_type=trigger_type,
                state=RunState.FAILED,
                started_at_utc=self.store.now_iso(),
                finished_at_utc=self.store.now_iso(),
                error_kind=ErrorKind.INVALID_CONFIGURATION.value,
                error_summary=str(exc),
                stdout_path=str(stdout_path),
                stderr_path=str(stderr_path),
                launch_snapshot=launch_snapshot,
                run_id=run_id,
            )
            stdout_path.touch(exist_ok=True)
            stderr_path.touch(exist_ok=True)
            self._write_metadata(run)
            QTimer.singleShot(0, lambda: self.run_finished.emit(run.id))
            return run
        except Exception as exc:  # pragma: no cover - defensive boundary
            self.logger.exception("Could not construct launch spec for job %s", job.id)
            run = self.store.create_run(
                job_id=int(job.id),
                trigger_type=trigger_type,
                state=RunState.FAILED,
                started_at_utc=self.store.now_iso(),
                finished_at_utc=self.store.now_iso(),
                error_kind=ErrorKind.INTERNAL_ERROR.value,
                error_summary=str(exc),
                stdout_path=str(stdout_path),
                stderr_path=str(stderr_path),
                launch_snapshot=launch_snapshot,
                run_id=run_id,
            )
            stdout_path.touch(exist_ok=True)
            stderr_path.touch(exist_ok=True)
            self._write_metadata(run)
            QTimer.singleShot(0, lambda: self.run_finished.emit(run.id))
            return run

        run = self.store.create_run(
            job_id=int(job.id),
            trigger_type=trigger_type,
            state=RunState.STARTING,
            started_at_utc=self.store.now_iso(),
            stdout_path=str(stdout_path),
            stderr_path=str(stderr_path),
            launch_snapshot={**launch_snapshot, "launch_spec": _spec_dict(spec)},
            run_id=run_id,
        )
        stdout_file = stdout_path.open("ab")
        stderr_file = stderr_path.open("ab")
        process = QProcess(self)
        process.setProgram(spec.executable)
        process.setArguments(list(spec.arguments))
        if spec.working_directory:
            process.setWorkingDirectory(spec.working_directory)
        # Automation jobs are non-interactive. Supplying EOF prevents a CLI
        # from waiting forever for input that this UI cannot provide.
        process.setStandardInputFile(QProcess.nullDevice())
        active = _ActiveProcess(
            job=job,
            run=run,
            process=process,
            stdout_file=stdout_file,
            stderr_file=stderr_file,
            started_monotonic=self.monotonic(),
            handoff_spec=spec if spec.handoff_process_names else None,
            emulator_watchdog=emulator_watchdog,
            post_run_action=post_run_action,
            resource_key=resource_key,
            expected_executable=spec.executable,
        )
        self._active[run.id] = active
        if active.emulator_watchdog is not None:
            active.emulator_watchdog.lost.connect(
                lambda summary: self._on_emulator_lost(run.id, summary)
            )
        process.started.connect(lambda: self._on_started(run.id))
        process.readyReadStandardOutput.connect(lambda: self._on_output(run.id, "stdout"))
        process.readyReadStandardError.connect(lambda: self._on_output(run.id, "stderr"))
        process.errorOccurred.connect(lambda error: self._on_error(run.id, error))
        process.finished.connect(lambda code, status: self._on_finished(run.id, code, status))
        self._write_metadata(run)
        self.logger.info("Starting run %s for job %s: %s", run.id, job.id, spec.display_command)
        process.start()
        return run

    def _new_run_id(self) -> str:
        import uuid

        return str(uuid.uuid4())

    def _on_started(self, run_id: str) -> None:
        active = self._get_active(run_id)
        if active is None or active.finalized:
            return
        run = self.store.update_run(run_id, state=RunState.RUNNING)
        active.run = run
        self._write_metadata(run)
        self._capture_process_identity(active)
        if active.handoff_spec is not None:
            launcher_pid = int(active.process.processId())
            if launcher_pid > 0:
                active.handoff = HandoffCoordinator(
                    HandoffTracker(
                        self.handoff_locator,
                        launcher_pid,
                        active.handoff_spec.executable,
                        active.handoff_spec.handoff_process_names,
                    ),
                    self.handoff_grace_seconds,
                )
                self._handoff_timer.start()
                self._poll_handoff()
        if active.emulator_watchdog is not None:
            active.emulator_watchdog.start()
        self.run_started.emit(run_id)
        if active.stop_requested:
            self._request_graceful_stop(active)

    def _capture_process_identity(self, active: _ActiveProcess) -> None:
        if active.expected_executable is None:
            return
        try:
            pid = int(active.process.processId())
        except (RuntimeError, TypeError, ValueError):
            pid = 0
        if pid <= 0:
            return
        try:
            identity = self.process_supervisor.capture(pid, active.expected_executable)
        except Exception:
            self.logger.exception("Could not inspect process identity for run %s", active.run.id)
            identity = None
        active.process_identity = identity
        process_snapshot: dict[str, object] = {
            "pid": pid,
            "expected_executable": active.expected_executable,
            "verified": identity is not None,
        }
        if identity is not None:
            process_snapshot.update(process_identity_dict(identity))
        else:
            self.logger.warning(
                "Could not verify the launcher image for run %s; exact stop will be refused",
                active.run.id,
            )
        try:
            active.run = self.store.update_run_launch_snapshot(
                active.run.id,
                {
                    "owned_process": process_snapshot,
                    "root_pid": pid,
                    "root_executable": active.expected_executable,
                    "root_process_token": identity.token if identity is not None else None,
                },
            )
            self._write_metadata(active.run)
        except Exception:
            self.logger.exception("Could not persist process identity for run %s", active.run.id)

    def stop(self, run_id: str, reason: str | None = None) -> bool:
        """Stop one exact active run without claiming success or completion."""

        active = self._get_active(run_id)
        if active is None or active.finalized:
            return False
        if active.stop_requested:
            return True
        active.stop_requested = True
        active.stop_reason = reason or self._summary("run.stop_requested")
        self.logger.warning("Stopping run %s: %s", run_id, active.stop_reason)
        state = active.process.state()
        if state == QProcess.ProcessState.NotRunning:
            QTimer.singleShot(0, lambda identifier=run_id: self._finalize_stopped(identifier))
        elif state == QProcess.ProcessState.Starting:
            # The started signal captures and verifies the PID before asking
            # the process to stop. A short timer covers a launcher that never
            # reaches Running and lets the close-event timeout record failure.
            QTimer.singleShot(
                self.stop_grace_ms,
                lambda identifier=run_id: self._force_stop_after_grace(identifier),
            )
        else:
            self._request_graceful_stop(active)
            QTimer.singleShot(
                self.stop_grace_ms,
                lambda identifier=run_id: self._force_stop_after_grace(identifier),
            )
        return True

    def stop_all(self, reason: str | None = None) -> tuple[str, ...]:
        identifiers = tuple(active.run.id for active in self._active.values())
        for identifier in identifiers:
            self.stop(identifier, reason=reason)
        return identifiers

    def force_finalize_stop_timeout(self, run_id: str, summary: str | None = None) -> bool:
        """Persist a stop timeout so orderly application shutdown can finish."""

        active = self._get_active(run_id)
        if active is None or active.finalized or not active.stop_requested:
            return False
        active.stop_failure_summary = summary or self._summary(
            "run.stop_application_timeout"
        )
        self._finalize_stopped(run_id)
        return True

    def _request_graceful_stop(self, active: _ActiveProcess) -> None:
        if active.finalized:
            return
        try:
            if active.process.state() != QProcess.ProcessState.NotRunning:
                active.process.terminate()
        except RuntimeError as exc:
            active.stop_failure_summary = self._summary(
                "run.stop_graceful_request_failed", error=str(exc)
            )

    def _force_stop_after_grace(self, run_id: str) -> None:
        active = self._get_active(run_id)
        if active is None or active.finalized or not active.stop_requested:
            return
        state = active.process.state()
        if state == QProcess.ProcessState.NotRunning:
            self._finalize_stopped(run_id)
            return
        if state == QProcess.ProcessState.Starting:
            active.stop_failure_summary = self._summary(
                "run.stop_start_timeout"
            )
            self._finalize_stopped(run_id)
            return
        identity = active.process_identity
        try:
            current_pid = int(active.process.processId())
        except (RuntimeError, TypeError, ValueError):
            current_pid = 0
        if identity is None or current_pid != identity.pid:
            active.stop_failure_summary = self._summary(
                "run.stop_identity_missing"
            )
            self._finalize_stopped(run_id)
            return
        try:
            verified = self.process_supervisor.verify(identity)
        except Exception:
            self.logger.exception("Could not revalidate process identity for run %s", run_id)
            verified = False
        if not verified:
            active.stop_failure_summary = self._summary(
                "run.stop_identity_changed"
            )
            self._finalize_stopped(run_id)
            return
        try:
            result = self.process_supervisor.terminate_tree(identity)
        except Exception as exc:  # pragma: no cover - defensive platform boundary
            self.logger.exception("Could not terminate owned process tree for run %s", run_id)
            result = None
            active.stop_failure_summary = self._summary(
                "run.stop_tree_exception", error=str(exc)
            )
        if result is not None and result.success:
            self.logger.info(
                "Force-stopped owned process tree for run %s: %s",
                run_id,
                result.attempted_pids,
            )
            # Keep Qt's QProcess state in sync with the native termination.
            # This targets the same verified root PID, never an image name.
            try:
                if active.process.state() != QProcess.ProcessState.NotRunning:
                    active.process.kill()
            except RuntimeError as exc:
                active.stop_failure_summary = self._summary(
                    "run.stop_qprocess_failed", error=str(exc)
                )
        elif result is not None:
            active.stop_failure_summary = self._summary(
                "run.stop_tree_failed",
                summary=result.summary
                or self._summary("run.stop_tree_failed_detail"),
            )
            # A failed native tree validation is deliberately fail-closed.
            # Do not fall back to QProcess.kill after a child/token/parent
            # anomaly; that would partially terminate a tree the supervisor
            # explicitly refused to prove.  The exact failure remains visible
            # and the shutdown timer will finalize the run as STOP_FAILED.
        if active.stop_failure_summary is not None and active.process.state() == QProcess.ProcessState.NotRunning:
            self._finalize_stopped(run_id)
            return
        QTimer.singleShot(
            self.stop_grace_ms,
            lambda identifier=run_id: self._stop_timeout(identifier),
        )

    def _stop_timeout(self, run_id: str) -> None:
        active = self._get_active(run_id)
        if active is None or active.finalized or not active.stop_requested:
            return
        if active.process.state() == QProcess.ProcessState.NotRunning:
            self._finalize_stopped(run_id)
            return
        if active.stop_failure_summary is None:
            active.stop_failure_summary = self._summary(
                "run.stop_timeout"
            )
        self._finalize_stopped(run_id)

    def _finalize_stopped(self, run_id: str) -> None:
        active = self._get_active(run_id)
        if active is None or active.finalized or not active.stop_requested:
            return
        if active.stop_failure_summary is not None:
            summary = active.stop_failure_summary
            self._finalize(
                run_id,
                state=RunState.FAILED,
                error_kind=ErrorKind.STOP_FAILED.value,
                error_summary=summary,
            )
            return
        self._finalize(
            run_id,
            state=RunState.INTERRUPTED,
            error_kind=ErrorKind.INTERRUPTED.value,
            error_summary=active.stop_reason
            or self._summary("run.stop_before_completion"),
        )

    def _on_output(self, run_id: str, stream: str) -> None:
        active = self._get_active(run_id)
        if active is None or active.finalized:
            return
        process = active.process
        try:
            data = bytes(
                process.readAllStandardOutput()
                if stream == "stdout"
                else process.readAllStandardError()
            )
        except RuntimeError:
            # The window can be closing while Qt delivers a final queued
            # signal. The durable run has already been finalized in that case.
            self.logger.debug("QProcess was deleted before draining %s", stream)
            return
        if not data:
            return
        target = active.stdout_file if stream == "stdout" else active.stderr_file
        target.write(data)
        target.flush()
        self.output_received.emit(run_id, stream, data)

    def _on_error(self, run_id: str, error: QProcess.ProcessError) -> None:
        active = self._get_active(run_id)
        if active is None or active.finalized:
            return
        try:
            message = active.process.errorString() or str(error)
        except RuntimeError:
            message = str(error)
        active.error_message = message
        self.logger.warning("QProcess error for run %s: %s", run_id, message)
        if error == QProcess.ProcessError.FailedToStart:
            if active.stop_requested:
                active.stop_reason = active.stop_reason or self._summary(
                    "run.stop_before_start"
                )
                self._finalize_stopped(run_id)
                return
            self._finalize(
                run_id,
                state=RunState.FAILED,
                error_kind=ErrorKind.FAILED_TO_START.value,
                error_summary=message,
            )

    def _on_finished(self, run_id: str, exit_code: int, exit_status: QProcess.ExitStatus) -> None:
        active = self._get_active(run_id)
        if active is None or active.finalized:
            return
        self._on_output(run_id, "stdout")
        self._on_output(run_id, "stderr")
        if active.stop_requested:
            self._finalize_stopped(run_id)
            return
        if active.forced_error_summary is not None:
            self._finalize(
                run_id,
                state=RunState.FAILED,
                exit_code=exit_code,
                exit_status=(
                    ExitStatus.CRASH.value
                    if exit_status == QProcess.ExitStatus.CrashExit
                    else ExitStatus.NORMAL.value
                ),
                error_kind=ErrorKind.EMULATOR_DISCONNECTED.value,
                error_summary=active.forced_error_summary,
            )
            return
        parent_outcome = ProcessOutcome(
            exit_code=exit_code,
            crashed=exit_status == QProcess.ExitStatus.CrashExit,
            error_message=active.error_message,
        )
        if active.handoff is not None:
            try:
                decision = active.handoff.parent_finished(parent_outcome, self.monotonic())
            except Exception:
                self.logger.exception("Could not monitor the OK-WW worker process")
                active.handoff.close()
                active.handoff = None
                decision = parent_outcome
            if decision is None:
                self._handoff_timer.start()
                return
            self._finalize_process_outcome(
                run_id,
                decision,
                worker=active.handoff.tracker.worker_exit_code is not None
                if active.handoff is not None
                else False,
            )
            return
        self._finalize_process_outcome(run_id, parent_outcome)

    def _on_emulator_lost(self, run_id: str, summary: str) -> None:
        active = self._get_active(run_id)
        if active is None or active.finalized or active.forced_error_summary is not None:
            return
        active.forced_error_summary = self._localize_watchdog_summary(summary)
        self.logger.warning("Stopping run %s because its emulator was lost: %s", run_id, summary)
        if active.process.state() != QProcess.ProcessState.NotRunning:
            active.process.terminate()
            QTimer.singleShot(
                self.emulator_stop_grace_ms,
                lambda identifier=run_id: self._kill_after_emulator_loss(identifier),
            )

    def _kill_after_emulator_loss(self, run_id: str) -> None:
        active = self._get_active(run_id)
        if (
            active is None
            or active.finalized
            or active.forced_error_summary is None
            or active.process.state() == QProcess.ProcessState.NotRunning
        ):
            return
        self.logger.warning("Force-stopping run %s after its emulator closed", run_id)
        active.process.kill()

    def _poll_handoff(self) -> None:
        handoffs_active = False
        for active in tuple(self._active.values()):
            if active.finalized or active.handoff is None:
                continue
            handoffs_active = True
            try:
                decision = active.handoff.poll(self.monotonic())
            except Exception:
                self.logger.exception("Could not monitor the OK-WW worker process")
                parent_outcome = active.handoff.parent_outcome
                active.handoff.close()
                active.handoff = None
                if parent_outcome is not None:
                    self._finalize_process_outcome(run_id=active.run.id, outcome=parent_outcome)
                continue
            if decision is None:
                continue
            worker = active.handoff.tracker.worker_exit_code is not None
            self._finalize_process_outcome(active.run.id, decision, worker=worker)
        if not handoffs_active or not any(
            active.handoff is not None and not active.finalized
            for active in self._active.values()
        ):
            self._handoff_timer.stop()

    def _finalize_process_outcome(
        self,
        run_id: str,
        outcome: ProcessOutcome,
        *,
        worker: bool = False,
    ) -> None:
        active = self._get_active(run_id)
        if active is None or active.finalized:
            return
        if outcome.crashed:
            self._finalize(
                run_id,
                state=RunState.FAILED,
                exit_code=outcome.exit_code,
                exit_status=ExitStatus.CRASH.value,
                error_kind=ErrorKind.PROCESS_CRASHED.value,
                error_summary=outcome.error_message or "The process crashed.",
            )
        elif outcome.exit_code == 0:
            try:
                assessment = self._localize_assessment(
                    self.result_auditor(
                        active.job,
                        active.run.stdout_path or "",
                        active.run.stderr_path or "",
                    )
                )
            except Exception:
                self.logger.exception("Could not verify automation result for run %s", run_id)
                assessment = RunResultAssessment(
                    needs_attention=True,
                    summary=(
                        "Hsiesta could not verify the automation result. "
                        "The emulator was left open."
                    ),
                )
            if assessment.needs_attention:
                banner = f"\n[Hsiesta] {assessment.summary}\n".encode("utf-8")
                active.stderr_file.write(banner)
                active.stderr_file.flush()
                self._finalize(
                    run_id,
                    state=RunState.NEEDS_ATTENTION,
                    exit_code=outcome.exit_code,
                    exit_status=ExitStatus.NORMAL.value,
                    error_kind=(
                        assessment.diagnostic_code
                        or ErrorKind.AUTOMATION_INCOMPLETE.value
                    ),
                    error_summary=assessment.summary,
                )
                return
            if active.post_run_action is not None and not active.post_run_action_started:
                self._start_post_run_action(run_id)
            else:
                self._finalize(
                    run_id,
                    state=RunState.EXITED,
                    exit_code=outcome.exit_code,
                    exit_status=ExitStatus.NORMAL.value,
                )
        else:
            subject = "OK-WW worker" if worker else "The process"
            self._finalize(
                run_id,
                state=RunState.FAILED,
                exit_code=outcome.exit_code,
                exit_status=ExitStatus.NORMAL.value,
                error_kind=ErrorKind.NONZERO_EXIT.value,
                error_summary=f"{subject} exited with code {outcome.exit_code}.",
            )

    def _start_post_run_action(self, run_id: str) -> None:
        active = self._get_active(run_id)
        if active is None or active.finalized or active.post_run_action is None:
            return
        action = active.post_run_action
        active.post_run_action_started = True
        if active.emulator_watchdog is not None:
            active.emulator_watchdog.stop()
            active.emulator_watchdog.deleteLater()
            active.emulator_watchdog = None
        if active.handoff is not None:
            active.handoff.close()
            active.handoff = None
        previous_process = active.process
        process = QProcess(self)
        process.setProgram(action.executable)
        process.setArguments(list(action.arguments))
        process.setStandardInputFile(QProcess.nullDevice())
        active.process = process
        active.expected_executable = action.executable
        active.process_identity = None
        banner = f"\n[Hsiesta] {action.description}: {action.display_command}\n".encode()
        active.stdout_file.write(banner)
        active.stdout_file.flush()
        process.started.connect(lambda: self._capture_process_identity(active))
        process.readyReadStandardOutput.connect(lambda: self._on_output(run_id, "stdout"))
        process.readyReadStandardError.connect(lambda: self._on_output(run_id, "stderr"))
        process.errorOccurred.connect(lambda error: self._on_post_run_action_error(run_id, error))
        process.finished.connect(
            lambda code, status: self._on_post_run_action_finished(run_id, code, status)
        )
        previous_process.deleteLater()
        self.logger.info("Starting post-run action for %s: %s", run_id, action.display_command)
        process.start()
        QTimer.singleShot(
            self.post_run_action_timeout_ms,
            lambda identifier=run_id: self._on_post_run_action_timeout(identifier),
        )

    def _on_post_run_action_timeout(self, run_id: str) -> None:
        active = self._get_active(run_id)
        if (
            active is None
            or active.finalized
            or not active.post_run_action_started
            or active.process.state() == QProcess.ProcessState.NotRunning
        ):
            return
        description = active.post_run_action.description if active.post_run_action else "Post-run action"
        active.process.kill()
        self._finalize(
            run_id,
            state=RunState.EXITED,
            exit_code=0,
            exit_status=ExitStatus.NORMAL.value,
            error_kind=ErrorKind.POST_RUN_ACTION_FAILED.value,
            error_summary=(
                f"The automation succeeded, but {description.lower()} timed out."
            ),
        )

    def _on_post_run_action_error(self, run_id: str, error: QProcess.ProcessError) -> None:
        active = self._get_active(run_id)
        if active is None or active.finalized:
            return
        if error != QProcess.ProcessError.FailedToStart:
            return
        message = active.process.errorString() or "The post-run action could not start."
        self._finalize(
            run_id,
            state=RunState.EXITED,
            exit_code=0,
            exit_status=ExitStatus.NORMAL.value,
            error_kind=ErrorKind.POST_RUN_ACTION_FAILED.value,
            error_summary=(
                f"The automation succeeded, but {active.post_run_action.description.lower()} failed: "
                f"{message}"
            ),
        )

    def _on_post_run_action_finished(
        self,
        run_id: str,
        exit_code: int,
        exit_status: QProcess.ExitStatus,
    ) -> None:
        active = self._get_active(run_id)
        if active is None or active.finalized:
            return
        self._on_output(run_id, "stdout")
        self._on_output(run_id, "stderr")
        if exit_status == QProcess.ExitStatus.NormalExit and exit_code == 0:
            self._finalize(
                run_id,
                state=RunState.EXITED,
                exit_code=0,
                exit_status=ExitStatus.NORMAL.value,
            )
            return
        description = active.post_run_action.description if active.post_run_action else "Post-run action"
        self._finalize(
            run_id,
            state=RunState.EXITED,
            exit_code=0,
            exit_status=ExitStatus.NORMAL.value,
            error_kind=ErrorKind.POST_RUN_ACTION_FAILED.value,
            error_summary=(
                f"The automation succeeded, but {description.lower()} exited with code {exit_code}."
            ),
        )

    def _finalize(
        self,
        run_id: str,
        *,
        state: RunState,
        exit_code: int | None = None,
        exit_status: str | None = None,
        error_kind: str | None = None,
        error_summary: str | None = None,
    ) -> None:
        active = self._get_active(run_id)
        if active is None or active.finalized:
            return
        try:
            self._on_output(run_id, "stdout")
            self._on_output(run_id, "stderr")
        except RuntimeError:
            # QProcess can be in the process of being torn down after an error.
            self.logger.exception("Could not drain output for run %s", run_id)
        active.finalized = True
        if active.handoff is not None:
            active.handoff.close()
            active.handoff = None
        if active.emulator_watchdog is not None:
            active.emulator_watchdog.stop()
            active.emulator_watchdog.deleteLater()
            active.emulator_watchdog = None
        finished = self.store.now_iso()
        run = self.store.update_run(
            run_id,
            state=state,
            finished_at_utc=finished,
            exit_code=exit_code,
            exit_status=exit_status,
            error_kind=error_kind,
            error_summary=error_summary,
        )
        active.run = run
        self._write_metadata(run)
        for stream in (active.stdout_file, active.stderr_file):
            try:
                stream.flush()
                stream.close()
            except (OSError, ValueError):
                pass
        process = active.process
        self._active.pop(run_id, None)
        if not any(item.handoff is not None for item in self._active.values()):
            self._handoff_timer.stop()
        process.deleteLater()
        self.logger.info("Finished run %s with state %s", run_id, state.value)
        # FailedToStart can be delivered synchronously inside QProcess.start()
        # on Windows. Emit on the next Qt turn so queue callers have received
        # the returned Run and recorded its id before observing completion.
        QTimer.singleShot(0, lambda identifier=run_id: self.run_finished.emit(identifier))

    def _get_active(self, run_id: str) -> _ActiveProcess | None:
        return self._active.get(run_id)

    def _write_metadata(self, run: Run) -> None:
        if not run.stdout_path:
            return
        metadata_path = Path(run.stdout_path).parent / "metadata.json"
        metadata_path.write_text(
            json.dumps(
                {
                    "run_id": run.id,
                    "job_id": run.job_id,
                    "state": run.state.value,
                    "trigger_type": run.trigger_type,
                    "started_at_utc": run.started_at_utc,
                    "finished_at_utc": run.finished_at_utc,
                    "exit_code": run.exit_code,
                    "exit_status": run.exit_status,
                    "error_kind": run.error_kind,
                    "error_summary": run.error_summary,
                    "launch_snapshot": json.loads(run.launch_snapshot_json),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )


def _spec_dict(spec: LaunchSpec) -> dict[str, object]:
    values: dict[str, object] = {
        "executable": spec.executable,
        "arguments": list(spec.arguments),
        "working_directory": spec.working_directory,
        "display_command": spec.display_command,
    }
    if spec.handoff_process_names:
        values["handoff_process_names"] = list(spec.handoff_process_names)
    return values
