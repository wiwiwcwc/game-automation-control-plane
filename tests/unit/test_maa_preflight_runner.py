from __future__ import annotations

import time

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from game_control_plane.integrations.maa_preflight import (
    CheckState,
    CheckStep,
    MaaPreflightReport,
)
from game_control_plane.ui import maa_preflight_runner


_APP: QApplication | None = None


def app_instance() -> QApplication:
    global _APP
    _APP = QApplication.instance() or QApplication([])
    return _APP


def test_worker_keeps_qt_event_loop_responsive(monkeypatch):
    app_instance()
    report = MaaPreflightReport(
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

    def fake_preflight(config, progress):
        progress("Starting emulator…")
        time.sleep(0.1)
        return report

    monkeypatch.setattr(maa_preflight_runner, "run_maa_preflight", fake_preflight)
    event_loop_ticks: list[bool] = []
    QTimer.singleShot(10, lambda: event_loop_ticks.append(True))

    result, error = maa_preflight_runner.run_preflight_with_progress({})

    assert error is None
    assert result == report
    assert event_loop_ticks == [True]


def test_worker_exception_closes_dialog_and_returns_error(monkeypatch):
    app_instance()

    def broken_preflight(config, progress):
        raise RuntimeError("probe failed")

    monkeypatch.setattr(maa_preflight_runner, "run_maa_preflight", broken_preflight)

    result, error = maa_preflight_runner.run_preflight_with_progress({})

    assert result is None
    assert error == "probe failed"
