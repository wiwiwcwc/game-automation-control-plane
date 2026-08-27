from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import QMainWindow, QMessageBox

from ..application.execution_service import ExecutionService
from ..application.queue_service import QueueService
from ..application.post_run_actions import mumu_resource_key
from ..domain.models import DailyStatus
from ..integrations.maa_cli import MAA_CLI_RUNNER_TYPE
from ..integrations.maa_punish import MAA_PUNISH_RUNNER_TYPE
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
    def __init__(
        self,
        paths: AppPaths,
        logger: logging.Logger | None = None,
        i18n: LanguageManager | None = None,
    ):
        super().__init__()
        self.paths = paths.ensure()
        self.logger = logger or logging.getLogger("game_control_plane")
        self.database = Database(self.paths.database_path)
        self.store = Store(self.database)
        recovered = self.store.recover_incomplete_runs()
        if recovered:
            self.logger.info("Recovered %d interrupted run(s)", len(recovered))
        retention = prune_run_logs(self.paths.runs_dir, self.store, logger=self.logger)
        if retention.removed_run_ids:
            self.logger.info("Pruned %d old captured run log set(s)", len(retention.removed_run_ids))
        self.execution = ExecutionService(self.store, self.paths.runs_dir, logger=self.logger, parent=self)
        self.queue = QueueService(self.store, self.execution, logger=self.logger, parent=self)
        self.i18n = i18n or LanguageManager(parent=self)
        self.dashboard = Dashboard(self.i18n)
        self.setCentralWidget(self.dashboard)
        self.resize(1120, 780)
        self.setMinimumSize(900, 640)
        self._create_menus()

        self.dashboard.add_requested.connect(self.add_job)
        self.dashboard.run_dailies_requested.connect(self.run_today_dailies)
        self.dashboard.run_requested.connect(self.run_job)
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
        dialog = JobEditorDialog(parent=self, i18n=self.i18n)
        if dialog.exec() != JobEditorDialog.DialogCode.Accepted:
            return
        self._save_job(dialog.payload)

    def edit_job(self, job_id: int) -> None:
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
        try:
            self.execution.start(job, runtime_context=runtime_context)
        except Exception as exc:
            self.logger.exception("Could not start job %s", job_id)
            QMessageBox.critical(self, self.i18n.text("message.start_failed_title"), str(exc))
        self.refresh()

    def run_today_dailies(self) -> None:
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

    def _integration_preflight_report(self, job, *, kind: str):
        def check():
            if kind == "fos":
                report, error = run_preflight_with_progress(
                    job.runner_config, parent=self, i18n=self.i18n, kind="fos"
                )
            else:
                report, error = run_preflight_with_progress(
                    job.runner_config, parent=self, i18n=self.i18n
                )
            if report is None:
                raise RuntimeError(
                    error
                    or self.i18n.text(
                        "message.fos_preflight_failed_body"
                        if kind == "fos"
                        else "message.preflight_failed_body"
                    )
                )
            return report

        try:
            report = check()
        except Exception as exc:  # pragma: no cover - defensive UI boundary
            self.logger.exception("Could not check MAA setup for job %s", job.id)
            QMessageBox.critical(
                self,
                self.i18n.text(
                    "message.fos_preflight_failed_title"
                    if kind == "fos"
                    else "message.preflight_failed_title"
                ),
                str(exc)
                or self.i18n.text(
                    "message.fos_preflight_failed_body"
                    if kind == "fos"
                    else "message.preflight_failed_body"
                ),
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
        job = self.store.get_job(job_id)
        runs = self.store.list_runs(job_id, limit=50)
        if job is None or not runs:
            return
        dialog = RunHistoryDialog(job, runs, parent=self, i18n=self.i18n)
        dialog.exec()

    def toggle_enabled(self, job_id: int) -> None:
        if self.execution.is_job_running(job_id) or self.queue.is_job_queued(job_id):
            return
        job = self.store.get_job(job_id)
        if job is None:
            return
        self.store.set_job_enabled(job_id, not job.enabled)
        self.refresh()

    def move_job_up(self, job_id: int) -> None:
        if self.queue.active:
            return
        if self.store.move_job_up(job_id):
            self.refresh()

    def move_job_down(self, job_id: int) -> None:
        if self.queue.active:
            return
        if self.store.move_job_down(job_id):
            self.refresh()

    def remove_job(self, job_id: int) -> None:
        if self.execution.is_job_running(job_id) or self.queue.is_job_queued(job_id):
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
        self.refresh()

    def _run_finished(self, _run_id: str) -> None:
        self.refresh()

    def _output_received(self, _run_id: str, _stream: str, _data: bytes) -> None:
        # The log viewer reads durable files when opened. Keeping this signal
        # here gives the UI a clear extension point for a future live viewer.
        return

    def _queue_state_changed(self) -> None:
        self.refresh()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API name
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
        self.database.close()
        event.accept()


__all__ = ["MainWindow"]
