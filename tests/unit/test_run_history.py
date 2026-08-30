from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtWidgets import QApplication

from game_control_plane.domain.models import Run, RunState
from game_control_plane.ui.run_log_dialog import RunHistoryDialog, _read_log, concise_error
from game_control_plane.ui.i18n import LanguageManager


_APP: QApplication | None = None


def app_instance() -> QApplication:
    global _APP
    _APP = QApplication.instance() or QApplication([])
    return _APP


def make_run(tmp_path: Path, identifier: str, started: str, state: RunState, error: str | None = None) -> Run:
    run_dir = tmp_path / identifier
    run_dir.mkdir()
    stdout = run_dir / "stdout.log"
    stderr = run_dir / "stderr.log"
    stdout.write_text(f"stdout for {identifier}", encoding="utf-8")
    stderr.write_text(f"stderr for {identifier}", encoding="utf-8")
    started_at = datetime.fromisoformat(started)
    finished_at = started_at.replace(microsecond=500000)
    return Run(
        id=identifier,
        job_id=1,
        trigger_type="manual",
        state=state,
        started_at_utc=started,
        finished_at_utc=finished_at.isoformat(),
        exit_code=1 if state == RunState.FAILED else 0,
        exit_status="normal",
        error_kind="nonzero_exit" if state == RunState.FAILED else None,
        error_summary=error,
        stdout_path=str(stdout),
        stderr_path=str(stderr),
        launch_snapshot_json="{}",
        created_at_utc=started,
    )


def test_history_sorts_latest_first_and_selects_logs(tmp_path: Path):
    app_instance()
    older = make_run(tmp_path, "older", "2026-08-20T10:00:00+00:00", RunState.EXITED)
    latest = make_run(
        tmp_path,
        "latest",
        "2026-08-24T10:00:00+00:00",
        RunState.FAILED,
        "first line\nsecond line",
    )
    dialog = RunHistoryDialog(
        "Game · Daily",
        [older, latest],
        i18n=LanguageManager("en_US", persist=False),
    )
    assert dialog.history_table.rowCount() == 2
    assert dialog.selected_run and dialog.selected_run.id == "latest"
    assert dialog.history_table.item(0, 1).text() == "Failed"
    assert "Duration:" in dialog.summary.text()
    assert "stdout for latest" in dialog.stdout.toPlainText()
    assert "stderr for latest" in dialog.stderr.toPlainText()
    assert dialog.technical.toPlainText() == "first line\nsecond line"

    dialog.i18n.set_language("zh_CN")
    assert dialog.history_table.item(0, 1).text() == "运行失败"
    assert dialog.technical.toPlainText() == "first line\nsecond line"

    dialog.history_table.setCurrentCell(1, 0)
    app_instance().processEvents()
    assert dialog.selected_run and dialog.selected_run.id == "older"
    assert "stdout for older" in dialog.stdout.toPlainText()
    dialog.close()


def test_history_limits_to_50_and_shortens_errors(tmp_path: Path):
    app_instance()
    runs = [
        make_run(
            tmp_path,
            f"run-{index:02d}",
            f"2026-08-{24 - index // 24:02d}T{index % 24:02d}:00:00+00:00",
            RunState.FAILED,
            "x" * 200,
        )
        for index in range(51)
    ]
    dialog = RunHistoryDialog(
        "Game · Daily",
        runs,
        i18n=LanguageManager("en_US", persist=False),
    )
    assert dialog.history_table.rowCount() == 50
    assert len(concise_error("x" * 200)) == 120
    assert dialog.history_table.item(0, 4).text().startswith(
        "The external program exited unexpectedly"
    )
    assert dialog.technical.toPlainText() == "x" * 200
    dialog.close()


def test_log_preview_reads_only_the_tail_of_large_files(tmp_path: Path):
    path = tmp_path / "large.log"
    path.write_bytes(b"discard-me\n" + b"x" * 128 + b"tail-marker")
    preview = _read_log(str(path), max_bytes=32)
    assert preview.startswith("[Showing the last 32 bytes of this log.]")
    assert "discard-me" not in preview
    assert "tail-marker" in preview
