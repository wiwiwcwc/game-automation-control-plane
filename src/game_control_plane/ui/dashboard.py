from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..domain.models import DailyStatus, Job, Run
from ..integrations.registry import integration_label
from .i18n import LanguageManager, game_text, state_text


class MetricBlock(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.label = QLabel()
        self.label.setObjectName("MetricLabel")
        self.value = QLabel()
        self.value.setObjectName("MetricValue")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(self.label)
        layout.addWidget(self.value)


class SummaryTile(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SummaryTile")
        self.label = QLabel()
        self.label.setObjectName("SummaryLabel")
        self.value = QLabel("0")
        self.value.setObjectName("SummaryValue")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 13, 16, 13)
        layout.setSpacing(3)
        layout.addWidget(self.label)
        layout.addWidget(self.value)


class JobCard(QFrame):
    run_requested = Signal(int)
    completion_requested = Signal(int)
    view_log_requested = Signal(int)
    edit_requested = Signal(int)
    toggle_requested = Signal(int)
    remove_requested = Signal(int)
    move_up_requested = Signal(int)
    move_down_requested = Signal(int)

    def __init__(self, i18n: LanguageManager | None = None, parent=None):
        super().__init__(parent)
        self.i18n = i18n or LanguageManager(persist=False)
        self.setObjectName("JobCard")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.job_id: int | None = None
        self._data: tuple[Job, DailyStatus, Run | None, bool, str | None, bool, bool, bool] | None = None

        self.integration_badge = QLabel()
        self.integration_badge.setObjectName("StatusPill")
        self.title_label = QLabel()
        self.title_label.setObjectName("CardTitle")
        self.subtitle_label = QLabel()
        self.subtitle_label.setObjectName("CardSubtitle")
        self.status_pill = QLabel()
        self.status_pill.setObjectName("StatusPill")

        title_text = QVBoxLayout()
        title_text.setSpacing(2)
        title_text.addWidget(self.title_label)
        title_text.addWidget(self.subtitle_label)
        title_row = QHBoxLayout()
        title_row.setSpacing(10)
        title_row.addWidget(self.integration_badge)
        title_row.addLayout(title_text)
        title_row.addStretch()
        title_row.addWidget(self.status_pill)

        self.daily_metric = MetricBlock()
        self.execution_metric = MetricBlock()
        self.last_run_metric = MetricBlock()
        metrics = QHBoxLayout()
        metrics.setSpacing(30)
        metrics.addWidget(self.daily_metric, 1)
        metrics.addWidget(self.execution_metric, 1)
        metrics.addWidget(self.last_run_metric, 2)

        self.detail_label = QLabel()
        self.detail_label.setObjectName("Muted")
        self.detail_label.setWordWrap(True)

        self.run_button = QPushButton()
        self.run_button.setProperty("role", "primary")
        self.complete_button = QPushButton()
        self.log_button = QPushButton()
        self.edit_button = QPushButton()
        self.toggle_button = QPushButton()
        self.move_up_button = QPushButton("↑")
        self.move_up_button.setFixedWidth(38)
        self.move_down_button = QPushButton("↓")
        self.move_down_button.setFixedWidth(38)
        self.remove_button = QPushButton()
        self.remove_button.setProperty("role", "danger")
        self.run_button.clicked.connect(lambda: self._emit(self.run_requested))
        self.complete_button.clicked.connect(lambda: self._emit(self.completion_requested))
        self.log_button.clicked.connect(lambda: self._emit(self.view_log_requested))
        self.edit_button.clicked.connect(lambda: self._emit(self.edit_requested))
        self.toggle_button.clicked.connect(lambda: self._emit(self.toggle_requested))
        self.move_up_button.clicked.connect(lambda: self._emit(self.move_up_requested))
        self.move_down_button.clicked.connect(lambda: self._emit(self.move_down_requested))
        self.remove_button.clicked.connect(lambda: self._emit(self.remove_requested))

        primary_actions = QHBoxLayout()
        primary_actions.setSpacing(8)
        primary_actions.addWidget(self.run_button)
        primary_actions.addWidget(self.complete_button)
        primary_actions.addWidget(self.log_button)
        primary_actions.addStretch()
        manage_actions = QHBoxLayout()
        manage_actions.setSpacing(8)
        manage_actions.addWidget(self.edit_button)
        manage_actions.addWidget(self.toggle_button)
        manage_actions.addWidget(self.move_up_button)
        manage_actions.addWidget(self.move_down_button)
        manage_actions.addStretch()
        manage_actions.addWidget(self.remove_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(14)
        layout.addLayout(title_row)
        layout.addLayout(metrics)
        layout.addWidget(self.detail_label)
        layout.addLayout(primary_actions)
        layout.addLayout(manage_actions)
        self.i18n.language_changed.connect(self._retranslate)

    def _emit(self, signal: Signal) -> None:
        if self.job_id is not None:
            signal.emit(self.job_id)

    def set_job(
        self,
        job: Job,
        daily_status: DailyStatus,
        latest_run: Run | None,
        active: bool,
        queue_state: str | None = None,
        queue_active: bool = False,
        can_move_up: bool = False,
        can_move_down: bool = False,
        order_locked: bool = False,
    ) -> None:
        self._data = (job, daily_status, latest_run, active, queue_state, can_move_up, can_move_down, order_locked)
        self._render()

    def _retranslate(self, _language: str) -> None:
        self._render()

    def _render(self) -> None:
        if self._data is None:
            return
        job, daily_status, latest_run, active, queue_state, can_move_up, can_move_down, order_locked = self._data
        assert job.id is not None
        self.job_id = job.id
        self.setProperty("active", active)
        self.setProperty("disabled", not job.enabled)
        self.style().unpolish(self)
        self.style().polish(self)

        self.integration_badge.setText(integration_label(job.runner_type))
        self.title_label.setText(game_text(self.i18n, job.game_name, job.runner_type))
        subtitle = job.name
        if not job.enabled:
            subtitle += f" · {self.i18n.text('card.disabled')}"
        self.subtitle_label.setText(subtitle)
        self.daily_metric.label.setText(self.i18n.text("card.daily"))
        self.daily_metric.value.setText(self.i18n.text("card.completed" if daily_status == DailyStatus.COMPLETED else "card.pending"))
        self.execution_metric.label.setText(self.i18n.text("card.execution"))
        self.last_run_metric.label.setText(self.i18n.text("card.last_run"))

        if queue_state == "queued":
            execution, pill_state = self.i18n.text("card.queued"), "queued"
        elif queue_state == "running" or active:
            execution, pill_state = self.i18n.text("card.running"), "running"
        elif latest_run is None:
            execution, pill_state = self.i18n.text("card.never_run"), "idle"
        else:
            execution = state_text(self.i18n, latest_run.state.value)
            if latest_run.state.value == "exited":
                pill_state = "success"
            elif latest_run.state.value == "needs_attention":
                pill_state = "warning"
            elif latest_run.state.value in {"failed", "interrupted"}:
                pill_state = "failed"
            else:
                pill_state = "idle"
            if latest_run.exit_code is not None:
                execution += f" · {self.i18n.text('card.exit', code=latest_run.exit_code)}"
        self.execution_metric.value.setText(execution)
        self.status_pill.setText(execution.split(" · ", 1)[0])
        self.status_pill.setProperty("state", pill_state)
        self.status_pill.style().unpolish(self.status_pill)
        self.status_pill.style().polish(self.status_pill)

        if latest_run is None:
            self.last_run_metric.value.setText("—")
            self.detail_label.clear()
            self.detail_label.hide()
        else:
            when = latest_run.finished_at_utc or latest_run.started_at_utc or latest_run.created_at_utc
            last_run = format_timestamp(when)
            if latest_run.finished_at_utc:
                last_run += f" · {self.i18n.text('card.duration', duration=format_duration(latest_run.duration_seconds))}"
            self.last_run_metric.value.setText(last_run)
            self.detail_label.setText(latest_run.error_summary or "")
            self.detail_label.setVisible(bool(latest_run.error_summary))

        controls_locked = active or queue_state in {"queued", "running"}
        self.run_button.setText(self.i18n.text("button.run"))
        self.complete_button.setText(self.i18n.text("button.mark_pending" if daily_status == DailyStatus.COMPLETED else "button.mark_completed"))
        self.log_button.setText(self.i18n.text("button.view_log"))
        self.edit_button.setText(self.i18n.text("button.edit"))
        self.toggle_button.setText(self.i18n.text("button.disable" if job.enabled else "button.enable"))
        self.remove_button.setText(self.i18n.text("button.remove"))
        self.move_up_button.setToolTip(self.i18n.text("button.move_up"))
        self.move_up_button.setAccessibleName(self.i18n.text("button.move_up"))
        self.move_down_button.setToolTip(self.i18n.text("button.move_down"))
        self.move_down_button.setAccessibleName(self.i18n.text("button.move_down"))
        self.run_button.setEnabled(job.enabled and not controls_locked)
        self.complete_button.setEnabled(not controls_locked)
        self.log_button.setEnabled(latest_run is not None)
        self.edit_button.setEnabled(not controls_locked)
        self.toggle_button.setEnabled(not controls_locked)
        self.move_up_button.setEnabled(not order_locked and can_move_up)
        self.move_down_button.setEnabled(not order_locked and can_move_down)
        self.remove_button.setEnabled(not controls_locked)


class Dashboard(QWidget):
    add_requested = Signal()
    run_dailies_requested = Signal()
    run_requested = Signal(int)
    completion_requested = Signal(int)
    view_log_requested = Signal(int)
    edit_requested = Signal(int)
    toggle_requested = Signal(int)
    remove_requested = Signal(int)
    move_up_requested = Signal(int)
    move_down_requested = Signal(int)

    def __init__(self, i18n: LanguageManager | None = None, parent=None):
        super().__init__(parent)
        self.i18n = i18n or LanguageManager(persist=False)
        self._pending_count = 0
        self._completed_count = 0
        self._running_count = 0
        self._activity_key = "dashboard.idle"
        self._activity_values: dict[str, object] = {}

        self.eyebrow = QLabel()
        self.eyebrow.setObjectName("Eyebrow")
        self.title_label = QLabel()
        self.title_label.setObjectName("PageTitle")
        self.subtitle_label = QLabel()
        self.subtitle_label.setObjectName("PageSubtitle")
        title = QVBoxLayout()
        title.setSpacing(2)
        title.addWidget(self.eyebrow)
        title.addWidget(self.title_label)
        title.addWidget(self.subtitle_label)

        self.add_button = QPushButton()
        self.run_dailies_button = QPushButton()
        self.run_dailies_button.setProperty("role", "primary")
        self.run_dailies_button.clicked.connect(self.run_dailies_requested.emit)
        self.add_button.clicked.connect(self.add_requested.emit)
        header_actions = QHBoxLayout()
        header_actions.setSpacing(8)
        header_actions.addStretch()
        header_actions.addWidget(self.add_button)
        header_actions.addWidget(self.run_dailies_button)
        header = QVBoxLayout()
        header.setSpacing(10)
        header.addLayout(title)
        header.addLayout(header_actions)

        self.pending_tile = SummaryTile()
        self.completed_tile = SummaryTile()
        self.running_tile = SummaryTile()
        self.activity_tile = SummaryTile()
        summary = QGridLayout()
        summary.setHorizontalSpacing(10)
        summary.setVerticalSpacing(10)
        summary.addWidget(self.pending_tile, 0, 0)
        summary.addWidget(self.completed_tile, 0, 1)
        summary.addWidget(self.running_tile, 0, 2)
        summary.addWidget(self.activity_tile, 0, 3, 1, 2)
        summary.setColumnStretch(3, 1)

        self.queue_notice = QFrame()
        self.queue_notice.setObjectName("QueueNotice")
        self.queue_note = QLabel()
        self.queue_note.setWordWrap(True)
        notice_layout = QHBoxLayout(self.queue_notice)
        notice_layout.setContentsMargins(14, 10, 14, 10)
        notice_layout.addWidget(self.queue_note)

        self.empty_state = QFrame()
        self.empty_state.setObjectName("EmptyState")
        self.empty_title = QLabel()
        self.empty_title.setObjectName("CardTitle")
        self.empty_body = QLabel()
        self.empty_body.setObjectName("Muted")
        self.empty_body.setWordWrap(True)
        empty_layout = QVBoxLayout(self.empty_state)
        empty_layout.setContentsMargins(24, 28, 24, 28)
        empty_layout.setSpacing(7)
        empty_layout.addWidget(self.empty_title)
        empty_layout.addWidget(self.empty_body)

        self.cards_container = QWidget()
        self.cards_layout = QVBoxLayout(self.cards_container)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_layout.setSpacing(10)
        self.cards_layout.addStretch()
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setWidget(self.cards_container)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(15)
        layout.addLayout(header)
        layout.addLayout(summary)
        layout.addWidget(self.queue_notice)
        layout.addWidget(self.scroll, 1)
        self.i18n.language_changed.connect(self._retranslate)
        self._retranslate(self.i18n.language)

    def set_jobs(
        self,
        items: list[tuple[Job, DailyStatus, Run | None, bool]],
        *,
        queue_active: bool = False,
        queued_job_ids: set[int] | frozenset[int] = frozenset(),
        current_queue_job_id: int | None = None,
    ) -> None:
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self._pending_count = sum(status == DailyStatus.PENDING for _, status, _, _ in items)
        self._completed_count = len(items) - self._pending_count
        self._running_count = sum(active for _, _, _, active in items)
        order_locked = queue_active
        self.run_dailies_button.setEnabled(not queue_active)
        self.add_button.setEnabled(True)
        self.empty_state.setVisible(not items)
        if not items:
            self.cards_layout.addWidget(self.empty_state)
        for index, (job, daily_status, latest_run, active) in enumerate(items):
            card = JobCard(self.i18n)
            queue_state = None
            if queue_active and job.id in queued_job_ids:
                queue_state = "queued"
            if queue_active and job.id == current_queue_job_id:
                queue_state = "running"
            card.set_job(job, daily_status, latest_run, active, queue_state, queue_active, can_move_up=index > 0, can_move_down=index < len(items) - 1, order_locked=order_locked)
            card.run_requested.connect(self.run_requested)
            card.completion_requested.connect(self.completion_requested)
            card.view_log_requested.connect(self.view_log_requested)
            card.edit_requested.connect(self.edit_requested)
            card.toggle_requested.connect(self.toggle_requested)
            card.remove_requested.connect(self.remove_requested)
            card.move_up_requested.connect(self.move_up_requested)
            card.move_down_requested.connect(self.move_down_requested)
            self.cards_layout.addWidget(card)
        self.cards_layout.addStretch()
        self._update_summary()

    def set_activity(self, key: str, **values: object) -> None:
        self._activity_key = key
        self._activity_values = values
        self._update_summary()

    def _retranslate(self, _language: str) -> None:
        self.eyebrow.setText(self.i18n.text("dashboard.eyebrow"))
        self.title_label.setText(self.i18n.text("dashboard.title"))
        self.subtitle_label.setText(self.i18n.text("dashboard.subtitle"))
        self.add_button.setText(self.i18n.text("dashboard.add"))
        self.run_dailies_button.setText(self.i18n.text("dashboard.run_dailies"))
        self.queue_note.setText(self.i18n.text("dashboard.queue_note"))
        self.empty_title.setText(self.i18n.text("dashboard.empty_title"))
        self.empty_body.setText(self.i18n.text("dashboard.empty_body"))
        self.pending_tile.label.setText(self.i18n.text("dashboard.pending"))
        self.completed_tile.label.setText(self.i18n.text("dashboard.completed"))
        self.running_tile.label.setText(self.i18n.text("dashboard.running"))
        self.activity_tile.label.setText(self.i18n.text("dashboard.current"))
        self._update_summary()

    def _update_summary(self) -> None:
        self.pending_tile.value.setText(str(self._pending_count))
        self.completed_tile.value.setText(str(self._completed_count))
        self.running_tile.value.setText(str(self._running_count))
        self.activity_tile.value.setText(self.i18n.text(self._activity_key, **self._activity_values))


def format_timestamp(value: str | None) -> str:
    if not value:
        return "—"
    try:
        parsed = datetime.fromisoformat(value)
        return parsed.astimezone().strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return value


def format_duration(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, remainder = divmod(seconds, 60)
    if minutes < 60:
        return f"{int(minutes)}m {int(remainder):02d}s"
    hours, minutes = divmod(int(minutes), 60)
    return f"{hours}h {minutes:02d}m"


__all__ = ["Dashboard", "JobCard", "format_duration", "format_timestamp"]
