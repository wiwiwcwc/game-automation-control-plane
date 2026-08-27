from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from ..domain.models import Job
from ..integrations.maa_cli import MAA_CLI_RUNNER_TYPE
from ..integrations.maa_managed_task import (
    expected_managed_task_names,
    is_managed_maa_config,
)


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


def assess_run_result(job: Job, stdout_path: str | Path, stderr_path: str | Path) -> RunResultAssessment:
    if job.runner_type != MAA_CLI_RUNNER_TYPE or not is_managed_maa_config(job.runner_config):
        return RunResultAssessment()
    stdout = _read_text(stdout_path)
    stderr = _read_text(stderr_path)
    return assess_managed_maa_output(job.runner_config, stdout, stderr)


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
    )


def _read_text(path: str | Path) -> str:
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


__all__ = ["RunResultAssessment", "assess_managed_maa_output", "assess_run_result"]
