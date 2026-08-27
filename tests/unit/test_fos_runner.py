from __future__ import annotations

from pathlib import Path

from game_control_plane.integrations.fos_runner import (
    FosLogFollower,
    FosRunEvidence,
    classify_fos_log_text,
    run_fos_automation,
    summarize_fos_log_text,
)


class FakeProcess:
    def __init__(self, exit_code=None):
        self.exit_code = exit_code
        self.terminated = False

    def poll(self):
        return self.exit_code

    def terminate(self):
        self.terminated = True
        self.exit_code = 0

    def wait(self, timeout=None):
        return int(self.exit_code or 0)

    def kill(self):
        self.terminate()


def test_log_classifier_distinguishes_success_stop_and_noise():
    assert classify_fos_log_text("[INFO] 所有任务都已完成") == (None, "")
    assert classify_fos_log_text("任务 '每日' 执行失败")[0] == "failure"
    assert classify_fos_log_text("task_flow_finished: {'manual_stop': True}")[0] == "failure"
    assert classify_fos_log_text("设备连接成功") == (None, "")


def test_completion_requires_the_full_high_level_fos_evidence_sequence():
    evidence = FosRunEvidence()
    assert evidence.consume("[RUN_RECORD] TASK_FLOW_START") == (None, "")
    assert evidence.consume("[INFO] 所有任务都已完成") == (None, "")
    assert evidence.consume(
        "task_flow_finished: {'manual_stop': False, 'need_stop': False, 'tasks_started': True}"
    ) == (None, "")
    assert evidence.consume("[RUN_RECORD] TASK_FLOW_STOP manual=False")[0] == "success"


def test_log_forwarding_drops_large_debug_noise_but_keeps_progress():
    text = "huge numpy array [[1, 2]]\n[INFO] 执行任务: 启动\nrandom debug\n"
    assert summarize_fos_log_text(text) == "[INFO] 执行任务: 启动"


def test_log_follower_reads_only_content_appended_after_creation(tmp_path: Path):
    log = tmp_path / "gui.log"
    log.write_text("old success 所有任务都已完成\n", encoding="utf-8")
    follower = FosLogFollower(log)
    assert follower.read_new_text() == ""
    with log.open("a", encoding="utf-8") as stream:
        stream.write("new line\n")
    assert follower.read_new_text().splitlines() == ["new line"]


def test_log_follower_waits_for_a_complete_line(tmp_path: Path):
    log = tmp_path / "gui.log"
    log.write_text("", encoding="utf-8")
    follower = FosLogFollower(log)
    with log.open("a", encoding="utf-8") as stream:
        stream.write("[RUN_RECORD] TASK_FLOW_")
    assert follower.read_new_text() == ""
    with log.open("a", encoding="utf-8") as stream:
        stream.write("START\n")
    assert "TASK_FLOW_START" in follower.read_new_text()


def test_runner_waits_for_new_fos_completion_marker(tmp_path: Path):
    fos = tmp_path / "FOS.exe"
    fos.touch()
    log = tmp_path / "debug" / "gui.log"
    log.parent.mkdir()
    log.write_text("", encoding="utf-8")
    calls = []

    def popen(command, cwd):
        calls.append((tuple(command), cwd))
        return FakeProcess(None)

    def sleep(_seconds):
        if log.stat().st_size == 0:
            with log.open("a", encoding="utf-8") as stream:
                stream.write(
                    "[RUN_RECORD] TASK_FLOW_START\n"
                    "[INFO] 所有任务都已完成\n"
                    "task_flow_finished: {'manual_stop': False, 'need_stop': False, "
                    "'tasks_started': True}\n"
                    "[RUN_RECORD] TASK_FLOW_STOP manual=False\n"
                )

    assert run_fos_automation(
        fos,
        "c_daily",
        log_path=log,
        popen_factory=popen,
        sleeper=sleep,
        poll_seconds=0.01,
    ) == 0
    assert calls[0][0][1:] == (
        "--direct-run",
        "--reuse-existing",
        "--config-id",
        "c_daily",
    )


def test_runner_surfaces_rejected_reuse_request(tmp_path: Path):
    fos = tmp_path / "FOS.exe"
    fos.touch()
    assert run_fos_automation(
        fos,
        "c_daily",
        popen_factory=lambda _command, _cwd: FakeProcess(2),
        sleeper=lambda _seconds: None,
        poll_seconds=0.01,
    ) == 2


def test_runner_closes_fos_only_after_complete_success(tmp_path: Path):
    fos = tmp_path / "FOS.exe"
    fos.touch()
    log = tmp_path / "debug" / "gui.log"
    log.parent.mkdir()
    log.write_text("", encoding="utf-8")
    close_calls = []

    def sleep(_seconds):
        if log.stat().st_size == 0:
            log.write_text(
                "[RUN_RECORD] TASK_FLOW_START\n"
                "[INFO] 所有任务都已完成\n"
                "task_flow_finished: {'manual_stop': False, 'need_stop': False, "
                "'tasks_started': True}\n"
                "[RUN_RECORD] TASK_FLOW_STOP manual=False\n",
                encoding="utf-8",
            )

    result = run_fos_automation(
        fos,
        "c_daily",
        log_path=log,
        popen_factory=lambda _command, _cwd: FakeProcess(None),
        sleeper=sleep,
        poll_seconds=0.01,
        close_fos_after_run=True,
        process_closer=lambda path, process: close_calls.append((path, process)) or True,
    )

    assert result == 0
    assert len(close_calls) == 1
    assert close_calls[0][0] == fos.resolve()


def test_runner_reports_requested_fos_close_failure(tmp_path: Path):
    fos = tmp_path / "FOS.exe"
    fos.touch()
    log = tmp_path / "debug" / "gui.log"
    log.parent.mkdir()
    log.write_text("", encoding="utf-8")

    def sleep(_seconds):
        if log.stat().st_size == 0:
            log.write_text(
                "[RUN_RECORD] TASK_FLOW_START\n"
                "[INFO] All tasks have been completed\n"
                "task_flow_finished: {'manual_stop': False, 'need_stop': False, "
                "'tasks_started': True}\n"
                "[RUN_RECORD] TASK_FLOW_STOP manual=False\n",
                encoding="utf-8",
            )

    assert run_fos_automation(
        fos,
        "c_daily",
        log_path=log,
        popen_factory=lambda _command, _cwd: FakeProcess(None),
        sleeper=sleep,
        poll_seconds=0.01,
        close_fos_after_run=True,
        process_closer=lambda _path, _process: False,
    ) == 24
