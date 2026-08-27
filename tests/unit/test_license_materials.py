from __future__ import annotations

from pathlib import Path
import tomllib


def test_project_license_is_agpl_3_only() -> None:
    project_root = Path(__file__).resolve().parents[2]
    license_text = (project_root / "LICENSE").read_text(encoding="utf-8")
    metadata = tomllib.loads((project_root / "pyproject.toml").read_text(encoding="utf-8"))

    assert "GNU AFFERO GENERAL PUBLIC LICENSE" in license_text
    assert "Version 3, 19 November 2007" in license_text
    assert metadata["project"]["license"] == "AGPL-3.0-only"


def test_qt_license_materials_are_present() -> None:
    project_root = Path(__file__).resolve().parents[2]
    notice = (project_root / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    lgpl = (project_root / "licenses" / "LGPL-3.0-only.txt").read_text(encoding="utf-8")
    gpl = (project_root / "licenses" / "GPL-3.0-only.txt").read_text(encoding="utf-8")

    assert "PySide6 6.11.2" in notice
    assert "GNU LESSER GENERAL PUBLIC LICENSE" in lgpl
    assert "GNU GENERAL PUBLIC LICENSE" in gpl
