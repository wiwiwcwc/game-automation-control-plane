from __future__ import annotations

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from game_control_plane.domain.models import DailyStatus, RunState
from game_control_plane.ui.dashboard import Dashboard
from game_control_plane.ui.i18n import (
    _EN_US,
    _ZH_CN,
    LanguageManager,
    onedragon_preflight_message_text,
    preflight_progress_text,
    state_text,
)
from game_control_plane.ui.job_editor import JobEditorDialog
from game_control_plane.ui import job_editor
from game_control_plane.platform.paths import app_paths
from game_control_plane.ui.main_window import MainWindow


_APP: QApplication | None = None


def app_instance() -> QApplication:
    global _APP
    _APP = QApplication.instance() or QApplication([])
    return _APP


def test_default_language_is_chinese_and_language_choice_persists(tmp_path):
    settings_path = tmp_path / "language.ini"
    settings = QSettings(str(settings_path), QSettings.Format.IniFormat)
    manager = LanguageManager(settings=settings)

    assert manager.language == "zh_CN"
    assert manager.text("button.run") == "运行"

    manager.set_language("en_US")
    restored = LanguageManager(
        settings=QSettings(str(settings_path), QSettings.Format.IniFormat)
    )
    assert restored.language == "en_US"
    assert restored.text("button.run") == "Run"


def test_translation_catalogs_have_exact_key_parity():
    assert set(_ZH_CN) == set(_EN_US)


def test_external_maa_review_prompt_is_localized():
    zh = LanguageManager("zh_CN", persist=False)
    en = LanguageManager("en_US", persist=False)

    assert "外部 MAA 任务已正常退出" in zh.text("run.maa_external_unverified")
    assert "cannot confirm that every daily step completed" in en.text(
        "run.maa_external_unverified"
    )


def test_all_states_and_daily_statuses_have_chinese_display_text():
    manager = LanguageManager("zh_CN", persist=False)
    assert all(state_text(manager, state.value) != f"state.{state.value}" for state in RunState)
    assert {status.value for status in DailyStatus} == {"pending", "completed"}
    assert manager.text("card.pending") == "待完成"
    assert manager.text("card.completed") == "已完成"


def test_dashboard_retranslates_live_without_restarting():
    app_instance()
    manager = LanguageManager("zh_CN", persist=False)
    dashboard = Dashboard(manager)
    assert dashboard.run_dailies_button.text() == "运行今日任务"

    manager.set_language("en_US")

    assert dashboard.run_dailies_button.text() == "Run Today's Dailies"
    assert dashboard.title_label.text() == "Hsiesta"


def test_new_integration_jobs_use_chinese_game_names_by_default(monkeypatch):
    app_instance()
    monkeypatch.setattr(job_editor, "discover_maa_cli", lambda: None)
    monkeypatch.setattr(job_editor, "discover_mumu_cli", lambda: None)
    monkeypatch.setattr(job_editor, "discover_ok_ww", lambda: None)
    monkeypatch.setattr(job_editor, "discover_fos", lambda: None)
    monkeypatch.setattr(job_editor, "discover_zzz_onedragon", lambda: None)
    manager = LanguageManager("zh_CN", persist=False)
    dialog = JobEditorDialog(i18n=manager)
    dialog.integration_combo.setCurrentIndex(dialog.integration_combo.findData("maa_cli"))
    assert dialog.game_name.text() == "明日方舟"
    dialog.integration_combo.setCurrentIndex(dialog.integration_combo.findData("ok_ww"))
    assert dialog.game_name.text() == "鸣潮"
    dialog.integration_combo.setCurrentIndex(dialog.integration_combo.findData("maa_punish"))
    assert dialog.game_name.text() == "战双帕弥什"
    dialog.integration_combo.setCurrentIndex(dialog.integration_combo.findData("zzz_onedragon"))
    assert dialog.game_name.text() == "绝区零"
    assert dialog.onedragon_close_game.text() == "完成后由 OneDragon 关闭绝区零"
    dialog.close()


def test_main_window_language_menu_switches_interface_immediately(tmp_path):
    app_instance()
    manager = LanguageManager("zh_CN", persist=False)
    window = MainWindow(app_paths(tmp_path / "app"), i18n=manager)
    assert window.windowTitle() == "休汐 Hsiesta"
    assert window.settings_menu.title() == "设置"

    window.language_actions["en_US"].trigger()

    assert manager.language == "en_US"
    assert window.windowTitle() == "Hsiesta"
    assert window.settings_menu.title() == "Settings"
    window.database.close()


def test_mumu_progress_is_localized_without_changing_unknown_technical_text():
    manager = LanguageManager("zh_CN", persist=False)
    assert preflight_progress_text(
        manager,
        "Waiting for MuMu instance 1 to connect to ADB… 8/120 seconds",
    ) == "正在等待 MuMu 实例 1 连接 ADB… 8/120 秒"
    assert preflight_progress_text(manager, "raw third-party message") == "raw third-party message"


def test_onedragon_progress_and_game_text_are_localized():
    from game_control_plane.ui.i18n import (
        game_text,
        onedragon_preflight_progress_text,
    )

    manager = LanguageManager("en_US", persist=False)
    assert game_text(manager, "ignored", "zzz_onedragon") == "Zenless Zone Zero"
    assert onedragon_preflight_progress_text(
        manager, "Preparing the OneDragon launch contract…"
    ) == "Preparing the OneDragon launch contract…"


def test_onedragon_layout_messages_are_localized():
    missing = (
        "The classic OneDragon launcher needs one complete config pair: "
        "config/project.yml + config/repository.yml (Full-Environment), or "
        "resources/config/project.yml + resources/config/repository.yml "
        "(compatibility layout)."
    )
    next_action = (
        "Choose the complete official OneDragon directory containing "
        "OneDragon-Launcher.exe and either config/*.yml (Full-Environment) "
        "or resources/config/*.yml. Do not move YAML files."
    )

    zh = LanguageManager("zh_CN", persist=False)
    en = LanguageManager("en_US", persist=False)
    assert onedragon_preflight_message_text(zh, missing).startswith("经典 OneDragon")
    assert "请选择" in onedragon_preflight_message_text(zh, next_action)
    assert onedragon_preflight_message_text(en, missing) == missing
    assert onedragon_preflight_message_text(en, next_action) == next_action
