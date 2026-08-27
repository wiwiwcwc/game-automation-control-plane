import sys
from pathlib import Path

from game_control_plane.domain.models import Job
from game_control_plane.integrations.custom_cli import CustomCliIntegration


def make_job(script: Path) -> Job:
    import json

    return Job(
        id=1,
        game_id=1,
        game_name="Fixture",
        name="Fixture job",
        runner_type="custom_cli",
        runner_config_version=1,
        runner_config_json=json.dumps(
            {
                "config_version": 1,
                "executable_path": sys.executable,
                "arguments": [str(script), "--mode", "success"],
                "working_directory": str(script.parent),
            }
        ),
        enabled=True,
        queue_order=1,
        timezone_id="Asia/Shanghai",
        reset_minute=240,
    )


def test_custom_cli_builds_direct_launch_spec(tmp_path: Path):
    script = tmp_path / "fixture.py"
    script.write_text("print('ok')", encoding="utf-8")
    integration = CustomCliIntegration()
    job = make_job(script)
    result = integration.validate_config(job.runner_config)
    assert result.valid
    spec = integration.build_launch_spec(job)
    assert spec.executable == sys.executable
    assert spec.arguments[0] == str(script)
    assert spec.working_directory == str(tmp_path)
    assert spec.handoff_process_names == ()


def test_custom_cli_rejects_missing_executable(tmp_path: Path):
    result = CustomCliIntegration().validate_config(
        {
            "config_version": 1,
            "executable_path": str(tmp_path / "missing.exe"),
            "arguments": [],
            "working_directory": None,
        }
    )
    assert not result.valid
    assert any("not found" in error for error in result.errors)
