import json
from pathlib import Path

from game_control_plane.domain.models import Job
from game_control_plane.integrations import ok_ww
from game_control_plane.integrations.ok_ww import OkWwIntegration, discover_ok_ww
from game_control_plane.integrations.registry import default_registry


def make_job(
    executable: Path,
    task_index: int = 1,
    close_game_after_run: bool | None = None,
) -> Job:
    config = {
        "config_version": 1,
        "executable_path": str(executable),
        "task_index": task_index,
    }
    if close_game_after_run is not None:
        config["close_game_after_run"] = close_game_after_run
    return Job(
        id=1,
        game_id=1,
        game_name="Wuthering Waves",
        name="OK-WW daily",
        runner_type="ok_ww",
        runner_config_version=1,
        runner_config_json=json.dumps(config),
        enabled=True,
        queue_order=1,
        timezone_id="Asia/Shanghai",
        reset_minute=240,
    )


def test_ok_ww_builds_exact_task_and_exit_launch_spec(tmp_path: Path):
    executable = tmp_path / "ok-ww.exe"
    executable.write_text("fixture", encoding="utf-8")
    integration = OkWwIntegration()
    job = make_job(executable, task_index=3)

    result = integration.validate_config(job.runner_config)
    assert result.valid
    spec = integration.build_launch_spec(job)
    assert spec.executable == str(executable)
    assert spec.arguments == ("-t", "3", "-e")
    assert spec.working_directory == str(tmp_path)
    assert spec.display_command.endswith("ok-ww.exe -t 3 -e")
    assert spec.handoff_process_names == ("pythonw.exe", "python.exe")


def test_ok_ww_can_leave_game_open_and_old_configs_keep_exit_behavior(tmp_path: Path):
    executable = tmp_path / "ok-ww.exe"
    executable.write_text("fixture", encoding="utf-8")
    integration = OkWwIntegration()

    leave_open = integration.build_launch_spec(
        make_job(executable, task_index=2, close_game_after_run=False)
    )
    old_config = integration.build_launch_spec(make_job(executable, task_index=2))

    assert leave_open.arguments == ("-t", "2")
    assert old_config.arguments == ("-t", "2", "-e")


def test_ok_ww_rejects_missing_executable_and_nonpositive_task(tmp_path: Path):
    result = OkWwIntegration().validate_config(
        {
            "config_version": 1,
            "executable_path": str(tmp_path / "missing.exe"),
            "task_index": 0,
        }
    )
    assert not result.valid
    assert any("not found" in error for error in result.errors)
    assert any("positive integer" in error for error in result.errors)


def test_discovery_prefers_path_then_explicit_env_then_shortcut(tmp_path: Path, monkeypatch):
    on_path = tmp_path / "path" / "ok-ww.exe"
    on_path.parent.mkdir()
    on_path.write_text("fixture", encoding="utf-8")
    monkeypatch.setattr(ok_ww.shutil, "which", lambda name: str(on_path))
    monkeypatch.setenv(ok_ww.OK_WW_EXECUTABLE_ENV, str(tmp_path / "env.exe"))
    assert discover_ok_ww() == str(on_path)

    monkeypatch.setattr(ok_ww.shutil, "which", lambda name: None)
    env_executable = tmp_path / "env.exe"
    env_executable.write_text("fixture", encoding="utf-8")
    assert discover_ok_ww() == str(env_executable)


def test_shortcut_target_discovery_requires_existing_ok_ww_file(tmp_path: Path, monkeypatch):
    executable = tmp_path / "automation" / "ok-ww.exe"
    executable.parent.mkdir()
    executable.write_text("fixture", encoding="utf-8")
    shortcut = tmp_path / "ok-ww.exe - Shortcut.lnk"
    ansi_path = str(executable).encode("utf-8") + b"\x00"
    unicode_path = str(executable).encode("utf-16-le") + b"\x00\x00"
    local_path_offset = 0x24
    unicode_path_offset = local_path_offset + len(ansi_path)
    link_info_size = unicode_path_offset + len(unicode_path)
    header = bytearray(76)
    header[0:4] = b"\x4c\x00\x00\x00"
    header[0x14:0x18] = (0x02).to_bytes(4, "little")
    link_info = bytearray(link_info_size)
    link_info[0:4] = link_info_size.to_bytes(4, "little")
    link_info[4:8] = (0x24).to_bytes(4, "little")
    link_info[0x10:0x14] = local_path_offset.to_bytes(4, "little")
    link_info[0x1C:0x20] = unicode_path_offset.to_bytes(4, "little")
    link_info[local_path_offset:unicode_path_offset] = ansi_path
    link_info[unicode_path_offset:] = unicode_path
    shortcut.write_bytes(bytes(header) + bytes(link_info))

    monkeypatch.setattr(ok_ww.shutil, "which", lambda name: None)
    monkeypatch.setenv(ok_ww.OK_WW_EXECUTABLE_ENV, "")
    monkeypatch.setattr(ok_ww, "_shortcut_roots", lambda: (tmp_path,))
    assert discover_ok_ww() == str(executable)


def test_default_registry_registers_ok_ww():
    registry = default_registry()
    assert registry.get("ok_ww").display_name == "OK-WW"
    assert registry.types() == ("custom_cli", "maa_cli", "maa_punish", "ok_ww", "zzz_onedragon")
