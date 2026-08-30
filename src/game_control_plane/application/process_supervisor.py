from __future__ import annotations

import ctypes
import logging
import os
import signal
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Protocol


@dataclass(frozen=True)
class ProcessIdentity:
    """The identity captured for one process owned by a Hsiesta run."""

    pid: int
    executable: str
    token: str
    creation_time: int | None = None


@dataclass(frozen=True)
class ProcessTerminationResult:
    success: bool
    attempted_pids: tuple[int, ...] = ()
    failed_pids: tuple[int, ...] = ()
    summary: str = ""


class ProcessSupervisor(Protocol):
    def capture(self, pid: int, expected_executable: str) -> ProcessIdentity | None:
        """Capture a PID only when its current image matches the expected path."""

    def verify(self, identity: ProcessIdentity) -> bool:
        """Verify that the PID still represents the captured process."""

    def terminate_tree(self, identity: ProcessIdentity) -> ProcessTerminationResult:
        """Terminate only the verified process and its current descendants."""


def _normal_path(value: str | Path) -> str:
    try:
        return os.path.normcase(os.path.abspath(os.fspath(value)))
    except (OSError, TypeError, ValueError):
        return ""


def _same_path(left: str | Path, right: str | Path) -> bool:
    normalized_left = _normal_path(left)
    normalized_right = _normal_path(right)
    return bool(normalized_left and normalized_left == normalized_right)


def _descendant_pids(
    entries: Iterable[tuple[int, int]],
    root_pid: int,
) -> tuple[int, ...]:
    """Return only current descendants of one exact root PID.

    This deliberately uses parent-PID relationships from a point-in-time
    snapshot. It never searches by executable name, and the cycle guard keeps
    malformed snapshots from escaping the owned tree.
    """

    parent_map: dict[int, list[int]] = {}
    for pid, parent_pid in entries:
        parent_map.setdefault(parent_pid, []).append(pid)
    descendants: list[int] = []
    pending = list(parent_map.get(root_pid, ()))
    seen = {root_pid}
    while pending:
        pid = pending.pop(0)
        if pid in seen:
            continue
        seen.add(pid)
        descendants.append(pid)
        pending.extend(parent_map.get(pid, ()))
    return tuple(descendants)


@dataclass(frozen=True)
class _SnapshotProcess:
    """One process in a validated point-in-time parent tree."""

    pid: int
    parent_pid: int
    ancestry: tuple[int, ...]


def _trusted_tree_snapshot(
    entries: Iterable[tuple[int, int]],
    root_pid: int,
) -> tuple[_SnapshotProcess, ...] | None:
    """Build one exact root tree, rejecting malformed parent relationships.

    Toolhelp snapshots normally contain every PID once.  Treating duplicates,
    cycles, or a child that cannot be reached from the requested root as an
    invalid snapshot is important here: a stop operation must never turn an
    ambiguous parent relationship into a process kill.  Unrelated processes
    are intentionally ignored.
    """

    if root_pid <= 0:
        return None
    parent_map: dict[int, int] = {}
    children: dict[int, list[int]] = {}
    for raw_pid, raw_parent_pid in entries:
        pid = int(raw_pid)
        parent_pid = int(raw_parent_pid)
        # Toolhelp snapshots include PID 0 (the System Idle Process). It is
        # not a terminable user process and must not make an otherwise valid
        # owned tree fail closed. Keep parent PID 0 for legitimate roots, but
        # ignore the synthetic PID-0 row itself.
        if pid == 0:
            continue
        if pid < 0 or parent_pid < 0 or pid in parent_map:
            return None
        parent_map[pid] = parent_pid
        children.setdefault(parent_pid, []).append(pid)
    if root_pid not in parent_map:
        return None

    result = [_SnapshotProcess(root_pid, parent_map[root_pid], (root_pid,))]
    seen = {root_pid}
    pending = [(root_pid, (root_pid,))]
    while pending:
        parent_pid, ancestry = pending.pop(0)
        for pid in children.get(parent_pid, ()):
            if pid in seen:
                # This is a reachable cycle (or an impossible duplicate edge)
                # and therefore cannot be safely used for a stop.
                return None
            seen.add(pid)
            child_ancestry = ancestry + (pid,)
            result.append(
                _SnapshotProcess(pid, parent_pid, child_ancestry)
            )
            pending.append((pid, child_ancestry))
    return tuple(result)


class _UnsupportedProcessSupervisor:
    """Safe fallback where the host has no supported process inspection API."""

    def capture(self, _pid: int, _expected_executable: str) -> ProcessIdentity | None:
        return None

    def verify(self, _identity: ProcessIdentity) -> bool:
        return False

    def terminate_tree(self, identity: ProcessIdentity) -> ProcessTerminationResult:
        return ProcessTerminationResult(
            success=False,
            failed_pids=(identity.pid,),
            summary="The platform could not verify the owned process identity.",
        )


class _ProcFsProcessSupervisor:
    """Small non-Windows fallback used by portable tests and development hosts."""

    @staticmethod
    def _image_path(pid: int) -> str | None:
        try:
            return os.readlink(f"/proc/{pid}/exe")
        except (OSError, ValueError):
            return None

    @classmethod
    def _read_identity(cls, pid: int, expected_executable: str) -> ProcessIdentity | None:
        image = cls._image_path(pid)
        if image is None or not _same_path(image, expected_executable):
            return None
        try:
            token = str(os.stat(f"/proc/{pid}").st_ctime_ns)
        except OSError:
            return None
        return ProcessIdentity(
            pid=pid,
            executable=image,
            token=f"procfs:{token}",
            creation_time=int(token),
        )

    def capture(self, pid: int, expected_executable: str) -> ProcessIdentity | None:
        if pid <= 0:
            return None
        return self._read_identity(pid, expected_executable)

    def verify(self, identity: ProcessIdentity) -> bool:
        current = self._read_identity(identity.pid, identity.executable)
        return current is not None and current.token == identity.token

    def terminate_tree(self, identity: ProcessIdentity) -> ProcessTerminationResult:
        if not self.verify(identity):
            return ProcessTerminationResult(
                success=False,
                failed_pids=(identity.pid,),
                summary="The owned process identity changed before it could be stopped.",
            )
        try:
            os.kill(identity.pid, signal.SIGKILL)
        except ProcessLookupError:
            return ProcessTerminationResult(success=True, attempted_pids=(identity.pid,))
        except OSError as exc:
            return ProcessTerminationResult(
                success=False,
                attempted_pids=(identity.pid,),
                failed_pids=(identity.pid,),
                summary=f"Could not stop owned process {identity.pid}: {exc}",
            )
        return ProcessTerminationResult(success=True, attempted_pids=(identity.pid,))


if os.name == "nt":
    from ctypes import wintypes

    _TH32CS_SNAPPROCESS = 0x00000002
    _PROCESS_TERMINATE = 0x00000001
    _PROCESS_QUERY_LIMITED_INFORMATION = 0x00001000
    _SYNCHRONIZE = 0x00100000
    _WAIT_OBJECT_0 = 0x00000000
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

    @dataclass
    class _OpenProcess:
        pid: int
        parent_pid: int
        ancestry: tuple[int, ...]
        identity: ProcessIdentity
        handle: object

    @dataclass(frozen=True)
    class _TreeCaptureAttempt:
        result: ProcessTerminationResult | None
        retry: bool = False

    class WindowsProcessSupervisor:
        """Inspect and stop an exact launcher-rooted Windows process tree.

        The tree is discovered from the verified launcher PID at stop time.
        Each capture attempt takes a FILETIME cutoff before its Toolhelp
        snapshot, holds handles for the complete validated tree, and rejects
        a PID first observed with a creation token newer than that cutoff.
        No image-name based kill is used.
        """

        def __init__(
            self,
            kernel32=None,
            *,
            system_time_filetime: Callable[[], int] | None = None,
            max_capture_attempts: int = 3,
        ):
            self.kernel32 = kernel32 or ctypes.WinDLL("kernel32", use_last_error=True)
            self.logger = logging.getLogger("game_control_plane.process_supervisor")
            self._system_time_provider = system_time_filetime
            self._max_capture_attempts = max(1, int(max_capture_attempts))
            self._system_time_api = None
            self.kernel32.CreateToolhelp32Snapshot.argtypes = [
                ctypes.c_ulong,
                ctypes.c_ulong,
            ]
            self.kernel32.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
            self.kernel32.Process32FirstW.argtypes = [
                ctypes.c_void_p,
                ctypes.POINTER(_ProcessEntry32W),
            ]
            self.kernel32.Process32FirstW.restype = ctypes.c_bool
            self.kernel32.Process32NextW.argtypes = [
                ctypes.c_void_p,
                ctypes.POINTER(_ProcessEntry32W),
            ]
            self.kernel32.Process32NextW.restype = ctypes.c_bool
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
            self.kernel32.GetProcessTimes.argtypes = [
                ctypes.c_void_p,
                ctypes.POINTER(wintypes.FILETIME),
                ctypes.POINTER(wintypes.FILETIME),
                ctypes.POINTER(wintypes.FILETIME),
                ctypes.POINTER(wintypes.FILETIME),
            ]
            self.kernel32.GetProcessTimes.restype = ctypes.c_bool
            if self._system_time_provider is None:
                self._system_time_api = getattr(
                    self.kernel32,
                    "GetSystemTimePreciseAsFileTime",
                    None,
                ) or getattr(self.kernel32, "GetSystemTimeAsFileTime", None)
                if self._system_time_api is None:
                    raise AttributeError(
                        "kernel32 does not expose a FILETIME system clock API"
                    )
                self._system_time_api.argtypes = [
                    ctypes.POINTER(wintypes.FILETIME),
                ]
                self._system_time_api.restype = None
            self.kernel32.TerminateProcess.argtypes = [ctypes.c_void_p, ctypes.c_uint]
            self.kernel32.TerminateProcess.restype = ctypes.c_bool
            self.kernel32.WaitForSingleObject.argtypes = [
                ctypes.c_void_p,
                ctypes.c_ulong,
            ]
            self.kernel32.WaitForSingleObject.restype = ctypes.c_ulong
            self.kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
            self.kernel32.CloseHandle.restype = ctypes.c_bool

        @staticmethod
        def _filetime_value(value: wintypes.FILETIME) -> int:
            return (int(value.dwHighDateTime) << 32) | int(value.dwLowDateTime)

        def _open(self, pid: int, access: int):
            if pid <= 0:
                return None
            handle = self.kernel32.OpenProcess(access, False, pid)
            return handle if handle else None

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

        def _creation_time(self, handle) -> int | None:
            creation = wintypes.FILETIME()
            exit_time = wintypes.FILETIME()
            kernel_time = wintypes.FILETIME()
            user_time = wintypes.FILETIME()
            if not self.kernel32.GetProcessTimes(
                handle,
                ctypes.byref(creation),
                ctypes.byref(exit_time),
                ctypes.byref(kernel_time),
                ctypes.byref(user_time),
            ):
                return None
            return self._filetime_value(creation)

        def _system_time_filetime(self) -> int:
            if self._system_time_provider is not None:
                value = int(self._system_time_provider())
            else:
                current = wintypes.FILETIME()
                self._system_time_api(ctypes.byref(current))
                value = self._filetime_value(current)
            if value < 0:
                raise ValueError("FILETIME system clock returned a negative value")
            return value

        def _query(self, handle, pid: int) -> ProcessIdentity | None:
            image_path = self._image_path(handle)
            creation_time = self._creation_time(handle)
            if not image_path or creation_time is None:
                return None
            return ProcessIdentity(
                pid=pid,
                executable=image_path,
                token=f"win-filetime:{creation_time}",
                creation_time=creation_time,
            )

        def capture(self, pid: int, expected_executable: str) -> ProcessIdentity | None:
            try:
                cutoff = self._system_time_filetime()
            except Exception:
                self.logger.exception("Could not read the FILETIME system clock")
                return None
            handle = self._open(
                pid,
                _SYNCHRONIZE | _PROCESS_QUERY_LIMITED_INFORMATION,
            )
            if handle is None:
                return None
            try:
                identity = self._query(handle, pid)
                if (
                    identity is None
                    or identity.creation_time is None
                    or identity.creation_time > cutoff
                    or not _same_path(identity.executable, expected_executable)
                ):
                    return None
                return identity
            finally:
                self.kernel32.CloseHandle(handle)

        def verify(self, identity: ProcessIdentity) -> bool:
            current = self.capture(identity.pid, identity.executable)
            return current is not None and current.token == identity.token

        def _snapshot(self) -> list[tuple[int, int]] | None:
            snapshot = self.kernel32.CreateToolhelp32Snapshot(_TH32CS_SNAPPROCESS, 0)
            if not snapshot or snapshot == _INVALID_HANDLE_VALUE:
                return None
            try:
                entry = _ProcessEntry32W()
                entry.dwSize = ctypes.sizeof(entry)
                if not self.kernel32.Process32FirstW(snapshot, ctypes.byref(entry)):
                    return None
                result: list[tuple[int, int]] = []
                while True:
                    result.append(
                        (int(entry.th32ProcessID), int(entry.th32ParentProcessID))
                    )
                    if not self.kernel32.Process32NextW(snapshot, ctypes.byref(entry)):
                        break
                return result
            finally:
                self.kernel32.CloseHandle(snapshot)

        def _open_tree_process(
            self,
            pid: int,
            parent_pid: int,
            ancestry: tuple[int, ...],
        ) -> _OpenProcess | None:
            handle = self._open(
                pid,
                _PROCESS_TERMINATE
                | _SYNCHRONIZE
                | _PROCESS_QUERY_LIMITED_INFORMATION,
            )
            if handle is None:
                return None
            identity = self._query(handle, pid)
            if identity is None:
                self.kernel32.CloseHandle(handle)
                return None
            return _OpenProcess(pid, parent_pid, ancestry, identity, handle)

        def _capture_current_identity(self, pid: int) -> ProcessIdentity | None:
            """Read a PID for reuse detection without granting terminate access."""

            handle = self._open(
                pid,
                _SYNCHRONIZE | _PROCESS_QUERY_LIMITED_INFORMATION,
            )
            if handle is None:
                return None
            try:
                return self._query(handle, pid)
            finally:
                try:
                    self.kernel32.CloseHandle(handle)
                except Exception:
                    self.logger.exception("Could not close identity-check handle")

        def _wait_exited(self, handle, timeout_ms: int = 0) -> bool:
            try:
                return (
                    self.kernel32.WaitForSingleObject(handle, timeout_ms)
                    == _WAIT_OBJECT_0
                )
            except Exception:
                return False

        def _close_processes(self, processes: Iterable[_OpenProcess]) -> None:
            for process in processes:
                try:
                    self.kernel32.CloseHandle(process.handle)
                except Exception:
                    self.logger.exception("Could not close process handle")

        @staticmethod
        def _snapshot_pids(entries: Iterable[tuple[int, int]]) -> set[int]:
            return {int(pid) for pid, _parent_pid in entries}

        @staticmethod
        def _root_descendant_pids(
            entries: Iterable[tuple[int, int]],
            root_pid: int,
        ) -> tuple[int, ...] | None:
            """Return root descendants even when the root is absent.

            This is used only for the natural-exit and post-termination checks,
            where ``_trusted_tree_snapshot`` cannot distinguish an absent root
            from a malformed snapshot.  Any duplicate or cyclic relationship
            is unsafe and therefore returns ``None``.
            """

            parent_map: dict[int, int] = {}
            for raw_pid, raw_parent_pid in entries:
                pid = int(raw_pid)
                parent_pid = int(raw_parent_pid)
                # PID 0 is the synthetic System Idle Process entry that
                # Toolhelp snapshots include on Windows; it is not part of
                # any owned launcher tree.
                if pid == 0:
                    continue
                if pid < 0 or parent_pid < 0 or pid in parent_map:
                    return None
                parent_map[pid] = parent_pid

            descendants: list[int] = []
            for pid in parent_map:
                if pid == root_pid:
                    continue
                cursor = pid
                seen = {pid}
                while cursor in parent_map:
                    parent_pid = parent_map[cursor]
                    if parent_pid == root_pid:
                        descendants.append(pid)
                        break
                    if parent_pid in seen:
                        return None
                    seen.add(parent_pid)
                    cursor = parent_pid
            return tuple(descendants)

        def _failure(
            self,
            failed_pids: Iterable[int],
            summary: str,
            attempted_pids: Iterable[int] = (),
        ) -> ProcessTerminationResult:
            return ProcessTerminationResult(
                success=False,
                attempted_pids=tuple(attempted_pids),
                failed_pids=tuple(dict.fromkeys(int(pid) for pid in failed_pids)),
                summary=summary,
            )

        def _post_termination_check(
            self,
            identity: ProcessIdentity,
            attempted: Iterable[int],
        ) -> ProcessTerminationResult | None:
            """Require a fresh snapshot to prove that no owned tree remains."""

            entries = self._snapshot()
            if entries is None:
                return self._failure(
                    (identity.pid,),
                    "Could not verify that the owned process tree exited after termination.",
                    attempted,
                )
            tree = _trusted_tree_snapshot(entries, identity.pid)
            if tree is not None:
                residual = tuple(item.pid for item in tree)
                return self._failure(
                    residual or (identity.pid,),
                    "The owned process tree remained after termination: "
                    + ", ".join(str(pid) for pid in residual or (identity.pid,)),
                    attempted,
                )
            if any(pid == identity.pid for pid, _parent_pid in entries):
                return self._failure(
                    (identity.pid,),
                    "The owned launcher remained in an invalid parent tree after termination.",
                    attempted,
                )
            descendants = self._root_descendant_pids(entries, identity.pid)
            if descendants is None:
                return self._failure(
                    (identity.pid,),
                    "The post-termination process snapshot had an invalid parent relationship.",
                    attempted,
                )
            if descendants:
                return self._failure(
                    descendants,
                    "An owned descendant remained after termination: "
                    + ", ".join(str(pid) for pid in descendants),
                    attempted,
                )
            return None

        def _terminate_tree_attempt(
            self,
            identity: ProcessIdentity,
            cutoff: int,
        ) -> _TreeCaptureAttempt:
            """Capture, validate, and stop one stable tree attempt.

            A new descendant between the initial and fresh snapshots is not
            adopted into this attempt.  Returning ``retry=True`` closes every
            held handle and lets the caller take a new cutoff and capture.
            Conversely, a PID from the initial snapshot that opens with a
            creation token newer than that attempt's cutoff is a replacement
            race and fails closed, even when its parent is still the root.
            """

            initial_entries = self._snapshot()
            if initial_entries is None:
                return _TreeCaptureAttempt(
                    self._failure(
                        (identity.pid,),
                        "Could not take a trusted process snapshot for the owned launcher.",
                    )
                )
            if not any(pid == identity.pid for pid, _parent_pid in initial_entries):
                return _TreeCaptureAttempt(
                    ProcessTerminationResult(
                        success=True,
                        summary="The owned launcher had already exited.",
                    )
                )
            initial_tree = _trusted_tree_snapshot(initial_entries, identity.pid)
            if initial_tree is None:
                return _TreeCaptureAttempt(
                    self._failure(
                        (identity.pid,),
                        "The owned launcher process tree had an invalid parent relationship.",
                    )
                )

            held: list[_OpenProcess] = []
            missing: set[int] = set()
            try:
                # The validated root is opened first, followed immediately by
                # every descendant from that same snapshot.  The creation token
                # must be no newer than the cutoff taken before the snapshot.
                for item in initial_tree:
                    try:
                        process = self._open_tree_process(
                            item.pid,
                            item.parent_pid,
                            item.ancestry,
                        )
                    except Exception:
                        self.logger.exception(
                            "Could not open process %s from the owned tree", item.pid
                        )
                        process = None
                    if process is not None:
                        held.append(process)
                        if (
                            process.identity.creation_time is None
                            or process.identity.creation_time > cutoff
                        ):
                            return _TreeCaptureAttempt(
                                self._failure(
                                    (item.pid,),
                                    "A process in the owned tree was created after the trusted capture cutoff.",
                                )
                            )
                        continue

                    # A process can naturally disappear between the snapshot
                    # and OpenProcess.  Treat that case as already stopped
                    # only when a fresh, successful snapshot proves the PID is
                    # absent.  An access/query failure for a still-present PID
                    # rejects the entire tree; it is never skipped.
                    current_entries = self._snapshot()
                    if current_entries is None:
                        return _TreeCaptureAttempt(
                            self._failure(
                                (item.pid,),
                                "Could not re-snapshot the owned process tree after an OpenProcess failure.",
                            )
                        )
                    if item.pid in self._snapshot_pids(current_entries):
                        return _TreeCaptureAttempt(
                            self._failure(
                                (item.pid,),
                                "Could not hold a verified handle for every process in the owned tree.",
                            )
                        )
                    missing.add(item.pid)

                held_by_pid = {process.pid: process for process in held}
                root = held_by_pid.get(identity.pid)
                if root is None:
                    # The root may have exited after the trusted snapshot.  Do
                    # not touch any surviving descendant without a live root
                    # and a revalidated parent chain.
                    current_entries = self._snapshot()
                    if current_entries is None:
                        return _TreeCaptureAttempt(
                            self._failure(
                                (identity.pid,),
                                "Could not verify that the owned launcher exited naturally.",
                            )
                        )
                    if identity.pid in self._snapshot_pids(current_entries):
                        return _TreeCaptureAttempt(
                            self._failure(
                                (identity.pid,),
                                "The owned launcher could not be held for termination.",
                            )
                        )
                    descendants = self._root_descendant_pids(
                        current_entries,
                        identity.pid,
                    )
                    if descendants is None or descendants:
                        return _TreeCaptureAttempt(
                            self._failure(
                                descendants or (identity.pid,),
                                "The launcher exited while a descendant remained unverified.",
                            )
                        )
                    return _TreeCaptureAttempt(
                        ProcessTerminationResult(
                            success=True,
                            summary="The owned launcher had already exited.",
                        )
                    )

                if not _same_path(root.identity.executable, identity.executable):
                    return _TreeCaptureAttempt(
                        self._failure(
                            (identity.pid,),
                            "The owned launcher image changed before termination.",
                        )
                    )
                if root.identity.token != identity.token:
                    return _TreeCaptureAttempt(
                        self._failure(
                            (identity.pid,),
                            "The owned launcher creation token changed before termination.",
                        )
                    )

                # Validate the parent graph again immediately before any kill.
                # A new descendant is never opened or adopted in this attempt:
                # close the held handles and retry from a new cutoff instead.
                latest_entries = self._snapshot()
                if latest_entries is None:
                    return _TreeCaptureAttempt(
                        self._failure(
                            (identity.pid,),
                            "Could not revalidate the owned process tree before termination.",
                        )
                    )
                latest_tree = _trusted_tree_snapshot(latest_entries, identity.pid)
                initial_by_pid = {item.pid: item for item in initial_tree}
                latest_by_pid = {item.pid: item for item in latest_tree or ()}
                latest_pids = self._snapshot_pids(latest_entries)
                if latest_tree is None:
                    if any(pid == identity.pid for pid, _parent_pid in latest_entries):
                        return _TreeCaptureAttempt(
                            self._failure(
                                (identity.pid,),
                                "The owned launcher parent tree changed before termination.",
                            )
                        )
                    if not self._wait_exited(root.handle):
                        return _TreeCaptureAttempt(
                            self._failure(
                                (identity.pid,),
                                "The owned launcher parent tree changed before termination.",
                            )
                        )
                    descendants = self._root_descendant_pids(
                        latest_entries,
                        identity.pid,
                    )
                    if descendants is None or descendants:
                        return _TreeCaptureAttempt(
                            self._failure(
                                descendants or (identity.pid,),
                                "The launcher exited while a descendant remained alive and unverified.",
                            )
                        )
                    if any(
                        process.pid != identity.pid
                        and not self._wait_exited(process.handle)
                        for process in held
                    ):
                        return _TreeCaptureAttempt(
                            self._failure(
                                (identity.pid,),
                                "The launcher exited while a descendant remained alive and unverified.",
                            )
                        )
                    return _TreeCaptureAttempt(
                        ProcessTerminationResult(
                            success=True,
                            summary="The owned launcher had already exited.",
                        )
                    )

                new_pids = tuple(pid for pid in latest_by_pid if pid not in initial_by_pid)
                if new_pids:
                    return _TreeCaptureAttempt(result=None, retry=True)

                live: list[_OpenProcess] = []
                for process in held:
                    # A signalled held handle refers to the originally opened
                    # process, even if its PID has already been reused.  Never
                    # reopen or terminate that replacement PID.
                    expected = initial_by_pid[process.pid]
                    current = latest_by_pid.get(process.pid)
                    if self._wait_exited(process.handle):
                        if current is None:
                            continue
                        if (
                            current.parent_pid != expected.parent_pid
                            or current.ancestry != expected.ancestry
                        ):
                            return _TreeCaptureAttempt(
                                self._failure(
                                    (process.pid,),
                                    "The reused process parent chain changed before termination.",
                                )
                            )
                        # A PID that is still listed after its held handle was
                        # signalled may have been reused.  Read the current PID
                        # only for comparison; never use this new handle to
                        # terminate anything.
                        current_identity = self._capture_current_identity(process.pid)
                        if (
                            current_identity is None
                            or current_identity.creation_time is None
                            or current_identity.creation_time > cutoff
                            or current_identity.token != process.identity.token
                            or not _same_path(
                                current_identity.executable,
                                process.identity.executable,
                            )
                        ):
                            return _TreeCaptureAttempt(
                                self._failure(
                                    (process.pid,),
                                    "A process PID was reused before termination.",
                                )
                            )
                        continue
                    if (
                        current is None
                        or current.parent_pid != expected.parent_pid
                        or current.ancestry != expected.ancestry
                    ):
                        return _TreeCaptureAttempt(
                            self._failure(
                                (process.pid,),
                                "The owned process parent chain changed before termination.",
                            )
                        )
                    if process.pid in missing:
                        return _TreeCaptureAttempt(
                            self._failure(
                                (process.pid,),
                                "A process in the owned tree could not be revalidated.",
                            )
                        )
                    current_identity = self._query(process.handle, process.pid)
                    if (
                        current_identity is None
                        or current_identity.creation_time is None
                        or current_identity.creation_time > cutoff
                        or current_identity.token != process.identity.token
                        or not _same_path(
                            current_identity.executable,
                            process.identity.executable,
                        )
                    ):
                        return _TreeCaptureAttempt(
                            self._failure(
                                (process.pid,),
                                "A held process creation token or image changed before termination.",
                            )
                        )
                    if process is not root:
                        root_creation = root.identity.creation_time
                        process_creation = process.identity.creation_time
                        if (
                            root_creation is None
                            or process_creation is None
                            or process_creation < root_creation
                        ):
                            return _TreeCaptureAttempt(
                                self._failure(
                                    (process.pid,),
                                    "A descendant was created before the verified launcher root.",
                                )
                            )
                    live.append(process)

                if any(pid in latest_pids for pid in missing):
                    return _TreeCaptureAttempt(
                        self._failure(
                            tuple(pid for pid in missing if pid in latest_pids),
                            "A process that could not be held was still present before termination.",
                        )
                    )
                if root not in live:
                    if live:
                        return _TreeCaptureAttempt(
                            self._failure(
                                (identity.pid,),
                                "The owned launcher exited while a descendant remained alive.",
                            )
                        )
                    return _TreeCaptureAttempt(
                        ProcessTerminationResult(
                            success=True,
                            summary="The owned launcher had already exited.",
                        )
                    )

                attempted: list[int] = []
                failed: list[int] = []
                # Descendants first, root last.  The ancestry length is the
                # distance from the root and gives a deterministic child-first
                # order even when the snapshot's enumeration order changes.
                for process in sorted(
                    live,
                    key=lambda item: len(item.ancestry),
                    reverse=True,
                ):
                    attempted.append(process.pid)
                    try:
                        terminated = bool(
                            self.kernel32.TerminateProcess(process.handle, 1)
                        )
                    except Exception:
                        self.logger.exception(
                            "TerminateProcess failed for owned PID %s", process.pid
                        )
                        terminated = False
                    if not terminated:
                        # The same held handle can prove that the original
                        # process naturally exited between validation and this
                        # call.  A replacement process with the same PID is not
                        # represented by this handle and is never targeted.
                        if not self._wait_exited(process.handle):
                            failed.append(process.pid)
                            break

                if failed:
                    return _TreeCaptureAttempt(
                        self._failure(
                            failed,
                            "Could not terminate every held process in the owned tree: "
                            + ", ".join(str(pid) for pid in failed),
                            attempted,
                        )
                    )
                for process in live:
                    if not self._wait_exited(process.handle, 1000):
                        return _TreeCaptureAttempt(
                            self._failure(
                                (process.pid,),
                                "A held process remained alive after termination.",
                                attempted,
                            )
                        )
                post_failure = self._post_termination_check(identity, attempted)
                if post_failure is not None:
                    return _TreeCaptureAttempt(post_failure)
                return _TreeCaptureAttempt(
                    ProcessTerminationResult(
                        success=True,
                        attempted_pids=tuple(attempted),
                    )
                )
            finally:
                self._close_processes(held)

        def terminate_tree(self, identity: ProcessIdentity) -> ProcessTerminationResult:
            # A separate cutoff is taken immediately before each capture
            # attempt.  This permits a genuine new descendant to be included
            # only by a fresh, stable attempt, while a replacement of a PID
            # observed in that attempt is rejected when its creation token is
            # newer than the attempt cutoff.
            for attempt in range(self._max_capture_attempts):
                try:
                    cutoff = self._system_time_filetime()
                except Exception:
                    self.logger.exception("Could not read the FILETIME system clock")
                    return self._failure(
                        (identity.pid,),
                        "Could not establish a trusted process capture cutoff.",
                    )
                outcome = self._terminate_tree_attempt(identity, cutoff)
                if not outcome.retry:
                    return outcome.result or self._failure(
                        (identity.pid,),
                        "The owned process stop produced no result.",
                    )
                self.logger.warning(
                    "Owned process tree changed during capture; retry %s/%s",
                    attempt + 1,
                    self._max_capture_attempts,
                )
            return self._failure(
                (identity.pid,),
                "The owned process tree did not stabilize before termination; no process was stopped.",
            )

else:

    WindowsProcessSupervisor = _UnsupportedProcessSupervisor


def default_process_supervisor() -> ProcessSupervisor:
    if os.name == "nt":
        return WindowsProcessSupervisor()
    if Path("/proc").is_dir():
        return _ProcFsProcessSupervisor()
    return _UnsupportedProcessSupervisor()


def process_identity_dict(identity: ProcessIdentity) -> dict[str, object]:
    return {
        "pid": identity.pid,
        "executable": identity.executable,
        "token": identity.token,
        "creation_time": identity.creation_time,
    }


__all__ = [
    "ProcessIdentity",
    "ProcessSupervisor",
    "ProcessTerminationResult",
    "WindowsProcessSupervisor",
    "default_process_supervisor",
    "process_identity_dict",
]
