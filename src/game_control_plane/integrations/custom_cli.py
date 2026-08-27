from __future__ import annotations

import os
import subprocess
from pathlib import Path

from ..domain.models import Job
from .base import LaunchSpec, ValidationResult


class CustomCliIntegration:
    runner_type = "custom_cli"
    display_name = "Custom CLI"
    config_version = 1

    def validate_config(self, config: dict[str, object]) -> ValidationResult:
        errors: list[str] = []
        executable_value = config.get("executable_path")
        if not isinstance(executable_value, str) or not executable_value.strip():
            errors.append("Executable or interpreter path is required.")
        else:
            executable = Path(executable_value.strip()).expanduser()
            if not executable.is_absolute():
                errors.append("Executable or interpreter path must be absolute.")
            elif not executable.exists():
                errors.append(f"Executable was not found: {executable}")
            elif not executable.is_file():
                errors.append(f"Executable path is not a file: {executable}")
            elif not os.access(executable, os.X_OK) and os.name != "nt":
                errors.append(f"Executable is not runnable: {executable}")

        arguments = config.get("arguments", [])
        if not isinstance(arguments, list) or any(not isinstance(item, str) for item in arguments):
            errors.append("Arguments must be a list of text values.")

        working_value = config.get("working_directory")
        if working_value in (None, ""):
            pass
        elif not isinstance(working_value, str):
            errors.append("Working directory must be a text path.")
        else:
            working_directory = Path(working_value).expanduser()
            if not working_directory.is_absolute():
                errors.append("Working directory must be absolute when provided.")
            elif not working_directory.exists():
                errors.append(f"Working directory was not found: {working_directory}")
            elif not working_directory.is_dir():
                errors.append(f"Working directory is not a folder: {working_directory}")

        version = config.get("config_version", self.config_version)
        if version != self.config_version:
            errors.append(f"Unsupported Custom CLI configuration version: {version}")
        return ValidationResult(valid=not errors, errors=tuple(errors))

    def build_launch_spec(self, job: Job) -> LaunchSpec:
        config = job.runner_config
        result = self.validate_config(config)
        if not result.valid:
            raise ValueError(" ".join(result.errors))
        executable = str(config["executable_path"])
        arguments = tuple(str(item) for item in config.get("arguments", []))
        working_value = config.get("working_directory")
        working_directory = str(working_value) if working_value else None
        display_command = subprocess.list2cmdline((executable, *arguments))
        return LaunchSpec(
            executable=executable,
            arguments=arguments,
            working_directory=working_directory,
            display_command=display_command,
        )
