from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

APP_NAME = "GameAutomationControlPlane"
DATA_DIR_ENV = "GAME_CONTROL_PLANE_DATA_DIR"


@dataclass(frozen=True)
class AppPaths:
    data_dir: Path
    database_path: Path
    logs_dir: Path
    runs_dir: Path
    app_log_path: Path

    def ensure(self) -> "AppPaths":
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        return self


def default_data_dir() -> Path:
    override = os.environ.get(DATA_DIR_ENV)
    if override:
        return Path(override).expanduser()
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    if base:
        return Path(base) / APP_NAME
    return Path.home() / ".local" / "share" / APP_NAME


def app_paths(data_dir: str | Path | None = None) -> AppPaths:
    root = Path(data_dir).expanduser() if data_dir is not None else default_data_dir()
    return AppPaths(
        data_dir=root,
        database_path=root / "control_plane.sqlite3",
        logs_dir=root / "logs",
        runs_dir=root / "runs",
        app_log_path=root / "logs" / "app.log",
    )
