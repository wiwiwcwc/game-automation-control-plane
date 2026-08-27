from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from ..domain.models import Job
from .base import LaunchSpec, ValidationResult
from .maa_cli import (
    DEFAULT_EMULATOR_START_TIMEOUT_SECONDS,
    MUMU_EMULATOR_TYPE,
    discover_mumu_cli,
)


MAA_PUNISH_RUNNER_TYPE = "maa_punish"
MAA_PUNISH_CONFIG_VERSION = 1
INTERNAL_FOS_RUNNER_ARG = "--internal-fos-runner"


@dataclass(frozen=True)
class FosConfiguration:
    config_id: str
    name: str
    path: Path


@dataclass(frozen=True)
class FosController:
    controller_type: str
    adb_path: str = ""
    address: str = ""
    mumu_index: int | None = None
    mumu_path: str = ""


def discover_fos() -> str | None:
    """Find a released MAA_Punish FOS.exe without scanning broad drives."""

    on_path = shutil.which("FOS") or shutil.which("FOS.exe")
    if on_path:
        return str(Path(on_path))

    roots: list[Path] = []
    user_profile = os.environ.get("USERPROFILE")
    if user_profile:
        roots.extend((Path(user_profile) / "Desktop", Path(user_profile) / "Downloads"))
        roots.append(Path(user_profile) / "OneDrive" / "Desktop")

    candidates: list[Path] = []
    for root in roots:
        if not root.is_dir():
            continue
        candidates.extend(path for path in root.glob("MPA*/FOS.exe") if path.is_file())
        candidates.extend(path for path in root.glob("MAA_Punish*/FOS.exe") if path.is_file())
    if not candidates:
        return None
    candidates.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return str(candidates[0])


def discover_fos_configurations(executable: str | Path) -> tuple[FosConfiguration, ...]:
    root = Path(executable).expanduser().resolve().parent
    config_dir = root / "config" / "configs"
    if not config_dir.is_dir():
        return ()

    configurations: list[FosConfiguration] = []
    for path in sorted(config_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        config_id = str(payload.get("item_id") or path.stem).strip()
        name = str(payload.get("name") or config_id).strip()
        if config_id:
            configurations.append(FosConfiguration(config_id, name, path))
    return tuple(configurations)


def find_fos_configuration(
    executable: str | Path,
    config_id: str,
) -> FosConfiguration | None:
    return next(
        (
            configuration
            for configuration in discover_fos_configurations(executable)
            if configuration.config_id == config_id
        ),
        None,
    )


def read_fos_controller(configuration: FosConfiguration) -> FosController | None:
    try:
        payload = json.loads(configuration.path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    tasks = payload.get("tasks") if isinstance(payload, dict) else None
    if not isinstance(tasks, list):
        return None
    controller_task = next(
        (
            task
            for task in tasks
            if isinstance(task, dict)
            and task.get("item_id", task.get("name")) == "Controller"
        ),
        None,
    )
    if not isinstance(controller_task, dict):
        return None
    options = controller_task.get("task_option")
    if not isinstance(options, dict):
        return None
    controller_type = str(options.get("controller_type") or "").strip()
    selected = options.get(controller_type)
    if not isinstance(selected, dict) and controller_type == "Android":
        selected = options.get("安卓端")
    if not isinstance(selected, dict):
        return FosController(controller_type=controller_type)

    extras = selected.get("config")
    extras = extras.get("extras") if isinstance(extras, dict) else None
    mumu = extras.get("mumu") if isinstance(extras, dict) else None
    index = mumu.get("index") if isinstance(mumu, dict) else None
    if isinstance(index, bool) or not isinstance(index, int) or index < 0:
        index = None
    return FosController(
        controller_type=controller_type,
        adb_path=str(selected.get("adb_path") or "").strip(),
        address=str(selected.get("address") or "").strip(),
        mumu_index=index,
        mumu_path=str(mumu.get("path") or "").strip() if isinstance(mumu, dict) else "",
    )


def discover_fos_mumu_cli(controller: FosController | None) -> str | None:
    if controller is not None and controller.mumu_path:
        root = Path(controller.mumu_path).expanduser()
        candidates = (
            root / "nx_main" / "mumu-cli.exe",
            root / "shell" / "MuMuManager.exe",
        )
        found = next((candidate for candidate in candidates if candidate.is_file()), None)
        if found is not None:
            return str(found)
    return discover_mumu_cli()


def _internal_runner_command(
    fos_executable: str,
    config_id: str,
    close_fos_after_run: bool,
) -> tuple[str, tuple[str, ...]]:
    runner_arguments = [
        INTERNAL_FOS_RUNNER_ARG,
        "--fos-executable",
        fos_executable,
        "--config-id",
        config_id,
    ]
    if close_fos_after_run:
        runner_arguments.append("--close-fos-after-run")
    if getattr(sys, "frozen", False):
        return sys.executable, tuple(runner_arguments)
    return sys.executable, ("-m", "game_control_plane", *runner_arguments)


class MaaPunishIntegration:
    runner_type = MAA_PUNISH_RUNNER_TYPE
    display_name = "MAA_Punish"
    config_version = MAA_PUNISH_CONFIG_VERSION

    def validate_config(self, config: dict[str, object]) -> ValidationResult:
        errors: list[str] = []
        executable_value = config.get("executable_path")
        executable = (
            Path(executable_value.strip()).expanduser()
            if isinstance(executable_value, str) and executable_value.strip()
            else None
        )
        if executable is None:
            errors.append("FOS executable path is required.")
        elif not executable.is_absolute():
            errors.append("FOS executable path must be absolute.")
        elif not executable.is_file():
            errors.append(f"FOS executable was not found: {executable}")

        config_value = config.get("config_id")
        config_id = config_value.strip() if isinstance(config_value, str) else ""
        if not config_id:
            errors.append("FOS configuration is required.")
        selected_configuration = None
        if config_id and executable is not None and executable.is_file():
            selected_configuration = find_fos_configuration(executable, config_id)
            if selected_configuration is None:
                errors.append(f"FOS configuration was not found: {config_id}")

        auto_start = config.get("auto_start_emulator", False)
        close_after = config.get("close_emulator_after_run", False)
        close_fos_after = config.get("close_fos_after_run", True)
        if not isinstance(auto_start, bool):
            errors.append("Auto-start emulator must be enabled or disabled.")
        if not isinstance(close_after, bool):
            errors.append("Close emulator after run must be enabled or disabled.")
        elif close_after and auto_start is not True:
            errors.append("Closing the emulator after a run requires automatic emulator startup.")
        if not isinstance(close_fos_after, bool):
            errors.append("Close FOS after run must be enabled or disabled.")
        if auto_start is True:
            controller = (
                read_fos_controller(selected_configuration)
                if selected_configuration is not None
                else None
            )
            if (
                controller is None
                or controller.controller_type != "Android"
                or controller.mumu_index is None
            ):
                errors.append(
                    "The selected FOS configuration is not associated with a MuMu Android instance."
                )
            if config.get("emulator_type", MUMU_EMULATOR_TYPE) != MUMU_EMULATOR_TYPE:
                errors.append("Only MuMu automatic startup is supported for FOS.")
            emulator_value = config.get("emulator_executable_path")
            emulator = (
                Path(emulator_value.strip()).expanduser()
                if isinstance(emulator_value, str) and emulator_value.strip()
                else None
            )
            if emulator is None or not emulator.is_absolute() or not emulator.is_file():
                errors.append("MuMu command tool path is required for automatic startup.")
            instance = config.get("emulator_instance_index")
            if isinstance(instance, bool) or not isinstance(instance, int) or instance < 0:
                errors.append("MuMu instance number must be zero or greater.")
            elif controller is not None and controller.mumu_index is not None:
                if instance != controller.mumu_index:
                    errors.append(
                        "The MuMu instance number does not match the selected FOS configuration."
                    )
            timeout = config.get(
                "emulator_start_timeout_seconds",
                DEFAULT_EMULATOR_START_TIMEOUT_SECONDS,
            )
            if isinstance(timeout, bool) or not isinstance(timeout, int) or not 30 <= timeout <= 600:
                errors.append("Emulator startup timeout must be between 30 and 600 seconds.")

        version = config.get("config_version", self.config_version)
        if version != self.config_version:
            errors.append(f"Unsupported MAA_Punish configuration version: {version}")
        return ValidationResult(valid=not errors, errors=tuple(errors))

    def build_launch_spec(self, job: Job) -> LaunchSpec:
        config = job.runner_config
        result = self.validate_config(config)
        if not result.valid:
            raise ValueError(" ".join(result.errors))
        fos_executable = str(config["executable_path"]).strip()
        config_id = str(config["config_id"]).strip()
        close_fos_after_run = bool(config.get("close_fos_after_run", True))
        executable, arguments = _internal_runner_command(
            fos_executable,
            config_id,
            close_fos_after_run,
        )
        display_arguments = (
            "--direct-run",
            "--reuse-existing",
            "--config-id",
            config_id,
        )
        return LaunchSpec(
            executable=executable,
            arguments=arguments,
            working_directory=str(Path(fos_executable).parent),
            display_command=subprocess.list2cmdline((fos_executable, *display_arguments)),
        )


__all__ = [
    "FosConfiguration",
    "FosController",
    "INTERNAL_FOS_RUNNER_ARG",
    "MAA_PUNISH_CONFIG_VERSION",
    "MAA_PUNISH_RUNNER_TYPE",
    "MaaPunishIntegration",
    "discover_fos",
    "discover_fos_configurations",
    "discover_fos_mumu_cli",
    "find_fos_configuration",
    "read_fos_controller",
]
