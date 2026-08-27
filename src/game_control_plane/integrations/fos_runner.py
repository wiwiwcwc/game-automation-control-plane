from __future__ import annotations

import argparse
import ctypes
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, Protocol, Sequence


FOS_SUCCESS_MARKERS = ("所有任务都已完成", "All tasks have been completed")
FOS_FAILURE_MARKERS = (
    "任务流程执行异常",
    "Task flow error",
    "执行失败",
    "TASK_FLOW_STOP manual=True",
)
DEFAULT_POLL_SECONDS = 0.25
DEFAULT_START_TIMEOUT_SECONDS = 300.0
FOS_LOG_FORWARD_MARKERS = (
    "[RUN_RECORD]",
    "执行任务:",
    "设备连接成功",
    "所有任务都已完成",
    "执行失败",
    "task_flow_finished:",
    "收到停止请求",
    "Task flow error",
)


class ProcessHandle(Protocol):
    def poll(self) -> int | None:
        ...

    def terminate(self) -> None:
        ...

    def wait(self, timeout: float | None = None) -> int:
        ...

    def kill(self) -> None:
        ...


def _emit(message: str, *, error: bool = False, end: str = "\n") -> None:
    stream = sys.stderr if error else sys.stdout
    if stream is not None:
        print(message, file=stream, end=end, flush=True)
        return
    try:
        os.write(2 if error else 1, f"{message}{end}".encode("utf-8", errors="replace"))
    except OSError:
        pass


def classify_fos_log_text(text: str) -> tuple[str | None, str]:
    for marker in FOS_FAILURE_MARKERS:
        if marker in text:
            return "failure", marker
    if "task_flow_finished:" in text:
        if "'manual_stop': True" in text or "'need_stop': True" in text:
            return "failure", "FOS reported that the task flow stopped."
    if (
        "[RUN_RECORD] TASK_FLOW_START" in text
        and any(marker in text for marker in FOS_SUCCESS_MARKERS)
        and "task_flow_finished:" in text
        and "'manual_stop': False" in text
        and "'need_stop': False" in text
        and "'tasks_started': True" in text
        and "[RUN_RECORD] TASK_FLOW_STOP manual=False" in text
    ):
        return "success", "FOS recorded a complete successful task flow."
    return None, ""


def summarize_fos_log_text(text: str) -> str:
    return "\n".join(
        line
        for line in text.splitlines()
        if any(marker in line for marker in FOS_LOG_FORWARD_MARKERS)
    )


class FosRunEvidence:
    def __init__(self):
        self.started = False
        self.completion_message = False
        self.clean_finished = False
        self.clean_stop = False

    def consume(self, text: str) -> tuple[str | None, str]:
        failure, detail = classify_fos_log_text(text)
        if failure == "failure":
            return failure, detail
        if "[RUN_RECORD] TASK_FLOW_START" in text:
            self.started = True
        if any(marker in text for marker in FOS_SUCCESS_MARKERS):
            self.completion_message = True
        if (
            "task_flow_finished:" in text
            and "'manual_stop': False" in text
            and "'need_stop': False" in text
            and "'tasks_started': True" in text
        ):
            self.clean_finished = True
        if "[RUN_RECORD] TASK_FLOW_STOP manual=False" in text:
            self.clean_stop = True
        if self.started and self.completion_message and self.clean_finished and self.clean_stop:
            return "success", "FOS recorded a complete successful task flow."
        return None, ""


class FosLogFollower:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        stat = self.path.stat() if self.path.is_file() else None
        self.offset = stat.st_size if stat is not None else 0
        self.identity = (stat.st_dev, stat.st_ino) if stat is not None else None
        self._pending = ""

    def read_new_text(self) -> str:
        if not self.path.is_file():
            return ""
        stat = self.path.stat()
        identity = (stat.st_dev, stat.st_ino)
        size = stat.st_size
        if self.identity is not None and identity != self.identity:
            self.offset = 0
            self._pending = ""
        self.identity = identity
        if size < self.offset:
            self.offset = 0
            self._pending = ""
        if size == self.offset:
            return ""
        with self.path.open("rb") as stream:
            stream.seek(self.offset)
            data = stream.read()
            self.offset = stream.tell()
        text = self._pending + data.decode("utf-8", errors="replace")
        lines = text.splitlines(keepends=True)
        if lines and not lines[-1].endswith(("\n", "\r")):
            self._pending = lines.pop()
        else:
            self._pending = ""
        return "".join(lines)


def run_fos_automation(
    fos_executable: str | Path,
    config_id: str,
    *,
    log_path: str | Path | None = None,
    popen_factory: Callable[[Sequence[str], Path], ProcessHandle] | None = None,
    sleeper: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
    poll_seconds: float = DEFAULT_POLL_SECONDS,
    start_timeout_seconds: float = DEFAULT_START_TIMEOUT_SECONDS,
    close_fos_after_run: bool = False,
    process_closer: Callable[[Path, ProcessHandle], bool] | None = None,
) -> int:
    fos_path = Path(fos_executable).expanduser().resolve()
    root = fos_path.parent
    gui_log = Path(log_path) if log_path is not None else root / "debug" / "gui.log"
    follower = FosLogFollower(gui_log)
    command = (
        str(fos_path),
        "--direct-run",
        "--reuse-existing",
        "--config-id",
        config_id,
    )

    def default_popen(values: Sequence[str], cwd: Path) -> ProcessHandle:
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        return subprocess.Popen(
            list(values),
            cwd=str(cwd),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
        )

    launcher = (popen_factory or default_popen)(command, root)
    evidence = FosRunEvidence()
    requested_at = monotonic()
    _emit(f"[Control Plane] FOS request: {' '.join(command[1:])}")
    launcher_exit: int | None = None
    while True:
        text = follower.read_new_text()
        if text:
            summary = summarize_fos_log_text(text)
            if summary:
                _emit(summary)
            outcome, detail = evidence.consume(text)
            if outcome == "success":
                _emit(f"[Control Plane] FOS completed: {detail}")
                if close_fos_after_run:
                    closer = process_closer or _close_fos_process
                    if not closer(fos_path, launcher):
                        _emit(
                            "[Control Plane] FOS completed, but its process could not be closed.",
                            error=True,
                        )
                        return 24
                    _emit("[Control Plane] Closed the associated FOS process.")
                return 0
            if outcome == "failure":
                _emit(f"[Control Plane] FOS failed: {detail}", error=True)
                return 20

        if launcher_exit is None:
            launcher_exit = launcher.poll()
            if launcher_exit not in (None, 0):
                _emit(
                    f"[Control Plane] FOS rejected or failed to start (exit {launcher_exit}).",
                    error=True,
                )
                return int(launcher_exit)
            if launcher_exit == 0:
                elapsed = monotonic() - requested_at
                if evidence.started or elapsed >= 5.0:
                    _emit(
                        "[Control Plane] The active FOS process exited before a complete task result.",
                        error=True,
                    )
                    return 22
        if not evidence.started and monotonic() - requested_at >= start_timeout_seconds:
            _emit(
                "[Control Plane] FOS did not start the requested task flow before the timeout.",
                error=True,
            )
            return 23
        sleeper(max(0.01, poll_seconds))


def run_fos_runner_cli(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--fos-executable", required=True)
    parser.add_argument("--config-id", required=True)
    parser.add_argument("--close-fos-after-run", action="store_true")
    values = parser.parse_args(argv)
    try:
        return run_fos_automation(
            values.fos_executable,
            values.config_id,
            close_fos_after_run=values.close_fos_after_run,
        )
    except OSError as exc:
        _emit(f"[Control Plane] Could not start or monitor FOS: {exc}", error=True)
        return 21


__all__ = [
    "FosLogFollower",
    "FosRunEvidence",
    "classify_fos_log_text",
    "run_fos_automation",
    "run_fos_runner_cli",
    "summarize_fos_log_text",
]


def _close_fos_process(fos_path: Path, launcher: ProcessHandle) -> bool:
    """Close only the launched FOS process or an exact-path reused instance."""

    if launcher.poll() is None:
        try:
            launcher.terminate()
            launcher.wait(timeout=10.0)
            return True
        except subprocess.TimeoutExpired:
            try:
                launcher.kill()
                launcher.wait(timeout=5.0)
                return True
            except (OSError, subprocess.TimeoutExpired):
                return False
        except OSError:
            return False
    return _terminate_exact_windows_image(fos_path)


def _terminate_exact_windows_image(fos_path: Path) -> bool:
    if os.name != "nt":
        return False

    toolhelp_snapshot = 0x00000002
    process_terminate = 0x0001
    process_query = 0x1000
    invalid_handle = ctypes.c_void_p(-1).value

    class ProcessEntry32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", ctypes.c_ulong),
            ("cntUsage", ctypes.c_ulong),
            ("th32ProcessID", ctypes.c_ulong),
            ("th32DefaultHeapID", ctypes.c_void_p),
            ("th32ModuleID", ctypes.c_ulong),
            ("cntThreads", ctypes.c_ulong),
            ("th32ParentProcessID", ctypes.c_ulong),
            ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", ctypes.c_ulong),
            ("szExeFile", ctypes.c_wchar * 260),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateToolhelp32Snapshot.argtypes = [ctypes.c_ulong, ctypes.c_ulong]
    kernel32.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
    kernel32.Process32FirstW.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ProcessEntry32W),
    ]
    kernel32.Process32FirstW.restype = ctypes.c_bool
    kernel32.Process32NextW.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ProcessEntry32W),
    ]
    kernel32.Process32NextW.restype = ctypes.c_bool
    kernel32.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_bool, ctypes.c_ulong]
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.QueryFullProcessImageNameW.argtypes = [
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.POINTER(ctypes.c_wchar),
        ctypes.POINTER(ctypes.c_ulong),
    ]
    kernel32.QueryFullProcessImageNameW.restype = ctypes.c_bool
    kernel32.TerminateProcess.argtypes = [ctypes.c_void_p, ctypes.c_uint]
    kernel32.TerminateProcess.restype = ctypes.c_bool
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel32.CloseHandle.restype = ctypes.c_bool
    target = os.path.normcase(os.path.abspath(fos_path))
    snapshot = kernel32.CreateToolhelp32Snapshot(toolhelp_snapshot, 0)
    if not snapshot or snapshot == invalid_handle:
        return False
    matched = False
    succeeded = True
    try:
        entry = ProcessEntry32W()
        entry.dwSize = ctypes.sizeof(entry)
        has_entry = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
        while has_entry:
            if int(entry.th32ProcessID) != os.getpid() and str(entry.szExeFile).casefold() == "fos.exe":
                handle = kernel32.OpenProcess(
                    process_terminate | process_query,
                    False,
                    int(entry.th32ProcessID),
                )
                if handle:
                    try:
                        buffer = ctypes.create_unicode_buffer(32768)
                        size = ctypes.c_ulong(len(buffer))
                        if kernel32.QueryFullProcessImageNameW(
                            handle, 0, buffer, ctypes.byref(size)
                        ) and os.path.normcase(os.path.abspath(buffer.value)) == target:
                            matched = True
                            if not kernel32.TerminateProcess(handle, 0):
                                succeeded = False
                    finally:
                        kernel32.CloseHandle(handle)
            has_entry = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snapshot)
    return matched and succeeded
