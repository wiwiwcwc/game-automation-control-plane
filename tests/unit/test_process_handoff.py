from dataclasses import dataclass
from pathlib import Path

from game_control_plane.application.process_handoff import (
    HandoffCoordinator,
    HandoffTracker,
    ProcessOutcome,
    _is_child_image_under_launcher,
)


@dataclass
class FakeWorker:
    exit_codes: list[int | None]
    closed: bool = False
    pid: int = 123

    def poll_exit_code(self) -> int | None:
        if not self.exit_codes:
            return None
        return self.exit_codes.pop(0)

    def close(self) -> None:
        self.closed = True


class FakeLocator:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls: list[tuple[int, str, tuple[str, ...]]] = []

    def find_worker(self, launcher_pid, launcher_executable, process_names):
        self.calls.append((launcher_pid, launcher_executable, process_names))
        return self.responses.pop(0) if self.responses else None


def test_race_discovers_worker_during_parent_grace_period(tmp_path: Path):
    worker = FakeWorker([None, 0])
    locator = FakeLocator([None, worker])
    tracker = HandoffTracker(locator, 30320, str(tmp_path / "ok-ww.exe"), ("pythonw.exe",))
    coordinator = HandoffCoordinator(tracker, grace_seconds=1.0)

    assert coordinator.parent_finished(ProcessOutcome(15), now=0.0) is None
    assert coordinator.poll(now=0.1) is None
    result = coordinator.poll(now=0.2)

    assert result == ProcessOutcome(0)
    assert worker.closed
    assert locator.calls[-1][2] == ("pythonw.exe",)


def test_missing_worker_falls_back_to_launcher_after_grace(tmp_path: Path):
    locator = FakeLocator([None, None, None])
    tracker = HandoffTracker(locator, 30320, str(tmp_path / "ok-ww.exe"), ("pythonw.exe",))
    coordinator = HandoffCoordinator(tracker, grace_seconds=0.5)
    parent = ProcessOutcome(15)

    assert coordinator.parent_finished(parent, now=0.0) is None
    assert coordinator.poll(now=0.49) is None
    assert coordinator.poll(now=0.5) == parent


def test_worker_nonzero_exit_wins_over_launcher_result(tmp_path: Path):
    worker = FakeWorker([9])
    locator = FakeLocator([worker])
    tracker = HandoffTracker(locator, 30320, str(tmp_path / "ok-ww.exe"), ("python.exe",))
    coordinator = HandoffCoordinator(tracker, grace_seconds=1.0)

    result = coordinator.parent_finished(ProcessOutcome(15), now=0.0)

    assert result == ProcessOutcome(9)
    assert worker.closed


def test_worker_filter_rejects_unrelated_processes(tmp_path: Path):
    launcher = tmp_path / "ok-ww.exe"
    worker = tmp_path / "data" / "apps" / "ok-ww" / "pythonw.exe"
    unrelated = tmp_path.parent / "other-game" / "pythonw.exe"

    assert _is_child_image_under_launcher(
        str(worker), str(launcher), ("pythonw.exe", "python.exe")
    )
    assert not _is_child_image_under_launcher(
        str(unrelated), str(launcher), ("pythonw.exe", "python.exe")
    )
    assert not _is_child_image_under_launcher(
        str(worker.with_name("powershell.exe")),
        str(launcher),
        ("pythonw.exe", "python.exe"),
    )
