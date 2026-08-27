from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from ..domain.models import Job
from .base import LaunchSpec, ValidationResult


OK_WW_RUNNER_TYPE = "ok_ww"
OK_WW_CONFIG_VERSION = 1
OK_WW_HANDOFF_PROCESS_NAMES = ("pythonw.exe", "python.exe")
OK_WW_EXECUTABLE_ENV = "OK_WW_EXECUTABLE"
OK_WW_EXECUTABLE_NAMES = ("ok-ww.exe", "ok-ww")
_SHORTCUT_NAME_MARKERS = ("ok-ww", "ok_ww", "wuthering", "鸣潮")


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


def _shortcut_roots() -> tuple[Path, ...]:
    roots: list[Path] = []
    profile = os.environ.get("USERPROFILE")
    if profile:
        profile_path = Path(profile)
    else:
        profile_path = Path.home()
    roots.append(profile_path / "Desktop")

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


def _read_c_string(data: bytes, start: int, end: int) -> str | None:
    if start < 0 or start >= end or end > len(data):
        return None
    stop = data.find(b"\x00", start, end)
    if stop < 0:
        stop = end
    if stop <= start:
        return None
    try:
        return data[start:stop].decode("mbcs" if os.name == "nt" else "utf-8", errors="replace")
    except LookupError:
        return data[start:stop].decode(errors="replace")


def _read_utf16_string(data: bytes, start: int, end: int) -> str | None:
    if start < 0 or start + 1 >= end or end > len(data):
        return None
    stop = start
    while stop + 1 < end:
        if data[stop] == 0 and data[stop + 1] == 0:
            break
        stop += 2
    if stop <= start:
        return None
    return data[start:stop].decode("utf-16-le", errors="replace")


def _read_shortcut_target(shortcut: Path) -> str | None:
    """Read an absolute target from a Windows Shell Link without COM/UI calls."""

    try:
        data = shortcut.read_bytes()
    except OSError:
        return None
    if len(data) < 76 or data[:4] != b"\x4c\x00\x00\x00":
        return None

    link_flags = int.from_bytes(data[0x14:0x18], "little")
    offset = 76
    if link_flags & 0x01:  # HasLinkTargetIDList
        if offset + 2 > len(data):
            return None
        offset += 2 + int.from_bytes(data[offset : offset + 2], "little")
    if not link_flags & 0x02 or offset + 0x24 > len(data):  # HasLinkInfo
        return None

    link_info_size = int.from_bytes(data[offset : offset + 4], "little")
    link_info_header_size = int.from_bytes(data[offset + 4 : offset + 8], "little")
    if (
        link_info_header_size < 0x1C
        or link_info_size < link_info_header_size
        or offset + link_info_size > len(data)
    ):
        return None
    link_info_end = offset + link_info_size

    local_path_offset = int.from_bytes(data[offset + 0x10 : offset + 0x14], "little")
    if link_info_header_size >= 0x24:
        unicode_offset = int.from_bytes(data[offset + 0x1C : offset + 0x20], "little")
        if unicode_offset:
            target = _read_utf16_string(data, offset + unicode_offset, link_info_end)
            if target:
                return target
    if local_path_offset:
        return _read_c_string(data, offset + local_path_offset, link_info_end)
    return None


def _shortcut_candidates() -> tuple[Path, ...]:
    candidates: list[Path] = []
    for root in _shortcut_roots():
        try:
            if not root.is_dir():
                continue
            shortcuts = root.rglob("*.lnk")
            for shortcut in shortcuts:
                name = shortcut.stem.casefold()
                if not any(marker in name for marker in _SHORTCUT_NAME_MARKERS):
                    continue
                candidates.append(shortcut)
                if len(candidates) >= 256:
                    return tuple(candidates)
        except OSError:
            continue
    return tuple(candidates)


def discover_ok_ww() -> str | None:
    """Find an existing OK-WW executable without changing external state."""

    for name in OK_WW_EXECUTABLE_NAMES:
        found = _existing_file(shutil.which(name))
        if found:
            return str(found)

    configured = _existing_file(os.environ.get(OK_WW_EXECUTABLE_ENV))
    if configured:
        return str(configured)

    for shortcut in _shortcut_candidates():
        target = _existing_file(_read_shortcut_target(shortcut))
        if target and target.name.casefold() in {"ok-ww.exe", "ok_ww.exe"}:
            return str(target)
    return None


class OkWwIntegration:
    runner_type = OK_WW_RUNNER_TYPE
    display_name = "OK-WW"
    config_version = OK_WW_CONFIG_VERSION

    def validate_config(self, config: dict[str, object]) -> ValidationResult:
        errors: list[str] = []
        executable_value = config.get("executable_path")
        if not isinstance(executable_value, str) or not executable_value.strip():
            errors.append("OK-WW executable path is required.")
        else:
            executable = Path(executable_value.strip()).expanduser()
            if not executable.is_absolute():
                errors.append("OK-WW executable path must be absolute.")
            elif not executable.exists():
                errors.append(f"OK-WW executable was not found: {executable}")
            elif not executable.is_file():
                errors.append(f"OK-WW executable path is not a file: {executable}")
            elif not os.access(executable, os.X_OK) and os.name != "nt":
                errors.append(f"OK-WW executable is not runnable: {executable}")

        task_value = config.get("task_index")
        if isinstance(task_value, bool) or not isinstance(task_value, int) or task_value <= 0:
            errors.append("OK-WW task index must be a positive integer.")

        close_after = config.get("close_game_after_run", True)
        if not isinstance(close_after, bool):
            errors.append("Close Wuthering Waves after run must be enabled or disabled.")

        version = config.get("config_version", self.config_version)
        if version != self.config_version:
            errors.append(f"Unsupported OK-WW configuration version: {version}")
        return ValidationResult(valid=not errors, errors=tuple(errors))

    def build_launch_spec(self, job: Job) -> LaunchSpec:
        config = job.runner_config
        result = self.validate_config(config)
        if not result.valid:
            raise ValueError(" ".join(result.errors))
        executable = str(config["executable_path"]).strip()
        task_index = int(config["task_index"])
        arguments = ("-t", str(task_index))
        if bool(config.get("close_game_after_run", True)):
            arguments += ("-e",)
        display_command = subprocess.list2cmdline((executable, *arguments))
        return LaunchSpec(
            executable=executable,
            arguments=arguments,
            working_directory=str(Path(executable).parent),
            display_command=display_command,
            handoff_process_names=OK_WW_HANDOFF_PROCESS_NAMES,
        )


__all__ = [
    "OK_WW_CONFIG_VERSION",
    "OK_WW_EXECUTABLE_ENV",
    "OK_WW_EXECUTABLE_NAMES",
    "OK_WW_HANDOFF_PROCESS_NAMES",
    "OK_WW_RUNNER_TYPE",
    "OkWwIntegration",
    "discover_ok_ww",
]
