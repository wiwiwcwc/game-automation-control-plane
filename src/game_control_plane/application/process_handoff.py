from __future__ import annotations

import ctypes
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


DEFAULT_WORKER_PROCESS_NAMES = ("pythonw.exe", "python.exe")
DEFAULT_HANDOFF_GRACE_SECONDS = 2.0
DEFAULT_HANDOFF_POLL_INTERVAL_MS = 50


class WorkerProcess(Protocol):
    pid: int

    def poll_exit_code(self) -> int | None:
        """Return the exit code once the worker has exited, else None."""

    def close(self) -> None:
        """Release the held process handle."""


class WorkerLocator(Protocol):
    def find_worker(
        self,
        launcher_pid: int,
        launcher_executable: str,
        process_names: tuple[str, ...],
    ) -> WorkerProcess | None:
        """Find one trusted worker child of the launcher, if present."""


class NullWorkerLocator:
    def find_worker(
        self,
        launcher_pid: int,
        launcher_executable: str,
        process_names: tuple[str, ...],
    ) -> WorkerProcess | None:
        return None


class HandoffTracker:
    """Discover and hold one worker process while a launcher hands off to it."""

    def __init__(
        self,
        locator: WorkerLocator,
        launcher_pid: int,
        launcher_executable: str,
        process_names: tuple[str, ...] = DEFAULT_WORKER_PROCESS_NAMES,
    ):
        self.locator = locator
        self.launcher_pid = launcher_pid
        self.launcher_executable = launcher_executable
        self.process_names = tuple(name.casefold() for name in process_names)
        self.worker: WorkerProcess | None = None
        self.worker_exit_code: int | None = None

    @property
    def worker_seen(self) -> bool:
        return self.worker is not None or self.worker_exit_code is not None

    def poll(self) -> int | None:
        if self.worker is None and self.worker_exit_code is None:
            self.worker = self.locator.find_worker(
                self.launcher_pid,
                self.launcher_executable,
                self.process_names,
            )
        if self.worker is None:
            return self.worker_exit_code
        exit_code = self.worker.poll_exit_code()
        if exit_code is None:
            return None
        self.worker_exit_code = exit_code
        self.worker.close()
        self.worker = None
        return exit_code

    def close(self) -> None:
        if self.worker is None:
            return
        try:
            self.worker.close()
        finally:
            self.worker = None


@dataclass(frozen=True)
class ProcessOutcome:
    exit_code: int
    crashed: bool = False
    error_message: str | None = None


class HandoffCoordinator:
    """Apply the launcher/worker race and grace-period policy."""

    def __init__(self, tracker: HandoffTracker, grace_seconds: float):
        self.tracker = tracker
        self.grace_seconds = grace_seconds
        self.parent_outcome: ProcessOutcome | None = None
        self.deadline: float | None = None

    def parent_finished(self, outcome: ProcessOutcome, now: float) -> ProcessOutcome | None:
        self.parent_outcome = outcome
        return self.poll(now)

    def poll(self, now: float) -> ProcessOutcome | None:
        self.tracker.poll()
        worker_code = self.tracker.worker_exit_code
        if worker_code is not None and self.parent_outcome is not None:
            return ProcessOutcome(exit_code=worker_code)
        if self.parent_outcome is None:
            return None
        if self.tracker.worker_seen:
            return None
        if self.deadline is None:
            self.deadline = now + self.grace_seconds
        if now >= self.deadline:
            return self.parent_outcome
        return None

    def close(self) -> None:
        self.tracker.close()


def _is_child_image_under_launcher(
    image_path: str,
    launcher_executable: str,
    process_names: tuple[str, ...],
) -> bool:
    image_name = Path(image_path).name.casefold()
    if image_name not in process_names:
        return False
    try:
        launcher_root = os.path.normcase(
            os.path.abspath(os.fspath(Path(launcher_executable).parent))
        )
        candidate = os.path.normcase(os.path.abspath(image_path))
        return os.path.commonpath((launcher_root, candidate)) == launcher_root
    except (OSError, ValueError):
        return False


if os.name == "nt":
    _TH32CS_SNAPPROCESS = 0x00000002
    _PROCESS_QUERY_LIMITED_INFORMATION = 0x00001000
    _SYNCHRONIZE = 0x00100000
    _WAIT_OBJECT_0 = 0x00000000
    _WAIT_TIMEOUT = 0x00000102
    _INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

    class _ProcessEntry32W(ctypes.Structure):
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

    class _WindowsWorkerProcess:
        def __init__(self, kernel32, pid: int, handle, image_path: str):
            self.kernel32 = kernel32
            self.pid = pid
            self.handle = handle
            self.image_path = image_path

        def poll_exit_code(self) -> int | None:
            wait_result = self.kernel32.WaitForSingleObject(self.handle, 0)
            if wait_result == _WAIT_TIMEOUT:
                return None
            if wait_result != _WAIT_OBJECT_0:
                return None
            exit_code = ctypes.c_ulong()
            if not self.kernel32.GetExitCodeProcess(
                self.handle,
                ctypes.byref(exit_code),
            ):
                return None
            return int(exit_code.value)

        def close(self) -> None:
            if self.handle:
                self.kernel32.CloseHandle(self.handle)
                self.handle = None

    class WindowsWorkerLocator:
        """Locate only direct python/pythonw children inside the OK-WW folder."""

        def __init__(self):
            self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            self.kernel32.CreateToolhelp32Snapshot.argtypes = [
                ctypes.c_ulong,
                ctypes.c_ulong,
            ]
            self.kernel32.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
            self.kernel32.Process32FirstW.argtypes = [
                ctypes.c_void_p,
                ctypes.POINTER(_ProcessEntry32W),
            ]
            self.kernel32.Process32NextW.argtypes = [
                ctypes.c_void_p,
                ctypes.POINTER(_ProcessEntry32W),
            ]
            self.kernel32.OpenProcess.argtypes = [
                ctypes.c_ulong,
                ctypes.c_bool,
                ctypes.c_ulong,
            ]
            self.kernel32.OpenProcess.restype = ctypes.c_void_p
            self.kernel32.QueryFullProcessImageNameW.argtypes = [
                ctypes.c_void_p,
                ctypes.c_ulong,
                ctypes.POINTER(ctypes.c_wchar),
                ctypes.POINTER(ctypes.c_ulong),
            ]
            self.kernel32.QueryFullProcessImageNameW.restype = ctypes.c_bool
            self.kernel32.WaitForSingleObject.argtypes = [
                ctypes.c_void_p,
                ctypes.c_ulong,
            ]
            self.kernel32.WaitForSingleObject.restype = ctypes.c_ulong
            self.kernel32.GetExitCodeProcess.argtypes = [
                ctypes.c_void_p,
                ctypes.POINTER(ctypes.c_ulong),
            ]
            self.kernel32.GetExitCodeProcess.restype = ctypes.c_bool
            self.kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
            self.kernel32.CloseHandle.restype = ctypes.c_bool

        def _processes(self) -> list[tuple[int, int, str]]:
            snapshot = self.kernel32.CreateToolhelp32Snapshot(_TH32CS_SNAPPROCESS, 0)
            if not snapshot or snapshot == _INVALID_HANDLE_VALUE:
                return []
            try:
                entry = _ProcessEntry32W()
                entry.dwSize = ctypes.sizeof(entry)
                result: list[tuple[int, int, str]] = []
                if not self.kernel32.Process32FirstW(
                    snapshot,
                    ctypes.byref(entry),
                ):
                    return result
                while True:
                    result.append(
                        (
                            int(entry.th32ProcessID),
                            int(entry.th32ParentProcessID),
                            str(entry.szExeFile),
                        )
                    )
                    if not self.kernel32.Process32NextW(
                        snapshot,
                        ctypes.byref(entry),
                    ):
                        break
                return result
            finally:
                self.kernel32.CloseHandle(snapshot)

        def _image_path(self, handle) -> str | None:
            buffer = ctypes.create_unicode_buffer(32768)
            size = ctypes.c_ulong(len(buffer))
            if not self.kernel32.QueryFullProcessImageNameW(
                handle,
                0,
                buffer,
                ctypes.byref(size),
            ):
                return None
            return buffer.value

        def find_worker(
            self,
            launcher_pid: int,
            launcher_executable: str,
            process_names: tuple[str, ...],
        ):
            access = _SYNCHRONIZE | _PROCESS_QUERY_LIMITED_INFORMATION
            for pid, parent_pid, exe_name in self._processes():
                if parent_pid != launcher_pid or exe_name.casefold() not in process_names:
                    continue
                handle = self.kernel32.OpenProcess(access, False, pid)
                if not handle:
                    continue
                image_path = self._image_path(handle)
                if image_path and _is_child_image_under_launcher(
                    image_path,
                    launcher_executable,
                    process_names,
                ):
                    return _WindowsWorkerProcess(self.kernel32, pid, handle, image_path)
                self.kernel32.CloseHandle(handle)
            return None

else:

    class WindowsWorkerLocator(NullWorkerLocator):
        """Safe no-op on non-Windows hosts."""


def default_worker_locator() -> WorkerLocator:
    return WindowsWorkerLocator() if os.name == "nt" else NullWorkerLocator()


__all__ = [
    "HandoffCoordinator",
    "HandoffTracker",
    "DEFAULT_HANDOFF_GRACE_SECONDS",
    "DEFAULT_HANDOFF_POLL_INTERVAL_MS",
    "NullWorkerLocator",
    "ProcessOutcome",
    "WorkerLocator",
    "WorkerProcess",
    "WindowsWorkerLocator",
    "default_worker_locator",
]
