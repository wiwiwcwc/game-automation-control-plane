import sys
import json

from PySide6.QtWidgets import QApplication

from game_control_plane.ui import job_editor
from game_control_plane.ui.job_editor import JobEditorDialog
from game_control_plane.ui.i18n import LanguageManager


_APP: QApplication | None = None


def app_instance() -> QApplication:
    global _APP
    _APP = QApplication.instance() or QApplication([])
    return _APP


def test_maa_onboarding_labels_arknights_and_builds_versioned_payload(monkeypatch):
    app_instance()
    monkeypatch.setattr(job_editor, "discover_maa_cli", lambda: sys.executable)
    dialog = JobEditorDialog(i18n=LanguageManager("en_US", persist=False))
    dialog.show()
    dialog.integration_combo.setCurrentIndex(dialog.integration_combo.findData("maa_cli"))
    app_instance().processEvents()

    assert dialog.integration_combo.currentText() == "MAA"
    assert dialog.game_name.text() == "Arknights"
    assert dialog.game_name.isReadOnly()
    assert dialog.executable_path.text() == sys.executable
    assert not dialog.task_name.isVisible()
    assert dialog.maa_daily_group.isVisible()
    assert not dialog.arguments.isVisible()
    assert not dialog.working_container.isVisible()

    dialog.job_name.setText("Daily")
    dialog.maa_series.setCurrentIndex(dialog.maa_series.findData(6))
    payload, errors = dialog._payload()

    assert not errors
    assert payload["game_name"] == "Arknights"
    assert payload["runner_type"] == "maa_cli"
    assert payload["runner_config_version"] == 1
    config = payload["runner_config"]
    assert config["config_version"] == 1
    assert config["executable_path"] == sys.executable
    assert config["task_mode"] == "managed"
    assert str(config["task_name"]).startswith("control_plane_")
    assert config["managed_daily"]["series"] == 6
    assert config["managed_daily"]["mall"] is True
    assert config["managed_daily"]["fight"] is True
    dialog.close()


def test_maa_auto_start_fields_are_optional_and_round_trip(monkeypatch):
    app_instance()
    monkeypatch.setattr(job_editor, "discover_maa_cli", lambda: sys.executable)
    monkeypatch.setattr(job_editor, "discover_mumu_cli", lambda: sys.executable)
    dialog = JobEditorDialog(i18n=LanguageManager("en_US", persist=False))
    dialog.integration_combo.setCurrentIndex(dialog.integration_combo.findData("maa_cli"))
    dialog.maa_task_mode.setCurrentIndex(dialog.maa_task_mode.findData("external"))

    assert not dialog.auto_start_emulator.isChecked()
    assert dialog.emulator_container.isHidden()
    dialog.auto_start_emulator.setChecked(True)
    dialog.job_name.setText("Daily")
    dialog.task_name.setText("daily")
    dialog.emulator_instance_index.setValue(1)
    dialog.emulator_start_timeout.setValue(120)
    payload, errors = dialog._payload()

    assert errors == []
    assert not dialog.emulator_container.isHidden()
    assert payload["runner_config"] == {
        "config_version": 1,
        "executable_path": sys.executable,
        "task_mode": "external",
        "task_name": "daily",
        "auto_start_emulator": True,
        "emulator_type": "mumu",
        "emulator_executable_path": sys.executable,
        "emulator_instance_index": 1,
            "emulator_start_timeout_seconds": 120,
            "close_emulator_after_run": True,
    }
    dialog.close()


def test_custom_cli_remains_the_default_editor_choice():
    app_instance()
    dialog = JobEditorDialog(i18n=LanguageManager("en_US", persist=False))
    dialog.show()
    assert dialog.integration_combo.currentData() == "custom_cli"
    assert not dialog.game_name.isReadOnly()
    assert dialog.arguments.isVisible()
    assert not dialog.task_name.isVisible()
    dialog.close()


def test_ok_ww_onboarding_labels_wuthering_waves_and_builds_payload(monkeypatch):
    app_instance()
    monkeypatch.setattr(job_editor, "discover_ok_ww", lambda: sys.executable)
    dialog = JobEditorDialog(i18n=LanguageManager("en_US", persist=False))
    dialog.show()
    dialog.integration_combo.setCurrentIndex(dialog.integration_combo.findData("ok_ww"))
    assert dialog.integration_combo.currentText() == "OK-WW"
    assert dialog.game_name.text() == "Wuthering Waves"
    assert dialog.game_name.isReadOnly()
    assert dialog.executable_path.text() == sys.executable
    assert dialog.task_index.isVisible()
    assert dialog.arguments.isHidden()
    assert dialog.working_container.isHidden()

    dialog.job_name.setText("Wuthering daily")
    dialog.task_index.setValue(2)
    payload, errors = dialog._payload()
    assert errors == []
    assert payload["game_name"] == "Wuthering Waves"
    assert payload["runner_type"] == "ok_ww"
    assert payload["runner_config_version"] == 1
    assert payload["runner_config"] == {
        "config_version": 1,
        "executable_path": sys.executable,
        "task_index": 2,
        "close_game_after_run": True,
    }
    dialog.close()


def test_fos_onboarding_discovers_saved_configuration_and_builds_payload(monkeypatch, tmp_path):
    app_instance()
    fos = tmp_path / "MPA" / "FOS.exe"
    fos.parent.mkdir()
    fos.touch()
    config_dir = fos.parent / "config" / "configs"
    config_dir.mkdir(parents=True)
    (config_dir / "c_daily.json").write_text(
        json.dumps(
            {
                "name": "每日任务",
                "item_id": "c_daily",
                "tasks": [
                    {
                        "item_id": "Controller",
                        "task_option": {
                            "controller_type": "Android",
                            "Android": {
                                "config": {
                                    "extras": {
                                        "mumu": {"index": 0, "path": str(tmp_path)}
                                    }
                                }
                            },
                        },
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(job_editor, "discover_fos", lambda: str(fos))
    monkeypatch.setattr(job_editor, "discover_fos_mumu_cli", lambda _controller: None)
    dialog = JobEditorDialog(i18n=LanguageManager("zh_CN", persist=False))
    dialog.show()
    dialog.integration_combo.setCurrentIndex(dialog.integration_combo.findData("maa_punish"))
    app_instance().processEvents()

    assert dialog.game_name.text() == "战双帕弥什"
    assert dialog.game_name.isReadOnly()
    assert dialog.executable_path.text() == str(fos)
    assert dialog.fos_config_combo.currentText() == "每日任务"
    assert dialog.arguments.isHidden()
    dialog.job_name.setText("每日")
    payload, errors = dialog._payload()
    assert errors == []
    assert payload["runner_type"] == "maa_punish"
    assert payload["runner_config"] == {
        "config_version": 1,
        "executable_path": str(fos),
        "config_id": "c_daily",
        "close_fos_after_run": True,
    }
    dialog.close()
