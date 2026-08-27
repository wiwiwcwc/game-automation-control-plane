from __future__ import annotations

from PySide6.QtWidgets import QApplication

from game_control_plane.integrations.maa_preflight import (
    CheckState,
    CheckStep,
    MaaPreflightReport,
)
from game_control_plane.ui.maa_preflight_dialog import MaaPreflightDialog


_APP: QApplication | None = None


def app_instance() -> QApplication:
    global _APP
    _APP = QApplication.instance() or QApplication([])
    return _APP


def failed_report() -> MaaPreflightReport:
    return MaaPreflightReport(
        (
            CheckStep("executable", "MAA program", CheckState.PASSED, "Ready"),
            CheckStep(
                "task",
                "MAA task",
                CheckState.FAILED,
                "Task missing",
                "Open Edit and choose daily.",
                "Available: daily",
            ),
            CheckStep("dry_run", "Task configuration", CheckState.PENDING, "Waiting"),
            CheckStep("adb", "Emulator connection", CheckState.PENDING, "Waiting"),
        )
    )


def passed_report() -> MaaPreflightReport:
    return MaaPreflightReport(
        tuple(
            CheckStep(key, title, CheckState.PASSED, "Ready")
            for key, title in (
                ("executable", "MAA program"),
                ("task", "MAA task"),
                ("dry_run", "Task configuration"),
                ("adb", "Emulator connection"),
            )
        )
    )


def test_dialog_shows_next_step_and_retry_can_reach_ready_state():
    app_instance()
    dialog = MaaPreflightDialog(failed_report(), passed_report)

    assert "Open Edit" in dialog.action_label.text()
    assert dialog.retry_button.isVisibleTo(dialog)
    assert not dialog.run_button.isVisibleTo(dialog)
    dialog._retry()

    assert dialog.report.ready
    assert dialog.run_button.isVisibleTo(dialog)
    assert not dialog.retry_button.isVisibleTo(dialog)
    dialog.close()
