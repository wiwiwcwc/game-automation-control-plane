from __future__ import annotations

import json
from pathlib import Path

import pytest

from game_control_plane.domain.models import Job
from game_control_plane.integrations import onedragon
from game_control_plane.integrations.onedragon import (
    ZZZ_ONEDRAGON_CLASSIC_NAME,
    ZZZ_ONEDRAGON_RUNTIME_NAME,
    ZzzOneDragonIntegration,
    discover_zzz_onedragon,
    parse_instance_indices,
)
from game_control_plane.integrations.onedragon_preflight import run_onedragon_preflight
from game_control_plane.integrations.maa_preflight import CheckState
from game_control_plane.integrations.registry import default_registry


def make_job(executable: Path, *, instances: str = "", close_game: bool = False) -> Job:
    config = {
        "config_version": 1,
        "executable_path": str(executable),
        "instance_indices": instances,
        "close_game_after_run": close_game,
    }
    return Job(
        id=1,
        game_id=1,
        game_name="Zenless Zone Zero",
        name="ZZZ daily",
        runner_type="zzz_onedragon",
        runner_config_version=1,
        runner_config_json=json.dumps(config),
        enabled=True,
        queue_order=1,
        timezone_id="Asia/Shanghai",
        reset_minute=240,
    )


def test_instance_parser_accepts_active_account_or_positive_indices():
    assert parse_instance_indices("") == ()
    assert parse_instance_indices(" 1, 2 ") == (1, 2)


@pytest.mark.parametrize("value", ["0", "-1", "1,,2", "one", "1,1", 1])
def test_instance_parser_rejects_non_positive_or_non_comma_values(value):
    with pytest.raises(ValueError):
        parse_instance_indices(value)


def test_runtime_launch_spec_uses_exact_official_arguments_and_parent_directory(tmp_path: Path):
    executable = tmp_path / ZZZ_ONEDRAGON_RUNTIME_NAME
    executable.touch()
    spec = ZzzOneDragonIntegration().build_launch_spec(
        make_job(executable, instances="1,2", close_game=True)
    )

    assert spec.executable == str(executable)
    assert spec.arguments == ("-o", "-i", "1,2", "-c")
    assert spec.working_directory == str(tmp_path)
    assert spec.display_command.endswith(
        "OneDragon-RuntimeLauncher.exe -o -i 1,2 -c"
    )
    assert spec.handoff_process_names == ()


def test_adapter_rejects_unrelated_executable_name(tmp_path: Path):
    executable = tmp_path / "OneDragon.exe"
    executable.touch()
    result = ZzzOneDragonIntegration().validate_config(
        {"config_version": 1, "executable_path": str(executable)}
    )
    assert not result.valid
    assert any("RuntimeLauncher" in error for error in result.errors)


def test_discovery_prefers_runtime_on_path_then_falls_back_to_classic(tmp_path: Path, monkeypatch):
    runtime = tmp_path / ZZZ_ONEDRAGON_RUNTIME_NAME
    classic = tmp_path / ZZZ_ONEDRAGON_CLASSIC_NAME
    runtime.touch()
    classic.touch()

    monkeypatch.setattr(
        onedragon.shutil,
        "which",
        lambda name: str(runtime) if name.casefold() == ZZZ_ONEDRAGON_RUNTIME_NAME.casefold() else None,
    )
    monkeypatch.setenv(onedragon.ZZZ_ONEDRAGON_EXECUTABLE_ENV, str(classic))
    assert discover_zzz_onedragon() == str(runtime)

    monkeypatch.setattr(onedragon.shutil, "which", lambda _name: None)
    assert discover_zzz_onedragon() == str(classic)


def test_discovery_checks_only_immediate_common_root_children(tmp_path: Path, monkeypatch):
    install = tmp_path / "OneDragon"
    install.mkdir()
    runtime = install / ZZZ_ONEDRAGON_RUNTIME_NAME
    runtime.touch()
    monkeypatch.setattr(onedragon.shutil, "which", lambda _name: None)
    monkeypatch.delenv(onedragon.ZZZ_ONEDRAGON_EXECUTABLE_ENV, raising=False)
    monkeypatch.setattr(onedragon, "_candidate_roots", lambda: (tmp_path,))
    assert discover_zzz_onedragon() == str(runtime)


def test_runtime_preflight_requires_adjacent_runtime_and_source_directories(tmp_path: Path):
    executable = tmp_path / ZZZ_ONEDRAGON_RUNTIME_NAME
    executable.touch()
    report = run_onedragon_preflight(
        {
            "config_version": 1,
            "executable_path": str(executable),
            "instance_indices": "",
            "close_game_after_run": False,
        }
    )
    assert report.kind == "onedragon"
    assert not report.ready
    assert report.failed_step and report.failed_step.key == "layout"
    assert report.steps[2].state == CheckState.PENDING

    (tmp_path / ".runtime").mkdir()
    (tmp_path / "src").mkdir()
    ready = run_onedragon_preflight(
        {
            "config_version": 1,
            "executable_path": str(executable),
            "instance_indices": "1,2",
            "close_game_after_run": True,
        }
    )
    assert ready.ready
    assert [step.key for step in ready.steps] == ["executable", "layout", "accounts", "launch"]
    assert "-i 1,2 -c" in ready.steps[-1].summary


def test_classic_preflight_accepts_full_environment_root_config(tmp_path: Path):
    install = tmp_path / "ZenlessZoneZero-OneDragon-v2.5.1-Full-Environment"
    install.mkdir()
    executable = install / ZZZ_ONEDRAGON_CLASSIC_NAME
    executable.touch()
    (install / "config").mkdir()
    (install / "config" / "project.yml").write_text("name: zzz", encoding="utf-8")
    (install / "config" / "repository.yml").write_text("name: repo", encoding="utf-8")
    report = run_onedragon_preflight(
        {
            "config_version": 1,
            "executable_path": str(executable),
            "instance_indices": "3",
            "close_game_after_run": False,
        }
    )
    assert report.ready
    assert "Full-Environment" in report.steps[1].summary
    assert "account instances 3" in report.steps[2].summary


def test_classic_preflight_accepts_resources_config_compatibility_layout(tmp_path: Path):
    executable = tmp_path / ZZZ_ONEDRAGON_CLASSIC_NAME
    executable.touch()
    config_root = tmp_path / "resources" / "config"
    config_root.mkdir(parents=True)
    (config_root / "project.yml").write_text("name: zzz", encoding="utf-8")
    (config_root / "repository.yml").write_text("name: repo", encoding="utf-8")

    report = run_onedragon_preflight(
        {
            "config_version": 1,
            "executable_path": str(executable),
            "instance_indices": "",
            "close_game_after_run": False,
        }
    )

    assert report.ready
    assert "resources/config" in report.steps[1].summary


def test_classic_preflight_rejects_mixed_classic_config_layouts(tmp_path: Path):
    executable = tmp_path / ZZZ_ONEDRAGON_CLASSIC_NAME
    executable.touch()
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "project.yml").write_text("name: zzz", encoding="utf-8")
    resources_config = tmp_path / "resources" / "config"
    resources_config.mkdir(parents=True)
    (resources_config / "repository.yml").write_text("name: repo", encoding="utf-8")

    report = run_onedragon_preflight(
        {
            "config_version": 1,
            "executable_path": str(executable),
            "instance_indices": "",
            "close_game_after_run": False,
        }
    )

    assert not report.ready
    assert report.failed_step and report.failed_step.key == "layout"
    assert "one complete config pair" in report.failed_step.summary
    assert "Do not move YAML files" in report.failed_step.next_action
    assert "config/repository.yml" in report.failed_step.details
    assert "resources/config/project.yml" in report.failed_step.details


def test_classic_preflight_rejects_incomplete_classic_config_layouts(tmp_path: Path):
    executable = tmp_path / ZZZ_ONEDRAGON_CLASSIC_NAME
    executable.touch()
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "project.yml").write_text("name: zzz", encoding="utf-8")
    resources_config = tmp_path / "resources" / "config"
    resources_config.mkdir(parents=True)
    (resources_config / "project.yml").write_text("name: zzz", encoding="utf-8")

    report = run_onedragon_preflight(
        {
            "config_version": 1,
            "executable_path": str(executable),
            "instance_indices": "",
            "close_game_after_run": False,
        }
    )

    assert not report.ready
    assert report.failed_step and report.failed_step.key == "layout"
    assert "config/repository.yml" in report.failed_step.details
    assert "resources/config/repository.yml" in report.failed_step.details


def test_preflight_reuses_adapter_validation_for_version_and_boolean_errors(tmp_path: Path):
    executable = tmp_path / ZZZ_ONEDRAGON_RUNTIME_NAME
    executable.touch()
    (tmp_path / ".runtime").mkdir()
    (tmp_path / "src").mkdir()
    report = run_onedragon_preflight(
        {
            "config_version": 99,
            "executable_path": str(executable),
            "instance_indices": "1",
            "close_game_after_run": "yes",
        }
    )
    assert not report.ready
    assert report.failed_step and report.failed_step.key == "launch"
    assert "configuration version" in report.failed_step.summary
    assert "Close Zenless Zone Zero" in report.failed_step.summary


def test_default_registry_registers_zzz_onedragon():
    registry = default_registry()
    assert registry.get("zzz_onedragon").display_name == "绝区零 OneDragon"
    assert registry.types() == (
        "custom_cli",
        "maa_cli",
        "maa_punish",
        "ok_ww",
        "zzz_onedragon",
    )
