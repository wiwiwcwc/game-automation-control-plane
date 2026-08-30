from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..integrations.maa_preflight import CheckState, MaaPreflightReport
from .i18n import LanguageManager, preflight_step_text


class MaaPreflightDialog(QDialog):
    """Explain the first failed MAA setup step and let the user retry it."""

    def __init__(
        self,
        report: MaaPreflightReport,
        check_again: Callable[[], MaaPreflightReport],
        parent: QWidget | None = None,
        i18n: LanguageManager | None = None,
    ):
        super().__init__(parent)
        self.i18n = i18n or LanguageManager(persist=False)
        self.report = report
        self.check_again = check_again
        self.edit_requested = False
        self.prefix = {
            "fos": "fos_preflight",
            "onedragon": "onedragon_preflight",
        }.get(report.kind, "preflight")
        self.setWindowTitle(self.i18n.text(f"{self.prefix}.title"))
        self.setModal(True)
        self.resize(720, 470)

        heading = QLabel(self.i18n.text(f"{self.prefix}.heading"))
        heading.setObjectName("PageTitle")
        description = QLabel(self.i18n.text(f"{self.prefix}.description"))
        description.setObjectName("Muted")
        description.setWordWrap(True)

        self.steps_layout = QGridLayout()
        self.steps_layout.setColumnStretch(2, 1)
        self.step_widgets: list[tuple[QLabel, QLabel, QLabel]] = []
        for row in range(4):
            number = QLabel(str(row + 1))
            number.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
            state = QLabel()
            state.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
            text = QLabel()
            text.setWordWrap(True)
            self.steps_layout.addWidget(number, row, 0)
            self.steps_layout.addWidget(state, row, 1)
            self.steps_layout.addWidget(text, row, 2)
            self.step_widgets.append((number, state, text))

        self.action_label = QLabel()
        self.action_label.setObjectName("ActionCallout")
        self.action_label.setWordWrap(True)

        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setMaximumHeight(130)
        self.details.hide()
        self.details_button = QPushButton(self.i18n.text("preflight.show_details"))
        self.details_button.setCheckable(True)
        self.details_button.toggled.connect(self._toggle_details)

        self.buttons = QDialogButtonBox()
        self.retry_button = self.buttons.addButton(
            self.i18n.text("preflight.retry"), QDialogButtonBox.ButtonRole.ActionRole
        )
        self.edit_button = self.buttons.addButton(
            self.i18n.text("preflight.edit"), QDialogButtonBox.ButtonRole.ActionRole
        )
        self.run_button = self.buttons.addButton(
            self.i18n.text("preflight.run"), QDialogButtonBox.ButtonRole.AcceptRole
        )
        self.close_button = self.buttons.addButton(QDialogButtonBox.StandardButton.Close)
        self.close_button.setText(self.i18n.text("button.close"))
        self.run_button.setProperty("role", "primary")
        self.retry_button.clicked.connect(self._retry)
        self.edit_button.clicked.connect(self._request_edit)
        self.run_button.clicked.connect(self.accept)
        self.close_button.clicked.connect(self.reject)

        details_row = QHBoxLayout()
        details_row.addWidget(self.details_button)
        details_row.addStretch(1)

        layout = QVBoxLayout(self)
        layout.addWidget(heading)
        layout.addWidget(description)
        layout.addSpacing(8)
        layout.addLayout(self.steps_layout)
        layout.addSpacing(8)
        layout.addWidget(self.action_label)
        layout.addLayout(details_row)
        layout.addWidget(self.details)
        layout.addStretch(1)
        layout.addWidget(self.buttons)
        self._render()

    def _render(self) -> None:
        for index, (_, state_label, text_label) in enumerate(self.step_widgets):
            step = self.report.steps[index]
            if step.state == CheckState.PASSED:
                marker, color = "✓", "#2e7d32"
            elif step.state == CheckState.FAILED:
                marker, color = "!", "#b3261e"
            else:
                marker, color = "—", "#737373"
            state_label.setText(marker)
            state_label.setStyleSheet(f"font-weight: 700; color: {color};")
            title = self.i18n.text(f"{self.prefix}.step.{step.key}")
            summary, _ = preflight_step_text(self.i18n, self.report.kind, step)
            text_label.setText(f"<b>{title}</b><br>{summary}")

        failed = self.report.failed_step
        if failed is None:
            self.action_label.setText(self.i18n.text(f"{self.prefix}.all_passed"))
            details = "\n\n".join(step.details for step in self.report.steps if step.details)
        else:
            _, next_action = preflight_step_text(self.i18n, self.report.kind, failed)
            self.action_label.setText(
                f"<b>{self.i18n.text('preflight.next_step')}</b><br>{next_action}"
            )
            technical = [failed.details]
            if failed.summary:
                technical.append(
                    f"{self.i18n.text('preflight.detail_summary')} {failed.summary}"
                )
            if failed.next_action:
                technical.append(
                    f"{self.i18n.text('preflight.detail_action')} {failed.next_action}"
                )
            details = "\n\n".join(value for value in technical if value)
        self.details.setPlainText(details)
        self.details_button.setVisible(bool(details))
        if not details:
            self.details_button.setChecked(False)
        self.retry_button.setVisible(not self.report.ready)
        self.edit_button.setVisible(not self.report.ready)
        self.run_button.setVisible(self.report.ready)

    def _toggle_details(self, visible: bool) -> None:
        self.details.setVisible(visible)
        self.details_button.setText(
            self.i18n.text(
                "preflight.hide_details" if visible else "preflight.show_details"
            )
        )

    def _retry(self) -> None:
        self.retry_button.setEnabled(False)
        self.action_label.setText(self.i18n.text(f"{self.prefix}.checking"))
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        QApplication.processEvents()
        try:
            self.report = self.check_again()
        finally:
            QApplication.restoreOverrideCursor()
            self.retry_button.setEnabled(True)
        self._render()

    def _request_edit(self) -> None:
        self.edit_requested = True
        self.reject()


__all__ = ["MaaPreflightDialog"]
