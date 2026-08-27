from __future__ import annotations

from game_control_plane.app import app_icon_path


def test_app_icon_is_available_in_source_tree():
    icon = app_icon_path()

    assert icon.name == "app_icon.png"
    assert icon.is_file()
    assert icon.stat().st_size > 0
