from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from game_control_plane.integrations.maa_preflight import (
    CheckState,
    CommandResult,
    run_maa_preflight,
)
from game_control_plane.integrations.maa_managed_task import default_managed_daily


@dataclass
class ExpectedCall:
    command: tuple[str, ...]
    result: CommandResult


class FakeRunner:
    def __init__(self, calls: list[ExpectedCall]):
        self.expected = list(calls)
        self.commands: list[tuple[str, ...]] = []

    def run(self, command, timeout_seconds):
        command_tuple = tuple(command)
        self.commands.append(command_tuple)
        assert timeout_seconds > 0
        expected = self.expected.pop(0)
        assert command_tuple == expected.command
        return expected.result


def make_paths(tmp_path: Path) -> tuple[str, str, Path]:
    maa = tmp_path / "maa-cli.exe"
    adb = tmp_path / "adb.exe"
    maa.touch()
    adb.touch()
    config = tmp_path / "config"
    profile_dir = config / "profiles"
    profile_dir.mkdir(parents=True)
    (profile_dir / "default.toml").write_text(
        '[connection]\nadb_path = "' + str(adb).replace("\\", "\\\\") + '"\naddress = "127.0.0.1:5557"\n',
        encoding="utf-8",
    )
    return str(maa), str(adb), config


def make_mumu(tmp_path: Path) -> str:
    mumu = tmp_path / "mumu-cli.exe"
    mumu.touch()
    return str(mumu)


def success_prefix(maa: str, config: Path) -> list[ExpectedCall]:
    return [
        ExpectedCall((maa, "--version"), CommandResult(0, "maa 0.7.5\n")),
        ExpectedCall((maa, "list"), CommandResult(0, "daily\nweekly\n")),
        ExpectedCall(
            (maa, "run", "daily", "--batch", "--dry-run"),
            CommandResult(0, "Summary\n"),
        ),
        ExpectedCall((maa, "dir", "config"), CommandResult(0, str(config) + "\n")),
    ]


def test_preflight_passes_all_steps_and_uses_exact_command_order(tmp_path: Path):
    maa, adb, config = make_paths(tmp_path)
    runner = FakeRunner(
        success_prefix(maa, config)
        + [
            ExpectedCall((adb, "connect", "127.0.0.1:5557"), CommandResult(0, "connected\n")),
            ExpectedCall(
                (adb, "devices", "-l"),
                CommandResult(0, "List of devices attached\n127.0.0.1:5557 device product:test\n"),
            ),
        ]
    )

    report = run_maa_preflight(
        {"executable_path": maa, "task_name": "daily"}, runner=runner
    )

    assert report.ready
    assert not report.emulator_started
    assert [step.state for step in report.steps] == [CheckState.PASSED] * 4
    assert not runner.expected


def test_preflight_writes_and_dry_runs_managed_task_before_emulator_check(tmp_path: Path):
    maa, adb, config = make_paths(tmp_path)
    task_name = "control_plane_daily_test"
    runner = FakeRunner(
        [
            ExpectedCall((maa, "--version"), CommandResult(0, "maa 0.7.5\n")),
            ExpectedCall((maa, "dir", "config"), CommandResult(0, str(config) + "\n")),
            ExpectedCall((maa, "list"), CommandResult(0, task_name + "\n")),
            ExpectedCall(
                (maa, "run", task_name, "--batch", "--dry-run"),
                CommandResult(0, "Summary\n"),
            ),
            ExpectedCall((maa, "dir", "config"), CommandResult(0, str(config) + "\n")),
            ExpectedCall((adb, "connect", "127.0.0.1:5557"), CommandResult(0)),
            ExpectedCall(
                (adb, "devices", "-l"),
                CommandResult(0, "List of devices attached\n127.0.0.1:5557 device\n"),
            ),
        ]
    )

    report = run_maa_preflight(
        {
            "executable_path": maa,
            "task_mode": "managed",
            "task_name": task_name,
            "managed_daily": default_managed_daily(),
        },
        runner=runner,
    )

    generated = config / "tasks" / f"{task_name}.toml"
    assert report.ready
    assert generated.is_file()
    assert "series = 0" in generated.read_text(encoding="utf-8")
    assert str(generated) in report.steps[1].details
    assert not runner.expected


def test_task_name_must_match_a_complete_list_entry(tmp_path: Path):
    maa, _, _ = make_paths(tmp_path)
    runner = FakeRunner(
        [
            ExpectedCall((maa, "--version"), CommandResult(0, "maa 0.7.5\n")),
            ExpectedCall((maa, "list"), CommandResult(0, "daily-extra\n")),
        ]
    )

    report = run_maa_preflight(
        {"executable_path": maa, "task_name": "daily"}, runner=runner
    )

    assert not report.ready
    assert report.failed_step and report.failed_step.key == "task"
    assert "daily-extra" in report.failed_step.next_action
    assert report.steps[2].state == CheckState.PENDING


def test_dry_run_error_is_preserved_for_the_guide(tmp_path: Path):
    maa, _, _ = make_paths(tmp_path)
    runner = FakeRunner(
        [
            ExpectedCall((maa, "--version"), CommandResult(0, "maa 0.7.5\n")),
            ExpectedCall((maa, "list"), CommandResult(0, "daily\n")),
            ExpectedCall(
                (maa, "run", "daily", "--batch", "--dry-run"),
                CommandResult(1, stderr="filename is not set while custom mode is enabled"),
            ),
        ]
    )

    report = run_maa_preflight(
        {"executable_path": maa, "task_name": "daily"}, runner=runner
    )

    assert report.failed_step and report.failed_step.key == "dry_run"
    assert "filename is not set" in report.failed_step.details
    assert report.steps[3].state == CheckState.PENDING


@pytest.mark.parametrize(
    ("device_state", "expected_text"),
    [
        ("offline", "offline"),
        ("unauthorized", "authorized"),
    ],
)
def test_adb_nonready_states_have_specific_guidance(
    tmp_path: Path, device_state: str, expected_text: str
):
    maa, adb, config = make_paths(tmp_path)
    runner = FakeRunner(
        success_prefix(maa, config)
        + [
            ExpectedCall((adb, "connect", "127.0.0.1:5557"), CommandResult(0)),
            ExpectedCall(
                (adb, "devices", "-l"),
                CommandResult(0, f"List of devices attached\n127.0.0.1:5557 {device_state}\n"),
            ),
        ]
    )

    report = run_maa_preflight(
        {"executable_path": maa, "task_name": "daily"}, runner=runner
    )

    assert report.failed_step and report.failed_step.key == "adb"
    assert expected_text in (report.failed_step.summary + report.failed_step.next_action).casefold()


def test_command_start_or_timeout_error_stops_at_executable(tmp_path: Path):
    maa, _, _ = make_paths(tmp_path)
    runner = FakeRunner(
        [ExpectedCall((maa, "--version"), CommandResult(None, error="timed out"))]
    )

    report = run_maa_preflight(
        {"executable_path": maa, "task_name": "daily"}, runner=runner
    )

    assert report.failed_step and report.failed_step.key == "executable"
    assert "timed out" in report.failed_step.details


def test_auto_start_launches_exact_mumu_instance_and_waits_for_adb(tmp_path: Path):
    maa, adb, config_dir = make_paths(tmp_path)
    mumu = make_mumu(tmp_path)
    runner = FakeRunner(
        success_prefix(maa, config_dir)
        + [
            ExpectedCall((adb, "connect", "127.0.0.1:5557"), CommandResult(0)),
            ExpectedCall((adb, "devices", "-l"), CommandResult(0, "List of devices attached\n")),
            ExpectedCall(
                (mumu, "info", "--vmindex", "1"),
                CommandResult(0, '{"error_code":0,"is_process_started":false,"name":"Arknights"}'),
            ),
            ExpectedCall(
                (mumu, "control", "--vmindex", "1", "launch"),
                CommandResult(0, '{"errcode":0,"errmsg":""}'),
            ),
            ExpectedCall((adb, "connect", "127.0.0.1:5557"), CommandResult(0)),
            ExpectedCall(
                (adb, "devices", "-l"),
                CommandResult(0, "List of devices attached\n127.0.0.1:5557 device product:test\n"),
            ),
        ]
    )
    progress: list[str] = []

    report = run_maa_preflight(
        {
            "executable_path": maa,
            "task_name": "daily",
            "auto_start_emulator": True,
            "emulator_type": "mumu",
            "emulator_executable_path": mumu,
            "emulator_instance_index": 1,
            "emulator_start_timeout_seconds": 30,
        },
        runner=runner,
        sleeper=lambda _seconds: None,
        progress=progress.append,
        poll_interval_seconds=1,
    )

    assert report.ready
    assert report.emulator_started
    assert report.steps[-1].summary == "Started MuMu instance 1 and connected at 127.0.0.1:5557."
    assert any("Starting MuMu instance 1" in message for message in progress)
    assert not runner.expected


def test_auto_start_does_not_launch_when_exact_device_is_already_ready(tmp_path: Path):
    maa, adb, config_dir = make_paths(tmp_path)
    mumu = make_mumu(tmp_path)
    runner = FakeRunner(
        success_prefix(maa, config_dir)
        + [
            ExpectedCall((adb, "connect", "127.0.0.1:5557"), CommandResult(0)),
            ExpectedCall(
                (adb, "devices", "-l"),
                CommandResult(0, "List of devices attached\n127.0.0.1:5557 device\n"),
            ),
        ]
    )

    report = run_maa_preflight(
        {
            "executable_path": maa,
            "task_name": "daily",
            "auto_start_emulator": True,
            "emulator_type": "mumu",
            "emulator_executable_path": mumu,
            "emulator_instance_index": 1,
            "emulator_start_timeout_seconds": 30,
        },
        runner=runner,
    )

    assert report.ready
    assert not report.emulator_started
    assert not runner.expected


def test_auto_start_timeout_stops_before_real_maa_run(tmp_path: Path):
    maa, adb, config_dir = make_paths(tmp_path)
    mumu = make_mumu(tmp_path)
    runner = FakeRunner(
        success_prefix(maa, config_dir)
        + [
            ExpectedCall((adb, "connect", "127.0.0.1:5557"), CommandResult(0)),
            ExpectedCall((adb, "devices", "-l"), CommandResult(0, "List of devices attached\n")),
            ExpectedCall(
                (mumu, "info", "--vmindex", "1"),
                CommandResult(0, '{"error_code":0,"is_process_started":false}'),
            ),
            ExpectedCall(
                (mumu, "control", "--vmindex", "1", "launch"),
                CommandResult(0, '{"errcode":0}'),
            ),
            ExpectedCall((adb, "connect", "127.0.0.1:5557"), CommandResult(0)),
            ExpectedCall((adb, "devices", "-l"), CommandResult(0, "List of devices attached\n")),
        ]
    )

    report = run_maa_preflight(
        {
            "executable_path": maa,
            "task_name": "daily",
            "auto_start_emulator": True,
            "emulator_type": "mumu",
            "emulator_executable_path": mumu,
            "emulator_instance_index": 1,
            "emulator_start_timeout_seconds": 1,
        },
        runner=runner,
        sleeper=lambda _seconds: None,
        poll_interval_seconds=1,
    )

    assert not report.ready
    assert report.failed_step and "did not connect within 1 seconds" in report.failed_step.summary
    assert not runner.expected
