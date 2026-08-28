from pathlib import Path

from game_control_plane.platform.paths import app_paths


def test_app_paths_support_explicit_override(tmp_path: Path):
    paths = app_paths(tmp_path / "data")
    paths.ensure()
    assert paths.database_path.parent == tmp_path / "data"
    assert paths.logs_dir.is_dir()
    assert paths.runs_dir.is_dir()


def test_default_data_dir_keeps_legacy_application_name(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("GAME_CONTROL_PLANE_DATA_DIR", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.delenv("APPDATA", raising=False)

    assert app_paths().data_dir == tmp_path / "GameAutomationControlPlane"
