from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QProcess, QTimer
from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import QMainWindow, QMessageBox

from ..application.execution_service import ExecutionService
from ..application.queue_service import QueueService
from ..application.post_run_actions import mumu_resource_key
from ..domain.models import DailyStatus, ErrorKind
from ..integrations.maa_cli import MAA_CLI_RUNNER_TYPE
from ..integrations.maa_punish import MAA_PUNISH_RUNNER_TYPE
from ..integrations.onedragon import ZZZ_ONEDRAGON_RUNNER_TYPE, ZzzOneDragonIntegration
from ..persistence.database import Database
from ..persistence.store import Store
from ..platform.log_retention import prune_run_logs
from ..platform.paths import AppPaths
from .dashboard import Dashboard
from .job_editor import JobEditorDialog
from .i18n import LanguageManager, SUPPORTED_LANGUAGES
from .maa_preflight_dialog import MaaPreflightDialog
from .maa_preflight_runner import run_preflight_with_progress
from .run_log_dialog import RunHistoryDialog


class MainWindow(QMainWindow):
    CLOSE_STOP_TIMEOUT_MS = 5_000

    def __init__(
        self,
        paths: AppPaths,
        logger: logging.Logger | None = None,
        i18n: LanguageManager | None = None,
    ):
        super().__init__()
        self._database_closed = False
        self._shutdown_finalized = False
        self.paths = paths.ensure()
        self.logger = logger or logging.getLogger("game_control_plane")
        self.database = Database(self.paths.database_path)
        self.store = Store(self.database)
        self.i18n = i18n or LanguageManager(parent=self)
        recovered = self.store.recover_incomplete_runs()
        if recovered:
            self.logger.info("Recovered %d interrupted run(s)", len(recovered))
        retention = prune_run_logs(self.paths.runs_dir, self.store, logger=self.logger)
        if retention.removed_run_ids:
            self.logger.info("Pruned %d old captured run log set(s)", len(retention.removed_run_ids))
        self.execution = ExecutionService(
            self.store,
            self.paths.runs_dir,
            logger=self.logger,
            parent=self,
            summary_text=self.i18n.text,
        )
        self.queue = QueueService(self.store, self.execution, logger=self.logger, parent=self)
        self.dashboard = Dashboard(self.i18n)
        self.setCentralWidget(self.dashboard)
        self._closing_requested = False
        self._close_ready = False
        self._closing_run_ids: set[str] = set()
        self._close_timer = QTimer(self)
        self._close_timer.setSingleShot(True)
        self._close_timer.timeout.connect(self._close_stop_timeout)
        self.resize(1120, 780)
        self.setMinimumSize(900, 640)
        self._create_menus()

        self.dashboard.add_requested.connect(self.add_job)
        self.dashboard.run_dailies_requested.connect(self.run_today_dailies)
        self.dashboard.run_requested.connect(self.run_job)
        self.dashboard.open_gui_requested.connect(self.open_onedragon_gui)
        self.dashboard.stop_requested.connect(self.stop_job)
        self.dashboard.completion_requested.connect(self.toggle_completion)
        self.dashboard.view_log_requested.connect(self.view_latest_log)
        self.dashboard.edit_requested.connect(self.edit_job)
        self.dashboard.toggle_requested.connect(self.toggle_enabled)
        self.dashboard.remove_requested.connect(self.remove_job)
        self.dashboard.move_up_requested.connect(self.move_job_up)
        self.dashboard.move_down_requested.connect(self.move_job_down)
        self.execution.run_started.connect(self._run_started)
        self.execution.run_finished.connect(self._run_finished)
        self.execution.output_received.connect(self._output_received)
        self.queue.state_changed.connect(self._queue_state_changed)
        self.i18n.language_changed.connect(self._language_changed)
        self._retranslate_ui()
        self.refresh()

    def _create_menus(self) -> None:
        self.settings_menu = self.menuBar().addMenu("")
        self.language_menu = self.settings_menu.addMenu("")
        self.language_group = QActionGroup(self)
        self.language_group.setExclusive(True)
        self.language_actions: dict[str, QAction] = {}
        for language in SUPPORTED_LANGUAGES:
            action = QAction(self)
            action.setCheckable(True)
            action.setData(language)
            action.setChecked(language == self.i18n.language)
            action.triggered.connect(
                lambda checked, code=language: checked and self.i18n.set_language(code)
            )
            self.language_group.addAction(action)
            self.language_menu.addAction(action)
            self.language_actions[language] = action

    def _language_changed(self, _language: str) -> None:
        self._retranslate_ui()
        self.refresh()

    def _retranslate_ui(self) -> None:
        self.setWindowTitle(self.i18n.text("app.title"))
        self.settings_menu.setTitle(self.i18n.text("menu.settings"))
        self.language_menu.setTitle(self.i18n.text("menu.language"))
        for language, action in self.language_actions.items():
            action.setText(self.i18n.text(f"language.{language}"))

    def refresh(self) -> None:
        if self._database_closed or self._shutdown_finalized:
            return
        items = []
        active_job_ids = self.execution.active_job_ids
        queue_active = self.queue.active
        queued_job_ids = set(self.queue.queued_job_ids)
        current_queue_job_id = self.queue.current_job_id
        for job in self.store.list_jobs():
            status = self.store.daily_status(job)
            latest = self.store.latest_run(int(job.id))
            items.append((job, status, latest, job.id in active_job_ids))
        self.dashboard.set_jobs(
            items,
            queue_active=queue_active,
            queued_job_ids=queued_job_ids,
            current_queue_job_id=current_queue_job_id,
        )
        active_count = len(self.execution.active_runs)
        if active_count == 0:
            if queue_active:
                self.dashboard.set_activity("dashboard.queue_active")
            else:
                self.dashboard.set_activity("dashboard.idle")
        elif active_count == 1:
            active_job = self.store.get_job(self.execution.active_runs[0].job_id)
            self.dashboard.set_activity(
                "dashboard.running_one",
                name=active_job.name if active_job else self.i18n.text("card.running"),
            )
        else:
            self.dashboard.set_activity("dashboard.running_many", count=active_count)

    def add_job(self) -> None:
        if self._closing_requested:
            return
        dialog = JobEditorDialog(parent=self, i18n=self.i18n)
        if dialog.exec() != JobEditorDialog.DialogCode.Accepted:
            return
        self._save_job(dialog.payload)

    def edit_job(self, job_id: int) -> None:
        if self._closing_requested:
            return
        if self.execution.is_job_running(job_id) or self.queue.is_job_queued(job_id):
            return
        job = self.store.get_job(job_id)
        if job is None:
            return
        dialog = JobEditorDialog(job, parent=self, i18n=self.i18n)
        if dialog.exec() != JobEditorDialog.DialogCode.Accepted:
            return
        self._save_job(dialog.payload)

    def _save_job(self, payload: dict[str, object]) -> None:
        try:
            self.store.save_job(
                game_name=str(payload["game_name"]),
                name=str(payload["name"]),
                runner_type=str(payload["runner_type"]),
                runner_config_version=int(payload["runner_config_version"]),
                runner_config=dict(payload["runner_config"]),
                timezone_id=str(payload["timezone_id"]),
                reset_minute=int(payload["reset_minute"]),
                enabled=bool(payload["enabled"]),
                job_id=payload["job_id"],
            )
        except Exception as exc:
            self.logger.exception("Could not save job")
            QMessageBox.critical(self, self.i18n.text("message.save_failed_title"), str(exc))
            return
        self.refresh()

    def run_job(self, job_id: int) -> None:
        if self._closing_requested:
            return
        if self.execution.is_job_running(job_id) or self.queue.is_job_queued(job_id):
            QMessageBox.information(
                self,
                self.i18n.text("message.start_active_title"),
                self.i18n.text("message.start_active_body"),
            )
            return
        job = self.store.get_job(job_id)
        if job is None:
            return
        runtime_context = None
        if job.runner_type == MAA_CLI_RUNNER_TYPE:
            report = self._maa_preflight_report(job)
            if report is None:
                return
            runtime_context = {
                "emulator_started_by_control_plane": report.emulator_started,
            }
        elif job.runner_type == MAA_PUNISH_RUNNER_TYPE:
            report = self._fos_preflight_report(job)
            if report is None:
                return
            runtime_context = {
                "emulator_started_by_control_plane": report.emulator_started,
            }
        elif job.runner_type == ZZZ_ONEDRAGON_RUNNER_TYPE:
            report = self._onedragon_preflight_report(job)
            if report is None:
                return
        try:
            self.execution.start(job, runtime_context=runtime_context)
        except Exception as exc:
            self.logger.exception("Could not start job %s", job_id)
            QMessageBox.critical(self, self.i18n.text("message.start_failed_title"), str(exc))
        self.refresh()

    def open_onedragon_gui(self, job_id: int) -> None:
        """Launch the configured OneDragon GUI as an independent action."""

        if self._closing_requested:
            return
        if self.execution.is_job_running(job_id) or self.queue.is_job_queued(job_id):
            QMessageBox.information(
                self,
                self.i18n.text("message.onedragon_gui_active_title"),
                self.i18n.text("message.onedragon_gui_active_body"),
            )
            return
        job = self.store.get_job(job_id)
        if job is None or job.runner_type != ZZZ_ONEDRAGON_RUNNER_TYPE:
            return
        report = self._onedragon_preflight_report(job)
        if report is None:
            return
        spec = None
        failure = ""
        try:
            spec = ZzzOneDragonIntegration().build_gui_launch_spec(job)
            result = QProcess.startDetached(
                spec.executable,
                list(spec.arguments),
                spec.working_directory or "",
            )
            started = bool(result[0]) if isinstance(result, tuple) else bool(result)
        except Exception as exc:  # pragma: no cover - defensive UI boundary
            self.logger.exception("Could not open OneDragon GUI for job %s", job_id)
            started = False
            failure = str(exc)
        if not started:
            detail = failure or str(job.runner_config.get("executable_path", ""))
            QMessageBox.critical(
                self,
                self.i18n.text("message.onedragon_gui_failed_title"),
                self.i18n.text("message.onedragon_gui_failed_body", path=detail),
            )
            return
        QMessageBox.information(
            self,
            self.i18n.text("message.onedragon_gui_started_title"),
            self.i18n.text("message.onedragon_gui_started_body"),
        )

    def stop_job(self, job_id: int) -> None:
        if self._closing_requested:
            return
        job = self.store.get_job(job_id)
        if job is None or job.runner_type != ZZZ_ONEDRAGON_RUNNER_TYPE:
            return
        run = next(
            (active for active in self.execution.active_runs if active.job_id == job_id),
            None,
        )
        if run is None:
            return
        if not self.execution.stop(
            run.id,
            reason=self.i18n.text("run.stop_requested"),
        ):
            QMessageBox.warning(
                self,
                self.i18n.text("message.stop_failed_title"),
                self.i18n.text(
                    "message.stop_failed_body",
                    summary=self.i18n.text("run.stop_no_longer_active"),
                ),
            )
        self.refresh()

    def run_today_dailies(self) -> None:
        if self._closing_requested:
            return
        if self.queue.active:
            return
        active_job_ids = self.execution.active_job_ids
        eligible_jobs = [
            job
            for job in self.store.list_jobs()
            if job.enabled
            and job.id not in active_job_ids
            and self.store.daily_status(job) == DailyStatus.PENDING
        ]
        runtime_contexts: dict[int, dict[str, object]] = {}
        for job in eligible_jobs:
            if job.runner_type == MAA_CLI_RUNNER_TYPE:
                report = self._maa_preflight_report(job)
                if report is None:
                    return
                runtime_contexts[int(job.id)] = {
                    "emulator_started_by_control_plane": report.emulator_started,
                }
            elif job.runner_type == MAA_PUNISH_RUNNER_TYPE:
                report = self._fos_preflight_report(job)
                if report is None:
                    return
                runtime_contexts[int(job.id)] = {
                    "emulator_started_by_control_plane": report.emulator_started,
                }
            elif job.runner_type == ZZZ_ONEDRAGON_RUNNER_TYPE:
                report = self._onedragon_preflight_report(job)
                if report is None:
                    return
        self._transfer_queue_emulator_ownership(eligible_jobs, runtime_contexts)
        if not self.queue.start(
            excluded_job_ids=active_job_ids,
            runtime_contexts=runtime_contexts,
        ):
            QMessageBox.information(
                self,
                self.i18n.text("message.nothing_title"),
                self.i18n.text("message.nothing_body"),
            )
        self.refresh()

    @staticmethod
    def _transfer_queue_emulator_ownership(jobs, runtime_contexts) -> None:
        """Keep a queue-started instance open until its final queued consumer."""

        started_resources = {
            key
            for job in jobs
            if (key := mumu_resource_key(job)) is not None
            and bool(
                runtime_contexts.get(int(job.id), {}).get(
                    "emulator_started_by_control_plane", False
                )
            )
        }
        for resource in started_resources:
            consumers = [job for job in jobs if mumu_resource_key(job) == resource]
            for job in consumers:
                runtime_contexts.setdefault(int(job.id), {})[
                    "emulator_started_by_control_plane"
                ] = False
            if consumers:
                runtime_contexts.setdefault(int(consumers[-1].id), {})[
                    "emulator_started_by_control_plane"
                ] = True

    def _maa_preflight_report(self, job):
        return self._integration_preflight_report(job, kind="maa")

    def _fos_preflight_report(self, job):
        return self._integration_preflight_report(job, kind="fos")

    def _onedragon_preflight_report(self, job):
        return self._integration_preflight_report(job, kind="onedragon")

    def _integration_preflight_report(self, job, *, kind: str):
        def check():
            if kind == "maa":
                # Keep the original call shape for embedders/tests that
                # provide the MAA runner callback; specialized integrations
                # opt into the explicit kind dispatch below.
                report, error = run_preflight_with_progress(
                    job.runner_config, parent=self, i18n=self.i18n
                )
            else:
                report, error = run_preflight_with_progress(
                    job.runner_config, parent=self, i18n=self.i18n, kind=kind
                )
            if report is None:
                body_key = {
                    "fos": "message.fos_preflight_failed_body",
                    "onedragon": "message.onedragon_preflight_failed_body",
                }.get(kind, "message.preflight_failed_body")
                raise RuntimeError(
                    error
                    or self.i18n.text(body_key)
                )
            return report

        try:
            report = check()
        except Exception as exc:  # pragma: no cover - defensive UI boundary
            self.logger.exception("Could not check MAA setup for job %s", job.id)
            title_key = {
                "fos": "message.fos_preflight_failed_title",
                "onedragon": "message.onedragon_preflight_failed_title",
            }.get(kind, "message.preflight_failed_title")
            body_key = {
                "fos": "message.fos_preflight_failed_body",
                "onedragon": "message.onedragon_preflight_failed_body",
            }.get(kind, "message.preflight_failed_body")
            QMessageBox.critical(
                self,
                self.i18n.text(title_key),
                str(exc)
                or self.i18n.text(body_key),
            )
            return None
        if report.ready:
            return report
        dialog = MaaPreflightDialog(report, check, parent=self, i18n=self.i18n)
        accepted = dialog.exec() == MaaPreflightDialog.DialogCode.Accepted
        if dialog.edit_requested and job.id is not None:
            self.edit_job(int(job.id))
        return dialog.report if accepted and dialog.report.ready else None

    def toggle_completion(self, job_id: int) -> None:
        if self._closing_requested:
            return
        if self.execution.is_job_running(job_id) or self.queue.is_job_queued(job_id):
            return
        job = self.store.get_job(job_id)
        if job is None:
            return
        if self.store.daily_status(job) == DailyStatus.COMPLETED:
            self.store.undo_completed(job)
        else:
            self.store.mark_completed(job)
        self.refresh()

    def view_latest_log(self, job_id: int) -> None:
        if self._closing_requested:
            return
        job = self.store.get_job(job_id)
        runs = self.store.list_runs(job_id, limit=50)
        if job is None or not runs:
            return
        dialog = RunHistoryDialog(job, runs, parent=self, i18n=self.i18n)
        dialog.exec()

    def toggle_enabled(self, job_id: int) -> None:
        if self._closing_requested:
            return
        if self.execution.is_job_running(job_id) or self.queue.is_job_queued(job_id):
            return
        job = self.store.get_job(job_id)
        if job is None:
            return
        self.store.set_job_enabled(job_id, not job.enabled)
        self.refresh()

    def move_job_up(self, job_id: int) -> None:
        if self._closing_requested or self.queue.active:
            return
        if self.store.move_job_up(job_id):
            self.refresh()

    def move_job_down(self, job_id: int) -> None:
        if self._closing_requested or self.queue.active:
            return
        if self.store.move_job_down(job_id):
            self.refresh()

    def remove_job(self, job_id: int) -> None:
        if self._closing_requested or self.execution.is_job_running(job_id) or self.queue.is_job_queued(job_id):
            return
        job = self.store.get_job(job_id)
        if job is None:
            return
        answer = QMessageBox.question(
            self,
            self.i18n.text("message.remove_title"),
            self.i18n.text("message.remove_body", name=job.name),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.store.delete_job(job_id)
        self.refresh()

    def _run_started(self, _run_id: str) -> None:
        if self._database_closed or self._shutdown_finalized:
            return
        self.refresh()

    def _run_finished(self, run_id: str) -> None:
        if self._database_closed or self._shutdown_finalized:
            return
        self.refresh()
        finished = self.store.get_run(run_id)
        if (
            finished is not None
            and finished.error_kind == ErrorKind.STOP_FAILED.value
        ):
            QMessageBox.warning(
                self,
                self.i18n.text("message.stop_failed_title"),
                self.i18n.text(
                    "message.stop_failed_body",
                    summary=finished.error_summary
                    or self.i18n.text("run.stop_tree_failed_detail"),
                ),
            )
        if self._closing_requested:
            self._closing_run_ids.discard(run_id)
            self._request_close_if_ready()

    def _output_received(self, _run_id: str, _stream: str, _data: bytes) -> None:
        # The log viewer reads durable files when opened. Keeping this signal
        # here gives the UI a clear extension point for a future live viewer.
        return

    def _queue_state_changed(self) -> None:
        if self._database_closed or self._shutdown_finalized:
            return
        self.refresh()

    def _disconnect_runtime_signals(self) -> None:
        """Prevent late Qt emissions from entering the closed store."""

        for signal, slot in (
            (self.execution.run_started, self._run_started),
            (self.execution.run_finished, self._run_finished),
            (self.execution.output_received, self._output_received),
            (self.queue.state_changed, self._queue_state_changed),
        ):
            try:
                signal.disconnect(slot)
            except (RuntimeError, TypeError):
                # Disconnect is intentionally idempotent for repeated close
                # events and for tests that already detached a signal.
                pass

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API name
        if self._database_closed:
            event.accept()
            return
        if self._close_ready:
            self._close_timer.stop()
            self._shutdown_finalized = True
            self._disconnect_runtime_signals()
            try:
                self.database.close()
            except Exception:
                self.logger.exception("Could not close the application database")
            finally:
                self._database_closed = True
            event.accept()
            return
        if self._closing_requested:
            event.ignore()
            return
        if self.execution.is_running:
            active_count = len(self.execution.active_runs)
            answer = QMessageBox.question(
                self,
                self.i18n.text("message.close_running_title"),
                self.i18n.text("message.close_running_body", count=active_count),
                QMessageBox.StandardButton.Close | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if answer != QMessageBox.StandardButton.Close:
                event.ignore()
                return
        self._closing_requested = True
        self.execution.set_accepting_runs(False)
        self.queue.cancel()
        self._closing_run_ids = {run.id for run in self.execution.active_runs}
        event.ignore()
        for run_id in tuple(self._closing_run_ids):
            if not self.execution.stop(
                run_id,
                reason=self.i18n.text("run.close_requested"),
            ):
                # The process may have finished between the snapshot above
                # and this stop request. There will be no matching signal to
                # remove an already-finalized run, so do not wait for it.
                self._closing_run_ids.discard(run_id)
        if self._closing_run_ids:
            self._close_timer.start(self.CLOSE_STOP_TIMEOUT_MS)
        else:
            self._request_close_if_ready()

    def _close_stop_timeout(self) -> None:
        remaining = tuple(self._closing_run_ids)
        if not remaining:
            self._request_close_if_ready()
            return
        timed_out: list[str] = []
        for run_id in remaining:
            if self.execution.force_finalize_stop_timeout(run_id):
                timed_out.append(run_id)
            # Whether the run was finalized here or disappeared between the
            # close snapshot and this timer, it must not keep the application
            # waiting after its persistence attempt has completed.
            self._closing_run_ids.discard(run_id)
        if timed_out:
            QMessageBox.warning(
                self,
                self.i18n.text("message.close_timeout_title"),
                self.i18n.text(
                    "message.close_timeout_body", count=len(timed_out)
                ),
            )
        self._request_close_if_ready()

    def _request_close_if_ready(self) -> None:
        if not self._closing_requested or self._closing_run_ids:
            return
        self._close_timer.stop()
        if self._close_ready:
            return
        self._close_ready = True
        QTimer.singleShot(0, self.close)


__all__ = ["MainWindow"]
