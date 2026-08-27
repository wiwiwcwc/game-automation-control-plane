from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass

from ..domain.models import Job
from ..integrations.maa_cli import MAA_CLI_RUNNER_TYPE
from ..integrations.maa_punish import MAA_PUNISH_RUNNER_TYPE


_MUMU_RUNNER_TYPES = {MAA_CLI_RUNNER_TYPE, MAA_PUNISH_RUNNER_TYPE}


@dataclass(frozen=True)
class PostRunAction:
    executable: str
    arguments: tuple[str, ...]
    display_command: str
    description: str


def mumu_resource_key(job: Job) -> tuple[str, str, int] | None:
    """Identify a MuMu instance that must not be shared by concurrent jobs."""

    if job.runner_type not in _MUMU_RUNNER_TYPES:
        return None
    config = job.runner_config
    if not bool(config.get("auto_start_emulator", False)):
        return None
    executable_value = str(config.get("emulator_executable_path", "")).strip()
    executable = os.path.normcase(os.path.abspath(executable_value)) if executable_value else ""
    instance = config.get("emulator_instance_index")
    if not executable or isinstance(instance, bool) or not isinstance(instance, int):
        return None
    return ("mumu", executable, instance)


def create_post_run_action(
    job: Job,
    runtime_context: dict[str, object] | None = None,
) -> PostRunAction | None:
    """Return a safe, run-scoped cleanup action when its ownership proof exists."""

    if job.runner_type not in _MUMU_RUNNER_TYPES:
        return None
    config = job.runner_config
    context = runtime_context or {}
    if not bool(config.get("auto_start_emulator", False)):
        return None
    if not bool(config.get("close_emulator_after_run", False)):
        return None
    if not bool(context.get("emulator_started_by_control_plane", False)):
        return None
    executable = str(config.get("emulator_executable_path", "")).strip()
    instance = config.get("emulator_instance_index")
    if not executable or isinstance(instance, bool) or not isinstance(instance, int) or instance < 0:
        return None
    arguments = ("control", "--vmindex", str(instance), "shutdown")
    return PostRunAction(
        executable=executable,
        arguments=arguments,
        display_command=subprocess.list2cmdline((executable, *arguments)),
        description=f"Close MuMu instance {instance}",
    )


__all__ = ["PostRunAction", "create_post_run_action", "mumu_resource_key"]
