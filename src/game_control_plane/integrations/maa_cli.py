from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from ..domain.models import Job
from .base import LaunchSpec, ValidationIssue, ValidationResult
from .maa_managed_task import validate_managed_daily


MAA_CLI_RUNNER_TYPE = "maa_cli"
MAA_CLI_CONFIG_VERSION = 1
MAA_CLI_WINGET_PACKAGE_DIR = (
    "MaaAssistantArknights.maa-cli_Microsoft.Winget.Source_8wekyb3d8bbwe"
)
MUMU_EMULATOR_TYPE = "mumu"
DEFAULT_EMULATOR_START_TIMEOUT_SECONDS = 120


def discover_maa_cli() -> str | None:
    """Find the explicitly installed maa-cli without changing user config."""

    on_path = shutil.which("maa-cli")
    if on_path:
        return str(Path(on_path))

    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        return None
    package_executable = (
        Path(local_app_data)
        / "Microsoft"
        / "WinGet"
        / "Packages"
        / MAA_CLI_WINGET_PACKAGE_DIR
        / "maa-cli.exe"
    )
    return str(package_executable) if package_executable.is_file() else None


def discover_mumu_cli() -> str | None:
    """Find MuMu's supported instance-management CLI without starting it."""

    on_path = shutil.which("mumu-cli")
    if on_path:
        return str(Path(on_path))
    program_files = os.environ.get("ProgramFiles")
    if not program_files:
        return None
    root = Path(program_files) / "Netease"
    candidates = (
        root / "MuMuPlayerGlobal-12.0" / "nx_main" / "mumu-cli.exe",
        root / "MuMuPlayer-12.0" / "nx_main" / "mumu-cli.exe",
        root / "MuMuPlayer-12.0" / "shell" / "MuMuManager.exe",
    )
    return next((str(candidate) for candidate in candidates if candidate.is_file()), None)


class MaaCliIntegration:
    runner_type = MAA_CLI_RUNNER_TYPE
    display_name = "MAA"
    config_version = MAA_CLI_CONFIG_VERSION

    def validate_config(self, config: dict[str, object]) -> ValidationResult:
        errors: list[str] = []
        executable_value = config.get("executable_path")
        if not isinstance(executable_value, str) or not executable_value.strip():
            errors.append("MAA executable path is required.")
        else:
            executable = Path(executable_value.strip()).expanduser()
            if not executable.is_absolute():
                errors.append("MAA executable path must be absolute.")
            elif not executable.exists():
                errors.append(f"MAA executable was not found: {executable}")
            elif not executable.is_file():
                errors.append(f"MAA executable path is not a file: {executable}")
            elif not os.access(executable, os.X_OK) and os.name != "nt":
                errors.append(f"MAA executable is not runnable: {executable}")

        task_value = config.get("task_name")
        if not isinstance(task_value, str) or not task_value.strip():
            errors.append("MAA task name is required.")
        errors.extend(validate_managed_daily(config))

        auto_start = config.get("auto_start_emulator", False)
        close_after = config.get("close_emulator_after_run", False)
        if not isinstance(close_after, bool):
            errors.append("Close emulator after run must be enabled or disabled.")
        elif close_after and auto_start is not True:
            errors.append("Closing the emulator after a run requires automatic emulator startup.")
        if not isinstance(auto_start, bool):
            errors.append("Auto-start emulator must be enabled or disabled.")
        elif auto_start:
            emulator_type = config.get("emulator_type", MUMU_EMULATOR_TYPE)
            if emulator_type != MUMU_EMULATOR_TYPE:
                errors.append(f"Unsupported emulator auto-start type: {emulator_type}")
            emulator_value = config.get("emulator_executable_path")
            if not isinstance(emulator_value, str) or not emulator_value.strip():
                errors.append("MuMu command tool path is required for automatic startup.")
            else:
                emulator_executable = Path(emulator_value.strip()).expanduser()
                if not emulator_executable.is_absolute():
                    errors.append("MuMu command tool path must be absolute.")
                elif not emulator_executable.is_file():
                    errors.append(f"MuMu command tool was not found: {emulator_executable}")
            instance = config.get("emulator_instance_index")
            if isinstance(instance, bool) or not isinstance(instance, int) or instance < 0:
                errors.append("MuMu instance number must be zero or greater.")
            timeout = config.get(
                "emulator_start_timeout_seconds",
                DEFAULT_EMULATOR_START_TIMEOUT_SECONDS,
            )
            if isinstance(timeout, bool) or not isinstance(timeout, int) or not 30 <= timeout <= 600:
                errors.append("Emulator startup timeout must be between 30 and 600 seconds.")

        version = config.get("config_version", self.config_version)
        if version != self.config_version:
            errors.append(f"Unsupported MAA configuration version: {version}")
        return ValidationResult(
            valid=not errors,
            errors=tuple(errors),
            issues=(
                ValidationIssue(
                    "maa.configuration.invalid",
                    {"runner": self.runner_type},
                    " ".join(errors),
                ),
            )
            if errors
            else (),
        )

    def build_launch_spec(self, job: Job) -> LaunchSpec:
        config = job.runner_config
        result = self.validate_config(config)
        if not result.valid:
            raise ValueError(" ".join(result.errors))
        executable = str(config["executable_path"]).strip()
        task_name = str(config["task_name"]).strip()
        arguments = ("run", task_name, "--batch")
        display_command = subprocess.list2cmdline((executable, *arguments))
        return LaunchSpec(
            executable=executable,
            arguments=arguments,
            working_directory=None,
            display_command=display_command,
        )


__all__ = [
    "MAA_CLI_CONFIG_VERSION",
    "MAA_CLI_RUNNER_TYPE",
    "MUMU_EMULATOR_TYPE",
    "DEFAULT_EMULATOR_START_TIMEOUT_SECONDS",
    "MaaCliIntegration",
    "discover_maa_cli",
    "discover_mumu_cli",
]
