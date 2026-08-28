from __future__ import annotations

import os
from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from game_control_plane.application import process_supervisor
from game_control_plane.application.process_supervisor import (
    ProcessIdentity,
    _ProcFsProcessSupervisor,
    _descendant_pids,
    _trusted_tree_snapshot,
)


def test_descendant_snapshot_is_limited_to_one_root_and_handles_cycles():
    entries = (
        (101, 1),
        (102, 100),
        (103, 102),
        (104, 103),
        (105, 999),
        (103, 104),
    )

    assert _descendant_pids(entries, 100) == (102, 103, 104)


def test_procfs_identity_requires_exact_image_path_and_stable_token(monkeypatch):
    expected = "/opt/onedragon/OneDragon-RuntimeLauncher.exe"
    supervisor = _ProcFsProcessSupervisor()
    with monkeypatch.context() as context:
        context.setattr(
            _ProcFsProcessSupervisor,
            "_image_path",
            staticmethod(lambda _pid: expected),
        )
        context.setattr(
            process_supervisor.os,
            "stat",
            lambda _path, **_kwargs: SimpleNamespace(st_ctime_ns=1234),
        )
        identity = supervisor.capture(42, expected)
        assert identity == ProcessIdentity(
            pid=42,
            executable=expected,
            token="procfs:1234",
            creation_time=1234,
        )
        assert supervisor.verify(identity)

        context.setattr(
            _ProcFsProcessSupervisor,
            "_image_path",
            staticmethod(lambda _pid: "/opt/other/OneDragon-RuntimeLauncher.exe"),
        )
        assert supervisor.capture(42, expected) is None
        assert not supervisor.verify(identity)


def test_procfs_identity_rejects_token_change(monkeypatch):
    expected = "/opt/onedragon/OneDragon-RuntimeLauncher.exe"
    supervisor = _ProcFsProcessSupervisor()
    token = {"value": 1}
    with monkeypatch.context() as context:
        context.setattr(
            _ProcFsProcessSupervisor,
            "_image_path",
            staticmethod(lambda _pid: expected),
        )
        context.setattr(
            process_supervisor.os,
            "stat",
            lambda _path, **_kwargs: SimpleNamespace(st_ctime_ns=token["value"]),
        )
        identity = supervisor.capture(42, expected)
        assert identity is not None
        token["value"] = 2
        assert not supervisor.verify(identity)


def test_trusted_snapshot_rejects_duplicate_or_reachable_cycle():
    assert _trusted_tree_snapshot(((100, 1), (101, 100), (101, 100)), 100) is None
    assert _trusted_tree_snapshot(((100, 101), (101, 100)), 100) is None


@pytest.mark.skipif(os.name != "nt", reason="exercises the Windows kernel adapter")
class TestWindowsProcessSupervisorWithFakeKernel:
    """Exercise native handle lifetime without touching a real user process."""

    ROOT = 100
    CHILD = 101
    PATH = r"C:\OneDragon\OneDragon-RuntimeLauncher.exe"

    @dataclass
    class _Record:
        pid: int
        parent_pid: int
        token: int
        path: str
        alive: bool = True

    class _Callable:
        def __init__(self, callback):
            self.callback = callback
            self.argtypes = None
            self.restype = None

        def __call__(self, *args):
            return self.callback(*args)

    class _Snapshot:
        def __init__(self, entries):
            self.entries = list(entries)
            self.index = -1
            self.closed = False

    class _Handle:
        def __init__(self, record):
            self.pid = record.pid
            self.token = record.token
            self.path = record.path
            self.alive = record.alive
            self.terminated = False
            self.closed = False

    class _Kernel:
        def __init__(
            self,
            records,
            snapshots,
            *,
            time_filetime=5000,
            open_fail_pids=(),
            terminate_fail_pids=(),
            on_snapshot=None,
            on_open=None,
        ):
            self.records = records
            self.snapshots = list(snapshots)
            self.time_filetime = int(time_filetime)
            self.open_fail_pids = set(open_fail_pids)
            self.terminate_fail_pids = set(terminate_fail_pids)
            self.on_snapshot = on_snapshot
            self.on_open = on_open
            self.on_terminate = None
            self.time_calls = 0
            self.snapshot_count = 0
            self.opened = []
            self.closed = []
            self.terminated = []
            self._install()

        def _install(self):
            call = TestWindowsProcessSupervisorWithFakeKernel._Callable
            self.CreateToolhelp32Snapshot = call(self._create_snapshot)
            self.Process32FirstW = call(self._first)
            self.Process32NextW = call(self._next)
            self.OpenProcess = call(self._open)
            self.QueryFullProcessImageNameW = call(self._query_path)
            self.GetProcessTimes = call(self._times)
            self.GetSystemTimeAsFileTime = call(self._system_time)
            self.TerminateProcess = call(self._terminate)
            self.WaitForSingleObject = call(self._wait)
            self.CloseHandle = call(self._close)

        def _create_snapshot(self, _flags, _pid):
            index = min(self.snapshot_count, len(self.snapshots) - 1)
            source = self.snapshots[index]
            self.snapshot_count += 1
            if callable(source):
                source = source()
            if source is None:
                return 0
            if self.snapshot_count > len(self.snapshots):
                source = tuple(
                    (pid, parent_pid)
                    for pid, parent_pid in source
                    if self.records.get(pid) is None
                    or self.records[pid].alive
                )
                if not source:
                    # A real Toolhelp snapshot still contains unrelated
                    # system processes after the owned tree exits.  Keep a
                    # harmless foreign entry so Process32FirstW succeeds.
                    source = ((999, 1),)
            snapshot = TestWindowsProcessSupervisorWithFakeKernel._Snapshot(source)
            if self.on_snapshot is not None:
                self.on_snapshot(self.snapshot_count, snapshot)
            return snapshot

        @staticmethod
        def _fill(snapshot, pointer):
            entry = pointer._obj
            pid, parent_pid = snapshot.entries[snapshot.index]
            entry.th32ProcessID = pid
            entry.th32ParentProcessID = parent_pid
            return True

        def _first(self, snapshot, pointer):
            if not snapshot.entries:
                return False
            snapshot.index = 0
            return self._fill(snapshot, pointer)

        def _next(self, snapshot, pointer):
            snapshot.index += 1
            if snapshot.index >= len(snapshot.entries):
                return False
            return self._fill(snapshot, pointer)

        def _open(self, _access, _inherit, pid):
            pid = int(pid)
            if self.on_open is not None:
                self.on_open(pid)
            record = self.records.get(pid)
            if pid in self.open_fail_pids or record is None or not record.alive:
                return 0
            handle = TestWindowsProcessSupervisorWithFakeKernel._Handle(record)
            self.opened.append(handle)
            return handle

        @staticmethod
        def _query_path(handle, _flags, buffer, size):
            buffer.value = handle.path
            size._obj.value = len(handle.path)
            return True

        @staticmethod
        def _times(handle, creation, _exit, _kernel, _user):
            value = int(handle.token)
            creation._obj.dwLowDateTime = value & 0xFFFFFFFF
            creation._obj.dwHighDateTime = value >> 32
            return True

        def _system_time(self, pointer):
            self.time_calls += 1
            value = int(self.time_filetime)
            pointer._obj.dwLowDateTime = value & 0xFFFFFFFF
            pointer._obj.dwHighDateTime = value >> 32

        def _terminate(self, handle, _exit_code):
            if self.on_terminate is not None:
                self.on_terminate(handle)
            if handle.pid in self.terminate_fail_pids:
                return False
            handle.terminated = True
            handle.alive = False
            record = self.records.get(handle.pid)
            if record is not None:
                record.alive = False
            self.terminated.append(handle)
            return True

        @staticmethod
        def _wait(handle, _timeout):
            return (
                process_supervisor._WAIT_OBJECT_0
                if not handle.alive
                else 0x00000102  # WAIT_TIMEOUT
            )

        def _close(self, handle):
            handle.closed = True
            self.closed.append(handle)
            return True

    def _fixture(self, snapshots, **kwargs):
        records = {
            self.ROOT: self._Record(self.ROOT, 1, 1000, self.PATH),
            self.CHILD: self._Record(self.CHILD, self.ROOT, 1001, r"C:\OneDragon\worker.exe"),
            202: self._Record(202, self.ROOT, 1002, r"C:\OneDragon\new-worker.exe"),
            200: self._Record(200, 1, 2000, r"C:\Other\other.exe"),
            201: self._Record(201, 200, 2001, r"C:\Other\worker.exe"),
        }
        kernel = self._Kernel(records, snapshots, **kwargs)
        supervisor = process_supervisor.WindowsProcessSupervisor(kernel32=kernel)
        identity = ProcessIdentity(
            pid=self.ROOT,
            executable=self.PATH,
            token="win-filetime:1000",
            creation_time=1000,
        )
        return supervisor, identity, kernel

    def test_capture_reads_FILETIME_cutoff_before_opening_root(self):
        entries = ((self.ROOT, 1),)
        supervisor, identity, kernel = self._fixture((entries,))

        captured = supervisor.capture(self.ROOT, self.PATH)

        assert captured == identity
        assert kernel.time_calls == 1
        assert all(handle.closed for handle in kernel.opened)

    def test_late_pid_reuse_terminates_only_held_original_handle(self):
        entries = ((self.ROOT, 1), (self.CHILD, self.ROOT))
        supervisor, identity, kernel = self._fixture((entries, entries))

        def reuse_after_validation(handle):
            if handle.pid == self.CHILD:
                # The replacement happens after all identity and parent-chain
                # checks.  TerminateProcess still receives the held handle.
                kernel.records[self.CHILD].token = 9001

        kernel.on_terminate = reuse_after_validation

        result = supervisor.terminate_tree(identity)

        assert result.success
        assert [handle.pid for handle in kernel.terminated] == [self.CHILD, self.ROOT]
        assert [handle.token for handle in kernel.terminated] == [1001, 1000]
        assert all(handle.closed for handle in kernel.opened)

    def test_pid_reuse_to_unrelated_process_is_rejected_without_termination(self):
        entries = ((self.ROOT, 1), (self.CHILD, self.ROOT))
        kernel_holder = {}

        def reuse_on_latest_snapshot(count, _snapshot):
            if count == 2:
                kernel = kernel_holder["kernel"]
                kernel.records[self.CHILD].token = 9001
                kernel.records[self.CHILD].path = r"C:\Other\unrelated.exe"
                for handle in kernel.opened:
                    if handle.pid == self.CHILD:
                        handle.alive = False

        supervisor, identity, kernel = self._fixture(
            (entries, entries), on_snapshot=reuse_on_latest_snapshot
        )
        kernel_holder["kernel"] = kernel

        result = supervisor.terminate_tree(identity)

        assert not result.success
        assert result.failed_pids == (self.CHILD,)
        assert kernel.terminated == []

    def test_root_token_change_rejects_tree_without_termination(self):
        entries = ((self.ROOT, 1), (self.CHILD, self.ROOT))
        kernel_holder = {}

        def replace_root_on_latest_snapshot(count, _snapshot):
            if count == 2:
                kernel = kernel_holder["kernel"]
                kernel.records[self.ROOT].token = 9002
                kernel.records[self.ROOT].path = r"C:\Other\replacement.exe"
                for handle in kernel.opened:
                    if handle.pid == self.ROOT:
                        handle.alive = False

        supervisor, identity, kernel = self._fixture(
            (entries, entries), on_snapshot=replace_root_on_latest_snapshot
        )
        kernel_holder["kernel"] = kernel

        result = supervisor.terminate_tree(identity)

        assert not result.success
        assert result.failed_pids == (self.ROOT,)
        assert kernel.terminated == []

    def test_new_child_causes_bounded_recapture_then_stable_stop(self):
        initial = ((self.ROOT, 1), (self.CHILD, self.ROOT))
        current = initial + ((202, self.ROOT),)
        supervisor, identity, kernel = self._fixture(
            (initial, current, current, current)
        )

        result = supervisor.terminate_tree(identity)

        assert result.success
        assert result.attempted_pids == (self.CHILD, 202, self.ROOT)
        assert {handle.pid for handle in kernel.terminated} == {
            self.CHILD,
            202,
            self.ROOT,
        }
        assert all(handle.closed for handle in kernel.opened)
        assert kernel.snapshot_count == 5

    def test_continuous_new_children_fail_closed_without_termination(self):
        initial = ((self.ROOT, 1), (self.CHILD, self.ROOT))
        first_child = initial + ((202, self.ROOT),)
        second_child = first_child + ((203, self.ROOT),)
        third_child = second_child + ((204, self.ROOT),)
        supervisor, identity, kernel = self._fixture(
            (initial, first_child, first_child, second_child, second_child, third_child)
        )
        kernel.records[203] = self._Record(
            203,
            self.ROOT,
            1003,
            r"C:\OneDragon\new-worker-2.exe",
        )
        kernel.records[204] = self._Record(
            204,
            self.ROOT,
            1004,
            r"C:\OneDragon\new-worker-3.exe",
        )

        result = supervisor.terminate_tree(identity)

        assert not result.success
        assert result.attempted_pids == ()
        assert kernel.terminated == []
        assert kernel.snapshot_count == 6
        assert all(handle.closed for handle in kernel.opened)

    def test_pid_reuse_before_first_open_to_unrelated_parent_is_rejected(self):
        initial = ((self.ROOT, 1), (self.CHILD, self.ROOT))
        kernel_holder = {}

        def reuse_before_child_open(pid):
            if pid == self.CHILD:
                kernel = kernel_holder["kernel"]
                kernel.records[self.CHILD].parent_pid = 200
                kernel.records[self.CHILD].token = 9101
                kernel.records[self.CHILD].path = r"C:\Other\unrelated.exe"

        def current_entries():
            kernel = kernel_holder["kernel"]
            return (
                (self.ROOT, 1),
                (self.CHILD, kernel.records[self.CHILD].parent_pid),
                (200, 1),
            )

        supervisor, identity, kernel = self._fixture(
            (initial, current_entries), on_open=reuse_before_child_open
        )
        kernel_holder["kernel"] = kernel

        result = supervisor.terminate_tree(identity)

        assert not result.success
        assert result.failed_pids == (self.CHILD,)
        assert result.attempted_pids == ()
        assert kernel.terminated == []

    def test_pid_reuse_before_first_open_under_same_root_is_rejected_by_cutoff(self):
        initial = ((self.ROOT, 1), (self.CHILD, self.ROOT))
        kernel_holder = {}

        def reuse_before_child_open(pid):
            if pid == self.CHILD:
                kernel = kernel_holder["kernel"]
                kernel.records[self.CHILD].token = 6000

        def current_entries():
            return initial

        supervisor, identity, kernel = self._fixture(
            (initial, current_entries), on_open=reuse_before_child_open
        )
        kernel_holder["kernel"] = kernel

        result = supervisor.terminate_tree(identity)

        assert not result.success
        assert result.failed_pids == (self.CHILD,)
        assert result.attempted_pids == ()
        assert "cutoff" in result.summary
        assert kernel.terminated == []
        assert all(handle.closed for handle in kernel.opened)

    def test_post_termination_new_descendant_is_cleanup_failure(self):
        entries = ((self.ROOT, 1), (self.CHILD, self.ROOT))

        def spawn_after_termination(count, snapshot):
            if count == 3:
                snapshot.entries.append((202, self.ROOT))

        supervisor, identity, kernel = self._fixture(
            (entries, entries),
            on_snapshot=spawn_after_termination,
        )

        result = supervisor.terminate_tree(identity)

        assert not result.success
        assert result.attempted_pids == (self.CHILD, self.ROOT)
        assert result.failed_pids == (202,)
        assert "remained after termination" in result.summary
        assert [handle.pid for handle in kernel.terminated] == [
            self.CHILD,
            self.ROOT,
        ]
        assert all(handle.closed for handle in kernel.opened)

    def test_parent_chain_change_rejects_whole_tree_without_termination(self):
        initial = ((self.ROOT, 1), (self.CHILD, self.ROOT))
        changed = ((self.ROOT, 1), (self.CHILD, 200), (200, 1))
        supervisor, identity, kernel = self._fixture((initial, changed))

        result = supervisor.terminate_tree(identity)

        assert not result.success
        assert result.failed_pids == (self.CHILD,)
        assert kernel.terminated == []
        assert all(handle.closed for handle in kernel.opened)

    def test_natural_root_exit_is_already_stopped_and_does_not_kill(self):
        initial = ((self.ROOT, 1), (self.CHILD, self.ROOT))
        supervisor, identity, kernel = self._fixture((initial, ((200, 1),)))
        kernel.records[self.ROOT].alive = False

        result = supervisor.terminate_tree(identity)

        assert result.success
        assert result.attempted_pids == ()
        assert kernel.terminated == []

    def test_natural_child_exit_does_not_adopt_a_reused_stranger(self):
        initial = ((self.ROOT, 1), (self.CHILD, self.ROOT))
        current = ((self.ROOT, 1), (200, 1))
        supervisor, identity, kernel = self._fixture((initial, current, current))
        kernel.records[self.CHILD].alive = False

        result = supervisor.terminate_tree(identity)

        assert result.success
        assert result.attempted_pids == (self.ROOT,)
        assert [handle.pid for handle in kernel.terminated] == [self.ROOT]

    def test_open_process_failure_for_present_descendant_rejects_tree(self):
        entries = ((self.ROOT, 1), (self.CHILD, self.ROOT))
        supervisor, identity, kernel = self._fixture(
            (entries, entries), open_fail_pids=(self.CHILD,)
        )

        result = supervisor.terminate_tree(identity)

        assert not result.success
        assert result.failed_pids == (self.CHILD,)
        assert kernel.terminated == []
        assert all(handle.closed for handle in kernel.opened)

    def test_terminate_process_failure_is_visible_and_closes_handles(self):
        entries = ((self.ROOT, 1), (self.CHILD, self.ROOT))
        supervisor, identity, kernel = self._fixture(
            (entries, entries), terminate_fail_pids=(self.CHILD,)
        )

        result = supervisor.terminate_tree(identity)

        assert not result.success
        assert result.attempted_pids == (self.CHILD,)
        assert result.failed_pids == (self.CHILD,)
        assert kernel.terminated == []
        assert all(handle.closed for handle in kernel.opened)

    def test_concurrent_root_tree_never_touches_other_root(self):
        entries = (
            (self.ROOT, 1),
            (self.CHILD, self.ROOT),
            (200, 1),
            (201, 200),
        )
        supervisor, identity, kernel = self._fixture((entries, entries))

        result = supervisor.terminate_tree(identity)

        assert result.success
        assert result.attempted_pids == (self.CHILD, self.ROOT)
        assert {handle.pid for handle in kernel.terminated} == {self.CHILD, self.ROOT}
        assert all(handle.pid not in {200, 201} for handle in kernel.opened)
