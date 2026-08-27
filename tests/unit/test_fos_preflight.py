from __future__ import annotations

from game_control_plane.integrations.fos_preflight import run_fos_preflight
from game_control_plane.integrations.maa_preflight import CommandResult
from tests.unit.test_maa_punish import make_fos


class FakeRunner:
    def __init__(self, results):
        self.results = list(results)
        self.commands = []

    def run(self, command, timeout_seconds):
        self.commands.append((tuple(command), timeout_seconds))
        return self.results.pop(0)


def test_fos_preflight_accepts_saved_configuration_without_auto_start(tmp_path):
    fos, config_id = make_fos(tmp_path)
    report = run_fos_preflight(
        {
            "config_version": 1,
            "executable_path": str(fos),
            "config_id": config_id,
        }
    )
    assert report.ready
    assert report.kind == "fos"
    assert report.emulator_started is False


def test_fos_preflight_starts_saved_mumu_instance_and_records_ownership(tmp_path):
    fos, config_id = make_fos(tmp_path)
    mumu = tmp_path / "mumu-cli.exe"
    mumu.touch()
    runner = FakeRunner(
        [
            CommandResult(0, '{"error_code":0,"is_process_started":false,"is_android_started":false}'),
            CommandResult(0, '{"error_code":0}'),
            CommandResult(0, '{"error_code":0,"is_process_started":true,"is_android_started":true}'),
        ]
    )
    report = run_fos_preflight(
        {
            "config_version": 1,
            "executable_path": str(fos),
            "config_id": config_id,
            "auto_start_emulator": True,
            "emulator_executable_path": str(mumu),
            "emulator_instance_index": 0,
            "emulator_start_timeout_seconds": 30,
        },
        runner=runner,
        sleeper=lambda _seconds: None,
    )
    assert report.ready
    assert report.emulator_started
    assert runner.commands[1][0][-1] == "launch"
