from __future__ import annotations

from pathlib import Path
import tomllib

from game_control_plane import __version__


def test_package_version_matches_project_metadata() -> None:
    project_root = Path(__file__).resolve().parents[2]
    metadata = tomllib.loads((project_root / "pyproject.toml").read_text(encoding="utf-8"))

    assert __version__ == "0.1.21"
    assert __version__ == metadata["project"]["version"]
