from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..domain.models import Job


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    @classmethod
    def ok(cls) -> "ValidationResult":
        return cls(valid=True)


@dataclass(frozen=True)
class LaunchSpec:
    executable: str
    arguments: tuple[str, ...]
    working_directory: str | None
    display_command: str
    handoff_process_names: tuple[str, ...] = ()


class Integration(Protocol):
    runner_type: str
    display_name: str
    config_version: int

    def validate_config(self, config: dict[str, object]) -> ValidationResult:
        ...

    def build_launch_spec(self, job: Job) -> LaunchSpec:
        ...
