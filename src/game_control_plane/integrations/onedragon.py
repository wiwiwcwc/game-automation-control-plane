from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

from ..domain.models import Job
from .base import LaunchSpec, ValidationResult


ZZZ_ONEDRAGON_RUNNER_TYPE = "zzz_onedragon"
ZZZ_ONEDRAGON_CONFIG_VERSION = 1
ZZZ_ONEDRAGON_RUNTIME_NAME = "OneDragon-RuntimeLauncher.exe"
ZZZ_ONEDRAGON_CLASSIC_NAME = "OneDragon-Launcher.exe"
ZZZ_ONEDRAGON_EXECUTABLE_NAMES = (
    ZZZ_ONEDRAGON_RUNTIME_NAME,
    ZZZ_ONEDRAGON_CLASSIC_NAME,
)
ZZZ_ONEDRAGON_EXECUTABLE_ENV = "ZZZ_ONEDRAGON_EXECUTABLE"


def parse_instance_indices(value: object) -> tuple[int, ...]:
    """Parse OneDragon's comma-separated, one-based instance argument."""

    if value is None or (isinstance(value, str) and not value.strip()):
        return ()
    if not isinstance(value, str):
        raise ValueError("OneDragon account instances must be entered as 1,2 or left blank.")

    tokens = [token.strip() for token in value.split(",")]
    if not tokens or any(not re.fullmatch(r"[0-9]+", token) for token in tokens):
        raise ValueError(
            "OneDragon account instances must be positive integers separated by commas, such as 1,2."
        )
    indices = tuple(int(token) for token in tokens)
    if any(index <= 0 for index in indices):
        raise ValueError("OneDragon account instances must be positive integers starting at 1.")
    if len(set(indices)) != len(indices):
        raise ValueError("OneDragon account instances must not contain duplicates.")
    return indices


def format_instance_indices(value: object) -> str:
    return ",".join(str(index) for index in parse_instance_indices(value))


def _existing_file(value: str | Path | None) -> Path | None:
    if value is None:
        return None
    try:
        path = Path(value).expanduser()
    except (TypeError, ValueError, OSError):
        return None
    try:
        return path if path.is_file() else None
    except OSError:
        return None


def _candidate_roots() -> tuple[Path, ...]:
    """Return small, user-facing locations; never scan a drive recursively."""

    roots: list[Path] = []
    profile = os.environ.get("USERPROFILE")
    profile_path = Path(profile) if profile else Path.home()
    roots.extend(
        (
            profile_path / "Desktop",
            profile_path / "Downloads",
            profile_path / "OneDrive" / "Desktop",
            profile_path / "OneDrive" / "Downloads",
        )
    )
    public = os.environ.get("PUBLIC")
    if public:
        roots.append(Path(public) / "Desktop")
    app_data = os.environ.get("APPDATA")
    if app_data:
        roots.append(Path(app_data) / "Microsoft" / "Windows" / "Start Menu" / "Programs")
    program_data = os.environ.get("PROGRAMDATA")
    if program_data:
        roots.append(Path(program_data) / "Microsoft" / "Windows" / "Start Menu" / "Programs")
    return tuple(dict.fromkeys(roots))


def _is_launcher(path: Path, name: str) -> bool:
    return path.name.casefold() == name.casefold()


def _root_candidates(root: Path, name: str) -> tuple[Path, ...]:
    """Check a root and its immediate child folders only."""

    candidates: list[Path] = []
    try:
        if not root.is_dir():
            return ()
        for child in root.iterdir():
            if child.is_file() and _is_launcher(child, name):
                candidates.append(child)
            elif child.is_dir():
                nested = child / name
                if nested.is_file() and _is_launcher(nested, name):
                    candidates.append(nested)
            if len(candidates) >= 256:
                break
    except OSError:
        return tuple(candidates)
    return tuple(candidates)


def _discover_named(name: str) -> Path | None:
    for path_value in (shutil.which(name), shutil.which(Path(name).stem)):
        path = _existing_file(path_value)
        if path is not None and _is_launcher(path, name):
            return path

    configured = _existing_file(os.environ.get(ZZZ_ONEDRAGON_EXECUTABLE_ENV))
    if configured is not None and _is_launcher(configured, name):
        return configured

    candidates: list[Path] = []
    for root in _candidate_roots():
        candidates.extend(_root_candidates(root, name))
        if len(candidates) >= 256:
            break
    if not candidates:
        return None
    candidates.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return candidates[0]


def discover_zzz_onedragon() -> str | None:
    """Find an installed ZZZ OneDragon launcher without downloading or scanning broadly."""

    # The RuntimeLauncher package contains its own Python runtime and is the
    # supported first choice. The classic launcher is only the fallback.
    for name in ZZZ_ONEDRAGON_EXECUTABLE_NAMES:
        found = _discover_named(name)
        if found is not None:
            return str(found)
    return None


def find_child_casefold(root: str | Path, name: str, *, directory: bool | None = None) -> Path | None:
    """Find one exact direct child while tolerating Windows name casing."""

    root_path = Path(root)
    try:
        for child in root_path.iterdir():
            if child.name.casefold() != name.casefold():
                continue
            if directory is True and not child.is_dir():
                continue
            if directory is False and not child.is_file():
                continue
            return child
    except OSError:
        return None
    return None


def launcher_kind(executable: str | Path) -> str | None:
    name = Path(executable).name.casefold()
    if name == ZZZ_ONEDRAGON_RUNTIME_NAME.casefold():
        return "runtime"
    if name == ZZZ_ONEDRAGON_CLASSIC_NAME.casefold():
        return "classic"
    return None


class ZzzOneDragonIntegration:
    runner_type = ZZZ_ONEDRAGON_RUNNER_TYPE
    display_name = "绝区零 OneDragon"
    config_version = ZZZ_ONEDRAGON_CONFIG_VERSION

    def validate_config(self, config: dict[str, object]) -> ValidationResult:
        errors: list[str] = []
        executable_value = config.get("executable_path")
        executable: Path | None = None
        if not isinstance(executable_value, str) or not executable_value.strip():
            errors.append("OneDragon launcher path is required.")
        else:
            executable = Path(executable_value.strip()).expanduser()
            if not executable.is_absolute():
                errors.append("OneDragon launcher path must be absolute.")
            elif not executable.exists():
                errors.append(f"OneDragon launcher was not found: {executable}")
            elif not executable.is_file():
                errors.append(f"OneDragon launcher path is not a file: {executable}")
            elif launcher_kind(executable) is None:
                errors.append(
                    "Choose OneDragon-RuntimeLauncher.exe or the official OneDragon-Launcher.exe."
                )
            elif not os.access(executable, os.X_OK) and os.name != "nt":
                errors.append(f"OneDragon launcher is not runnable: {executable}")

        try:
            parse_instance_indices(config.get("instance_indices", ""))
        except ValueError as exc:
            errors.append(str(exc))

        close_game = config.get("close_game_after_run", False)
        if not isinstance(close_game, bool):
            errors.append("Close Zenless Zone Zero after run must be enabled or disabled.")

        version = config.get("config_version", self.config_version)
        if version != self.config_version:
            errors.append(f"Unsupported OneDragon configuration version: {version}")
        return ValidationResult(valid=not errors, errors=tuple(errors))

    def build_launch_spec(self, job: Job) -> LaunchSpec:
        config = job.runner_config
        result = self.validate_config(config)
        if not result.valid:
            raise ValueError(" ".join(result.errors))
        executable = str(config["executable_path"]).strip()
        arguments: list[str] = ["-o"]
        indices = format_instance_indices(config.get("instance_indices", ""))
        if indices:
            arguments.extend(("-i", indices))
        if bool(config.get("close_game_after_run", False)):
            arguments.append("-c")
        argument_tuple = tuple(arguments)
        return LaunchSpec(
            executable=executable,
            arguments=argument_tuple,
            working_directory=str(Path(executable).parent),
            display_command=subprocess.list2cmdline((executable, *argument_tuple)),
            # OneDragon does not expose a trustworthy external worker handoff
            # contract here, so the control plane monitors only this launcher.
        )


# Descriptive alias for callers that do not need to repeat the ZZZ scope. The
# persisted runner type remains explicit so this cannot be mistaken for a
# generic OneDragon adapter.
OneDragonIntegration = ZzzOneDragonIntegration


__all__ = [
    "ZZZ_ONEDRAGON_CLASSIC_NAME",
    "ZZZ_ONEDRAGON_CONFIG_VERSION",
    "ZZZ_ONEDRAGON_EXECUTABLE_ENV",
    "ZZZ_ONEDRAGON_EXECUTABLE_NAMES",
    "ZZZ_ONEDRAGON_RUNTIME_NAME",
    "ZZZ_ONEDRAGON_RUNNER_TYPE",
    "ZzzOneDragonIntegration",
    "OneDragonIntegration",
    "discover_zzz_onedragon",
    "find_child_casefold",
    "format_instance_indices",
    "launcher_kind",
    "parse_instance_indices",
]
