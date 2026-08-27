from pathlib import Path

from game_control_plane.platform.paths import app_paths


def test_app_paths_support_explicit_override(tmp_path: Path):
    paths = app_paths(tmp_path / "data")
    paths.ensure()
    assert paths.database_path.parent == tmp_path / "data"
    assert paths.logs_dir.is_dir()
    assert paths.runs_dir.is_dir()
