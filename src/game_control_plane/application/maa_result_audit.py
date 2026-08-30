from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from ..domain.models import ErrorKind, Job
from ..integrations.maa_cli import MAA_CLI_RUNNER_TYPE
from ..integrations.maa_managed_task import (
    expected_managed_task_names,
    is_managed_maa_config,
)
from ..integrations.onedragon import ZZZ_ONEDRAGON_RUNNER_TYPE


_SUMMARY_PATTERN = re.compile(
    r"^\[(?P<name>[^\]]+)\]\s+(?P<result>.+)$",
    re.MULTILINE,
)
_FIGHT_COUNT_PATTERN = re.compile(
    r"^Fight\s+.+?\s+(?P<count>\d+)\s+times,\s+drops:\s*$",
    re.MULTILINE,
)


@dataclass(frozen=True)
class RunResultAssessment:
    needs_attention: bool = False
    summary: str = ""
    localization_key: str | None = None
    diagnostic_code: str | None = None
    diagnostic_params: dict[str, object] = field(default_factory=dict)


_EXTERNAL_MAA_UNVERIFIED_SUMMARY = (
    "The external MAA task exited normally, but Hsiesta cannot verify that every "
    "daily step completed. Review the captured log and mark the daily complete "
    "manually only after confirming the task flow. Automatic emulator cleanup was "
    "skipped so you can inspect the run."
)


def assess_run_result(job: Job, stdout_path: str | Path, stderr_path: str | Path) -> RunResultAssessment:
    if job.runner_type == ZZZ_ONEDRAGON_RUNNER_TYPE:
        return assess_onedragon_output(stdout_path, stderr_path)
    if job.runner_type != MAA_CLI_RUNNER_TYPE:
        return RunResultAssessment()
    stdout = _read_text(stdout_path)
    stderr = _read_text(stderr_path)
    if not is_managed_maa_config(job.runner_config):
        return assess_external_maa_output(stdout, stderr)
    return assess_managed_maa_output(job.runner_config, stdout, stderr)


def assess_external_maa_output(
    _stdout: str,
    _stderr: str = "",
) -> RunResultAssessment:
    """Keep arbitrary external MAA task files reviewable after a clean exit.

    Hsiesta cannot infer the intended task sequence or completion evidence from
    a user-maintained maa-cli task file, so an exit code of zero is never
    treated as a verified daily success in external mode.
    """

    return RunResultAssessment(
        needs_attention=True,
        summary=_EXTERNAL_MAA_UNVERIFIED_SUMMARY,
        localization_key="run.maa_external_unverified",
        diagnostic_code=ErrorKind.MAA_EXTERNAL_UNVERIFIED.value,
    )


def assess_onedragon_output(
    stdout_path: str | Path,
    stderr_path: str | Path,
) -> RunResultAssessment:
    """Keep OneDragon exit-0 runs reviewable because no completion protocol exists."""

    stdout = _read_text(stdout_path)
    stderr = _read_text(stderr_path)
    captured = "stdout" if stdout.strip() else "stderr" if stderr.strip() else "no output"
    return RunResultAssessment(
        needs_attention=True,
        summary=(
            "OneDragon exited normally, but Hsiesta cannot verify that "
            f"Zenless Zone Zero daily tasks completed ({captured} captured). "
            "Review the captured OneDragon log and mark the daily complete manually if appropriate. "
            "Hsiesta does not follow or stop an unverified OneDragon worker; inspect manually if any process remains."
        ),
        localization_key="diagnostic.onedragon_unverified",
        diagnostic_code=ErrorKind.ONEDRAGON_UNVERIFIED.value,
        diagnostic_params={"captured": captured},
    )


def assess_managed_maa_output(
    config: dict[str, object],
    stdout: str,
    stderr: str = "",
) -> RunResultAssessment:
    results = {
        match.group("name"): match.group("result").strip()
        for match in _SUMMARY_PATTERN.finditer(stdout)
    }
    missing: list[str] = []
    incomplete: list[str] = []
    for name in expected_managed_task_names(config):
        result = results.get(name)
        if result is None:
            missing.append(name)
        elif not result.endswith("Completed"):
            incomplete.append(f"{name}: {result}")

    options = config.get("managed_daily")
    fight_enabled = isinstance(options, dict) and options.get("fight") is True
    fight_count = sum(int(match.group("count")) for match in _FIGHT_COUNT_PATTERN.finditer(stdout))
    reasons: list[str] = []
    diagnostic_params: dict[str, object] = {
        "missing": tuple(missing),
        "incomplete": tuple(incomplete),
        "zero_battles": bool(fight_enabled and fight_count == 0),
        "task_chain_error": "TaskChainError" in stdout or "TaskChainError" in stderr,
    }
    if missing:
        reasons.append("missing summary for " + ", ".join(missing))
    if incomplete:
        reasons.append("unfinished task: " + "; ".join(incomplete))
    if fight_enabled and fight_count == 0:
        reasons.append("the configured sanity fight completed zero battles")
    if "TaskChainError" in stdout or "TaskChainError" in stderr:
        reasons.append("MAA reported an internal task-chain error")
    if not reasons:
        return RunResultAssessment()
    return RunResultAssessment(
        needs_attention=True,
        summary="MAA needs attention: " + "; ".join(reasons) + ". The emulator was left open.",
        diagnostic_code=ErrorKind.MAA_MANAGED_INCOMPLETE.value,
        diagnostic_params=diagnostic_params,
    )


def _read_text(path: str | Path) -> str:
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


__all__ = [
    "RunResultAssessment",
    "assess_external_maa_output",
    "assess_managed_maa_output",
    "assess_onedragon_output",
    "assess_run_result",
]
