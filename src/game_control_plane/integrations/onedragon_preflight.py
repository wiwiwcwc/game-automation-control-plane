from __future__ import annotations

from pathlib import Path
from typing import Callable

from .maa_preflight import CheckState, CheckStep, MaaPreflightReport
from .onedragon import (
    ZZZ_ONEDRAGON_CLASSIC_NAME,
    ZZZ_ONEDRAGON_RUNTIME_NAME,
    find_child_casefold,
    format_instance_indices,
    launcher_kind,
    parse_instance_indices,
    ZzzOneDragonIntegration,
)


_ONEDRAGON_STEPS = (
    ("executable", "OneDragon launcher"),
    ("layout", "Installation layout"),
    ("accounts", "Account instances"),
    ("launch", "Launch contract"),
)


def run_onedragon_preflight(
    config: dict[str, object],
    progress: Callable[[str], None] | None = None,
) -> MaaPreflightReport:
    """Validate the installed ZZZ OneDragon launcher without starting it."""

    steps: list[CheckStep] = []
    executable_value = config.get("executable_path")
    executable = str(executable_value).strip() if isinstance(executable_value, str) else ""
    path = Path(executable).expanduser() if executable else None
    kind = launcher_kind(path) if path is not None else None

    _notify(progress, "Checking the OneDragon launcher…")
    validation = ZzzOneDragonIntegration().validate_config(config)
    if not validation.valid:
        if path is None or not path.is_absolute() or not path.is_file() or kind is None:
            failed_key = "executable"
        elif any(issue.code == "onedragon.accounts.invalid" for issue in validation.issues):
            failed_key = "accounts"
        else:
            failed_key = "launch"
        issue_code = next(
            (
                issue.code
                for issue in validation.issues
                if issue.code.startswith("onedragon.")
            ),
            f"onedragon.{failed_key}.invalid",
        )
        return _failed(
            steps,
            failed_key,
            "OneDragon configuration is invalid: " + " ".join(validation.errors),
            (
                "Open Edit and choose the installed OneDragon-RuntimeLauncher.exe, or the official OneDragon-Launcher.exe."
                if failed_key == "executable"
                else "Open Edit and correct the account indices/close option, then check again."
            ),
            executable,
            diagnostic_code=issue_code,
        )
    launcher_name = (
        ZZZ_ONEDRAGON_RUNTIME_NAME if kind == "runtime" else ZZZ_ONEDRAGON_CLASSIC_NAME
    )
    steps.append(
        CheckStep(
            "executable",
            "OneDragon launcher",
            CheckState.PASSED,
            f"Found {path.name} ({launcher_name}).",
            details=str(path),
        )
    )

    _notify(progress, "Checking the OneDragon installation layout…")
    layout_step = _layout_step(path, kind)
    steps.append(layout_step)
    if layout_step.state == CheckState.FAILED:
        return _pending_report(steps)

    _notify(progress, "Checking OneDragon account instances…")
    try:
        indices = parse_instance_indices(config.get("instance_indices", ""))
    except ValueError as exc:
        return _failed(
            steps,
            "accounts",
            str(exc),
            "Open Edit and leave the account field blank for active_in_od, or enter positive indices such as 1,2.",
            str(config.get("instance_indices", "")),
            diagnostic_code="onedragon.accounts.invalid",
        )
    account_summary = (
        "OneDragon will use the active_in_od account."
        if not indices
        else f"OneDragon will use account instances {format_instance_indices(config.get('instance_indices', ''))}."
    )
    steps.append(
        CheckStep(
            "accounts",
            "Account instances",
            CheckState.PASSED,
            account_summary,
            details="The account value is passed through unchanged; Hsiesta does not edit OneDragon account configuration.",
        )
    )

    _notify(progress, "Preparing the OneDragon launch contract…")
    arguments = ["-o"]
    normalized = format_instance_indices(config.get("instance_indices", ""))
    if normalized:
        arguments.extend(("-i", normalized))
    if bool(config.get("close_game_after_run", False)):
        arguments.append("-c")
    steps.append(
        CheckStep(
            "launch",
            "Launch contract",
            CheckState.PASSED,
            "OneDragon will be launched with the explicit arguments " + " ".join(arguments) + ".",
            details=(
                f"Working directory: {path.parent}\n"
                f"Command arguments: {' '.join(arguments)}\n"
                "No shell command, external game stop, or OneDragon configuration write is used."
            ),
        )
    )
    return MaaPreflightReport(tuple(steps), kind="onedragon")


def _layout_step(path: Path, kind: str) -> CheckStep:
    if kind == "runtime":
        runtime = find_child_casefold(path.parent, ".runtime", directory=True)
        source = find_child_casefold(path.parent, "src", directory=True)
        missing = [name for name, found in ((".runtime", runtime), ("src", source)) if found is None]
        if missing:
            return CheckStep(
                "layout",
                "Installation layout",
                CheckState.FAILED,
                "The RuntimeLauncher package is incomplete; missing " + ", ".join(missing) + ".",
                "Choose the complete OneDragon WithRuntime folder containing the launcher, .runtime, and src side by side. Do not select an EXE copied by itself.",
                details=f"Launcher folder: {path.parent}",
            )
        return CheckStep(
            "layout",
            "Installation layout",
            CheckState.PASSED,
            "RuntimeLauncher has the adjacent .runtime and src directories.",
            details=f"Runtime: {runtime}\nSource injection directory: {source}",
        )

    direct_config = find_child_casefold(path.parent, "config", directory=True)
    resources = find_child_casefold(path.parent, "resources", directory=True)
    resources_config = (
        find_child_casefold(resources, "config", directory=True)
        if resources
        else None
    )
    candidates = (("config", direct_config), ("resources/config", resources_config))
    checked_layouts: list[str] = []
    for label, config_root in candidates:
        project = (
            find_child_casefold(config_root, "project.yml", directory=False)
            if config_root
            else None
        )
        repository = (
            find_child_casefold(config_root, "repository.yml", directory=False)
            if config_root
            else None
        )
        if project is not None and repository is not None:
            if label == "config":
                summary = (
                    "The classic Full-Environment directory has "
                    "config/project.yml and config/repository.yml."
                )
            else:
                summary = (
                    "The classic launcher has a complete "
                    "resources/config compatibility layout."
                )
            return CheckStep(
                "layout",
                "Installation layout",
                CheckState.PASSED,
                summary,
                details=(
                    f"Config layout: {label}\n"
                    f"Project config: {project}\n"
                    f"Repository config: {repository}"
                ),
            )
        missing = [
            f"{label}/{name}"
            for name, found in (
                ("project.yml", project),
                ("repository.yml", repository),
            )
            if found is None
        ]
        checked_layouts.append(
            f"{label}: "
            + ("config directory missing" if config_root is None else "missing " + ", ".join(missing))
        )

    return CheckStep(
        "layout",
        "Installation layout",
        CheckState.FAILED,
        (
            "The classic OneDragon launcher needs one complete config pair: "
            "config/project.yml + config/repository.yml (Full-Environment), "
            "or resources/config/project.yml + resources/config/repository.yml "
            "(compatibility layout)."
        ),
        (
            "Choose the complete official OneDragon directory containing "
            "OneDragon-Launcher.exe and either config/*.yml (Full-Environment) "
            "or resources/config/*.yml. Do not move YAML files."
        ),
        details=(
            f"Launcher folder: {path.parent}\n"
            "Checked layout candidates:\n"
            + "\n".join(checked_layouts)
        ),
    )


def _failed(
    steps: list[CheckStep],
    key: str,
    summary: str,
    next_action: str,
    details: str = "",
    *,
    diagnostic_code: str | None = None,
) -> MaaPreflightReport:
    title = dict(_ONEDRAGON_STEPS)[key]
    steps.append(
        CheckStep(
            key,
            title,
            CheckState.FAILED,
            summary,
            next_action,
            details,
            diagnostic_code=diagnostic_code,
        )
    )
    return _pending_report(steps)


def _pending_report(steps: list[CheckStep]) -> MaaPreflightReport:
    existing = {step.key for step in steps}
    steps.extend(
        CheckStep(key, title, CheckState.PENDING, "Not checked yet.")
        for key, title in _ONEDRAGON_STEPS
        if key not in existing
    )
    order = {key: index for index, (key, _) in enumerate(_ONEDRAGON_STEPS)}
    steps.sort(key=lambda step: order[step.key])
    return MaaPreflightReport(tuple(steps), kind="onedragon")


def _notify(progress: Callable[[str], None] | None, message: str) -> None:
    if progress:
        progress(message)


__all__ = ["run_onedragon_preflight"]
