from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..domain.models import Run, RunState
from ..persistence.store import Store


@dataclass(frozen=True)
class RetentionResult:
    removed_run_ids: tuple[str, ...] = ()
    skipped_paths: tuple[Path, ...] = ()


def prune_run_logs(
    runs_dir: str | Path,
    store: Store,
    *,
    now: datetime | None = None,
    retention_days: int = 30,
    logger: logging.Logger | None = None,
) -> RetentionResult:
    """Remove old captured logs while retaining all SQLite run metadata.

    Only a direct, existing, non-symlink child directory of ``runs_dir`` can
    be considered. Paths stored in SQLite are treated as untrusted metadata;
    a path outside that root, nested below a child, or pointing through a
    symlink is skipped rather than followed.
    """

    if retention_days < 0:
        raise ValueError("retention_days must be non-negative")
    log = logger or logging.getLogger("game_control_plane.retention")
    root = Path(runs_dir).expanduser().resolve(strict=False)
    if not root.exists() or not root.is_dir():
        return RetentionResult()
    current = _aware_utc(now or datetime.now(timezone.utc))
    cutoff = current - timedelta(days=retention_days)
    runs = store.list_all_runs()
    protected_dirs = _latest_failed_dirs(runs, root)
    candidates: dict[Path, list[Run]] = {}
    skipped: list[Path] = []
    for run in runs:
        run_dir = _validated_run_dir(run, root)
        if run_dir is None:
            for path in (run.stdout_path, run.stderr_path):
                if path:
                    skipped.append(Path(path))
            continue
        candidates.setdefault(run_dir, []).append(run)

    removed_ids: list[str] = []
    for run_dir, directory_runs in candidates.items():
        if run_dir in protected_dirs:
            continue
        if any(_run_time(run) >= cutoff for run in directory_runs):
            continue
        try:
            shutil.rmtree(run_dir)
        except OSError as exc:
            log.warning("Could not prune captured run logs %s: %s", run_dir, exc)
            skipped.append(run_dir)
            continue
        removed_ids.extend(run.id for run in directory_runs)
        log.info("Pruned captured run logs %s", run_dir)
    return RetentionResult(tuple(removed_ids), tuple(skipped))


def _latest_failed_dirs(runs: list[Run], root: Path) -> set[Path]:
    latest_by_job: dict[int, Run] = {}
    for run in runs:
        if run.state not in {RunState.FAILED, RunState.NEEDS_ATTENTION}:
            continue
        previous = latest_by_job.get(run.job_id)
        if previous is None or _run_time(run) > _run_time(previous):
            latest_by_job[run.job_id] = run
    protected: set[Path] = set()
    for run in latest_by_job.values():
        run_dir = _validated_run_dir(run, root)
        if run_dir is not None:
            protected.add(run_dir)
    return protected


def _validated_run_dir(run: Run, root: Path) -> Path | None:
    paths = [Path(path) for path in (run.stdout_path, run.stderr_path) if path]
    if not paths:
        return None
    candidates: list[Path] = []
    for path in paths:
        try:
            if not path.is_absolute() or path.is_symlink():
                return None
            candidate = path.parent
            if candidate.is_symlink():
                return None
            relative = candidate.relative_to(root)
            if len(relative.parts) != 1 or relative.parts[0] != run.id:
                return None
            resolved = candidate.resolve(strict=False)
            if resolved != candidate or not resolved.is_dir() or resolved.is_symlink():
                return None
            candidates.append(resolved)
        except (OSError, RuntimeError, ValueError):
            return None
    if len(set(candidates)) != 1:
        return None
    return candidates[0]


def _run_time(run: Run) -> datetime:
    for value in (run.finished_at_utc, run.started_at_utc, run.created_at_utc):
        if value:
            try:
                return _aware_utc(datetime.fromisoformat(value))
            except ValueError:
                continue
    return datetime.min.replace(tzinfo=timezone.utc)


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


__all__ = ["RetentionResult", "prune_run_logs"]
