from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
)

from ..domain.models import Job, Run
from .dashboard import format_duration, format_timestamp
from .i18n import LanguageManager, game_text, state_text


class RunHistoryDialog(QDialog):
    """Show the latest 50 attempts for one automation and captured logs."""

    def __init__(
        self,
        job: Job | str,
        runs: list[Run],
        parent=None,
        i18n: LanguageManager | None = None,
    ):
        super().__init__(parent)
        self.i18n = i18n or LanguageManager(persist=False)
        self.job = job
        self.runs = sorted(runs, key=_run_sort_key, reverse=True)[:50]
        title = (
            job
            if isinstance(job, str)
            else f"{game_text(self.i18n, job.game_name, job.runner_type)} · {job.name}"
        )
        self.setWindowTitle(self.i18n.text("history.title", title=title))
        self.resize(900, 620)
        self.selected_run: Run | None = None

        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.history_table = QTableWidget(0, 5)
        self.history_table.setHorizontalHeaderLabels(
            [
                self.i18n.text("history.timestamp"),
                self.i18n.text("history.state"),
                self.i18n.text("history.duration"),
                self.i18n.text("history.exit_code"),
                self.i18n.text("history.error"),
            ]
        )
        self.history_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.history_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.history_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.history_table.setMinimumHeight(190)
        self.history_table.horizontalHeader().setStretchLastSection(True)
        self.history_table.currentCellChanged.connect(self._row_changed)

        self.stdout = QTextEdit()
        self.stderr = QTextEdit()
        self.stdout.setReadOnly(True)
        self.stderr.setReadOnly(True)
        tabs = QTabWidget()
        tabs.addTab(self.stdout, self.i18n.text("history.stdout"))
        tabs.addTab(self.stderr, self.i18n.text("history.stderr"))

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText(
            self.i18n.text("button.close")
        )
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout = QVBoxLayout(self)
        layout.addWidget(self.summary)
        layout.addWidget(self.history_table)
        layout.addWidget(tabs)
        layout.addWidget(buttons)
        self.reload()

    def reload(self) -> None:
        self.history_table.setRowCount(0)
        for run in self.runs:
            row = self.history_table.rowCount()
            self.history_table.insertRow(row)
            values = (
                format_timestamp(run.finished_at_utc or run.started_at_utc or run.created_at_utc),
                state_text(self.i18n, run.state.value),
                format_duration(run.duration_seconds),
                "—" if run.exit_code is None else str(run.exit_code),
                concise_error(run.error_summary),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, run.id)
                self.history_table.setItem(row, column, item)
        if self.runs:
            self.history_table.setCurrentCell(0, 0)
            self._select_row(0)
        else:
            self._select_row(-1)

    def _row_changed(self, current_row: int, *_: int) -> None:
        self._select_row(current_row)

    def _select_row(self, row: int) -> None:
        if row < 0 or row >= len(self.runs):
            self.selected_run = None
            self.summary.setText(self.i18n.text("history.no_runs"))
            self.stdout.clear()
            self.stderr.clear()
            return
        self.selected_run = self.runs[row]
        run = self.selected_run
        detail = concise_error(run.error_summary)
        exit_text = "—" if run.exit_code is None else str(run.exit_code)
        summary = self.i18n.text(
            "history.summary",
            run_id=run.id[:8],
            state=state_text(self.i18n, run.state.value),
            duration=format_duration(run.duration_seconds),
            exit_code=exit_text,
        )
        if detail:
            summary += f"\n{detail}"
        self.summary.setText(summary)
        self.stdout.setPlainText(_read_log(run.stdout_path, i18n=self.i18n))
        self.stderr.setPlainText(_read_log(run.stderr_path, i18n=self.i18n))


class RunLogDialog(RunHistoryDialog):
    """Compatibility wrapper for callers that already have one Run."""

    def __init__(self, run: Run, parent=None):
        super().__init__(f"Job {run.job_id}", [run], parent=parent)
        self.run = run


def concise_error(value: str | None, limit: int = 120) -> str:
    if not value:
        return ""
    text = " ".join(value.replace("\r", "").splitlines()).strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def _read_log(
    path: str | None,
    max_bytes: int = 2 * 1024 * 1024,
    i18n: LanguageManager | None = None,
) -> str:
    language = i18n or LanguageManager("en_US", persist=False)
    if not path:
        return language.text("history.log_missing")
    try:
        log_path = Path(path)
        size = log_path.stat().st_size
        with log_path.open("rb") as stream:
            if size > max_bytes:
                stream.seek(-max_bytes, 2)
            data = stream.read(max_bytes)
        text = data.decode("utf-8", errors="replace")
        if size > max_bytes:
            return language.text(
                "history.log_tail", limit=_format_byte_limit(max_bytes), text=text
            )
        return text
    except OSError:
        return language.text("history.log_gone")


def _format_byte_limit(value: int) -> str:
    mib = 1024 * 1024
    kib = 1024
    if value >= mib and value % mib == 0:
        return f"{value // mib} MiB"
    if value >= kib and value % kib == 0:
        return f"{value // kib} KiB"
    return f"{value} bytes"


def _run_sort_key(run: Run) -> datetime:
    for value in (run.started_at_utc, run.created_at_utc, run.finished_at_utc):
        if value:
            try:
                parsed = datetime.fromisoformat(value)
                if parsed.tzinfo is None or parsed.utcoffset() is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                return parsed.astimezone(timezone.utc)
            except ValueError:
                continue
    return datetime.min.replace(tzinfo=timezone.utc)


__all__ = ["RunHistoryDialog", "RunLogDialog", "concise_error"]
