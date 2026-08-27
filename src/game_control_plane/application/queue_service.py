from __future__ import annotations

import logging
from collections import deque
from enum import StrEnum
from typing import Protocol

from PySide6.QtCore import QObject, QTimer, Signal

from ..domain.models import DailyStatus, Job, TriggerType
from ..persistence.store import Store


class QueueExecutor(Protocol):
    """The small part of ExecutionService needed by the queue."""

    run_finished: Signal

    def start(
        self,
        job: Job,
        trigger_type: str = TriggerType.MANUAL.value,
        runtime_context: dict[str, object] | None = None,
    ):
        ...


class QueueState(StrEnum):
    IDLE = "idle"
    ACTIVE = "active"


class QueueService(QObject):
    """Runs a snapshot of today's pending jobs sequentially in memory."""

    state_changed = Signal()
    queue_started = Signal()
    queue_empty = Signal()
    item_started = Signal(int)
    item_finished = Signal(int, str)
    item_failed_to_start = Signal(int, str)
    queue_finished = Signal()

    def __init__(
        self,
        store: Store,
        executor: QueueExecutor,
        logger: logging.Logger | None = None,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self.store = store
        self.executor = executor
        self.logger = logger or logging.getLogger("game_control_plane.queue")
        self._state = QueueState.IDLE
        self._pending: deque[Job] = deque()
        self._current_job: Job | None = None
        self._current_run_id: str | None = None
        self._runtime_contexts: dict[int, dict[str, object]] = {}
        self.executor.run_finished.connect(self._on_run_finished)

    @property
    def state(self) -> QueueState:
        return self._state

    @property
    def active(self) -> bool:
        return self._state == QueueState.ACTIVE

    @property
    def current_job_id(self) -> int | None:
        return self._current_job.id if self._current_job else None

    @property
    def queued_job_ids(self) -> tuple[int, ...]:
        return tuple(int(job.id) for job in self._pending if job.id is not None)

    @property
    def current_run_id(self) -> str | None:
        return self._current_run_id

    def is_job_queued(self, job_id: int) -> bool:
        return self.current_job_id == job_id or job_id in self.queued_job_ids

    def start(
        self,
        *,
        excluded_job_ids: set[int] | frozenset[int] = frozenset(),
        runtime_contexts: dict[int, dict[str, object]] | None = None,
    ) -> bool:
        """Snapshot enabled/pending jobs and begin the sequential run.

        Returns False when already active or when there are no eligible jobs.
        The queue is intentionally not stored in SQLite and is lost on restart.
        """

        if self.active:
            return False
        jobs = [
            job
            for job in self.store.list_jobs()
            if job.enabled
            and job.id not in excluded_job_ids
            and self.store.daily_status(job) == DailyStatus.PENDING
        ]
        if not jobs:
            self._pending.clear()
            self._current_job = None
            self._current_run_id = None
            self._runtime_contexts.clear()
            self.queue_empty.emit()
            self.state_changed.emit()
            return False

        self._pending = deque(jobs)
        self._current_job = None
        self._current_run_id = None
        self._runtime_contexts = dict(runtime_contexts or {})
        self._state = QueueState.ACTIVE
        self.logger.info("Starting daily queue with %d job(s)", len(jobs))
        self.queue_started.emit()
        self.state_changed.emit()
        self._start_next()
        return True

    def _start_next(self) -> None:
        if not self.active:
            return
        if not self._pending:
            self._current_job = None
            self._current_run_id = None
            self._state = QueueState.IDLE
            self._runtime_contexts.clear()
            self.logger.info("Daily queue finished")
            self.state_changed.emit()
            self.queue_finished.emit()
            return

        job = self._pending.popleft()
        self._current_job = job
        self._current_run_id = None
        self.item_started.emit(int(job.id))
        self.state_changed.emit()
        try:
            context = self._runtime_contexts.get(int(job.id)) if job.id is not None else None
            run = self.executor.start(
                job,
                trigger_type=TriggerType.QUEUE.value,
                runtime_context=context,
            )
            self._current_run_id = run.id
        except Exception as exc:
            # A synchronous launch failure has no run_finished signal to wait
            # for. Treat it as one failed item and continue on the next event
            # loop turn, preserving the queue's continue-on-failure contract.
            message = str(exc) or "The job could not be started."
            self.logger.exception("Could not start queued job %s", job.id)
            self.item_failed_to_start.emit(int(job.id), message)
            self._current_job = None
            self._current_run_id = None
            self.state_changed.emit()
            QTimer.singleShot(0, self._start_next)

    def _on_run_finished(self, run_id: str) -> None:
        if not self.active or self._current_run_id != run_id or self._current_job is None:
            return
        job = self._current_job
        self.item_finished.emit(int(job.id), run_id)
        self._current_job = None
        self._current_run_id = None
        self.state_changed.emit()
        # Advance on the next Qt turn so run finalization and UI refresh finish
        # before the next process is launched.
        QTimer.singleShot(0, self._start_next)


__all__ = ["QueueExecutor", "QueueService", "QueueState"]
