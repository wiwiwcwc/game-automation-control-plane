from __future__ import annotations

import uuid
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from PySide6.QtCore import QTime
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from ..domain.models import Job
from ..integrations.custom_cli import CustomCliIntegration
from ..integrations.maa_cli import (
    DEFAULT_EMULATOR_START_TIMEOUT_SECONDS,
    MUMU_EMULATOR_TYPE,
    MaaCliIntegration,
    discover_maa_cli,
    discover_mumu_cli,
)
from ..integrations.maa_punish import (
    MaaPunishIntegration,
    discover_fos,
    discover_fos_configurations,
    discover_fos_mumu_cli,
    read_fos_controller,
)
from ..integrations.maa_managed_task import (
    EXTERNAL_TASK_MODE,
    MANAGED_TASK_MODE,
    default_managed_daily,
)
from ..integrations.ok_ww import OkWwIntegration, discover_ok_ww
from ..integrations.onedragon import (
    ZZZ_ONEDRAGON_RUNNER_TYPE,
    ZzzOneDragonIntegration,
    discover_zzz_onedragon,
    format_instance_indices,
)
from .i18n import LanguageManager


class JobEditorDialog(QDialog):
    def __init__(
        self,
        job: Job | None = None,
        parent=None,
        i18n: LanguageManager | None = None,
    ):
        super().__init__(parent)
        self.job = job
        self.i18n = i18n or LanguageManager(persist=False)
        self.setWindowTitle(
            self.i18n.text("job.edit_title" if job else "job.add_title")
        )
        self.setModal(True)
        self.resize(860, 680)
        self.setMinimumSize(720, 560)

        self.game_name = QLineEdit()
        self.game_name.setPlaceholderText(self.i18n.text("job.placeholder_game"))
        self.job_name = QLineEdit()
        self.job_name.setPlaceholderText(self.i18n.text("job.placeholder_name"))

        self.integration_combo = QComboBox()
        self.integration_combo.addItem("Custom CLI", CustomCliIntegration.runner_type)
        self.integration_combo.addItem("MAA", MaaCliIntegration.runner_type)
        self.integration_combo.addItem("MAA_Punish", MaaPunishIntegration.runner_type)
        self.integration_combo.addItem("OK-WW", OkWwIntegration.runner_type)
        self.integration_combo.addItem(
            self.i18n.text("job.integration_zzz_onedragon"),
            ZZZ_ONEDRAGON_RUNNER_TYPE,
        )
        self.integration_combo.currentIndexChanged.connect(self._on_integration_changed)

        self.executable_path = QLineEdit()
        self.executable_path.setPlaceholderText(self.i18n.text("job.placeholder_executable"))
        self.executable_button = QPushButton(self.i18n.text("button.browse"))
        self.executable_button.clicked.connect(self._browse_executable)
        executable_row = QHBoxLayout()
        executable_row.addWidget(self.executable_path)
        executable_row.addWidget(self.executable_button)

        self.arguments = QPlainTextEdit()
        self.arguments.setPlaceholderText(self.i18n.text("job.placeholder_arguments"))
        self.arguments.setMinimumHeight(120)

        self.task_name = QLineEdit()
        self.task_name.setPlaceholderText(self.i18n.text("job.placeholder_task"))
        self._managed_task_name = f"control_plane_{uuid.uuid4().hex[:12]}"
        self.maa_task_mode = QComboBox()
        self.maa_task_mode.addItem(self.i18n.text("job.maa_mode_managed"), MANAGED_TASK_MODE)
        self.maa_task_mode.addItem(self.i18n.text("job.maa_mode_external"), EXTERNAL_TASK_MODE)
        self.maa_task_mode.currentIndexChanged.connect(self._update_maa_task_mode)

        defaults = default_managed_daily()
        self.maa_startup = QCheckBox(self.i18n.text("job.maa_startup"))
        self.maa_recruit = QCheckBox(self.i18n.text("job.maa_recruit"))
        self.maa_recruit_times = QSpinBox()
        self.maa_recruit_times.setRange(0, 99)
        self.maa_infrast = QCheckBox(self.i18n.text("job.maa_infrast"))
        self.maa_mall = QCheckBox(self.i18n.text("job.maa_mall"))
        self.maa_visit_friends = QCheckBox(self.i18n.text("job.maa_visit_friends"))
        self.maa_shopping = QCheckBox(self.i18n.text("job.maa_shopping"))
        self.maa_credit_fight = QCheckBox(self.i18n.text("job.maa_credit_fight"))
        self.maa_fight = QCheckBox(self.i18n.text("job.maa_fight"))
        self.maa_stage = QLineEdit()
        self.maa_stage.setPlaceholderText(self.i18n.text("job.maa_stage_placeholder"))
        self.maa_fight_times = QSpinBox()
        self.maa_fight_times.setRange(1, 2_147_483_647)
        self.maa_series = QComboBox()
        self.maa_series.addItem(self.i18n.text("job.maa_series_auto"), 0)
        for series in range(1, 11):
            self.maa_series.addItem(self.i18n.text("job.maa_series_times", times=series), series)
        self.maa_series.addItem(self.i18n.text("job.maa_series_disabled"), -1)
        self.maa_medicine = QSpinBox()
        self.maa_medicine.setRange(0, 999)
        self.maa_expiring_medicine = QSpinBox()
        self.maa_expiring_medicine.setRange(0, 99)
        self.maa_stone = QSpinBox()
        self.maa_stone.setRange(0, 99)
        self.maa_award = QCheckBox(self.i18n.text("job.maa_award"))
        self.maa_mail = QCheckBox(self.i18n.text("job.maa_mail"))
        for key, widget in (
            ("startup", self.maa_startup),
            ("recruit", self.maa_recruit),
            ("infrast", self.maa_infrast),
            ("mall", self.maa_mall),
            ("visit_friends", self.maa_visit_friends),
            ("shopping", self.maa_shopping),
            ("credit_fight", self.maa_credit_fight),
            ("fight", self.maa_fight),
            ("award", self.maa_award),
            ("mail", self.maa_mail),
        ):
            widget.setChecked(bool(defaults[key]))
        self.maa_recruit_times.setValue(int(defaults["recruit_times"]))
        self.maa_fight_times.setValue(int(defaults["fight_times"]))
        self.maa_series.setCurrentIndex(self.maa_series.findData(defaults["series"]))
        self.maa_medicine.setValue(int(defaults["medicine"]))
        self.maa_expiring_medicine.setValue(int(defaults["medicine_expire_days"]))
        self.maa_stone.setValue(int(defaults["stone"]))
        self.maa_recruit.toggled.connect(self._update_maa_option_fields)
        self.maa_mall.toggled.connect(self._update_maa_option_fields)
        self.maa_fight.toggled.connect(self._update_maa_option_fields)
        self.maa_award.toggled.connect(self._update_maa_option_fields)

        self.maa_daily_group = QGroupBox(self.i18n.text("job.maa_daily_group"))
        maa_form = QFormLayout(self.maa_daily_group)
        maa_form.addRow(self.maa_startup)
        maa_form.addRow(self.maa_recruit)
        maa_form.addRow(self.i18n.text("job.maa_recruit_times"), self.maa_recruit_times)
        maa_form.addRow(self.maa_infrast)
        maa_form.addRow(self.maa_mall)
        maa_form.addRow(self.maa_visit_friends)
        maa_form.addRow(self.maa_shopping)
        maa_form.addRow(self.maa_credit_fight)
        maa_form.addRow(self.maa_fight)
        maa_form.addRow(self.i18n.text("job.maa_stage"), self.maa_stage)
        maa_form.addRow(self.i18n.text("job.maa_fight_times"), self.maa_fight_times)
        maa_form.addRow(self.i18n.text("job.maa_series"), self.maa_series)
        maa_form.addRow(self.i18n.text("job.maa_medicine"), self.maa_medicine)
        maa_form.addRow(self.i18n.text("job.maa_expiring_medicine"), self.maa_expiring_medicine)
        maa_form.addRow(self.i18n.text("job.maa_stone"), self.maa_stone)
        maa_form.addRow(self.maa_award)
        maa_form.addRow(self.maa_mail)
        self.fos_config_combo = QComboBox()
        self.fos_refresh_button = QPushButton(self.i18n.text("button.refresh"))
        self.fos_refresh_button.clicked.connect(self._reload_fos_configurations)
        self.fos_config_combo.currentIndexChanged.connect(self._on_fos_config_changed)
        fos_config_row = QHBoxLayout()
        fos_config_row.addWidget(self.fos_config_combo, 1)
        fos_config_row.addWidget(self.fos_refresh_button)
        self.fos_config_container = QWidget()
        self.fos_config_container.setLayout(fos_config_row)
        self.auto_start_emulator = QCheckBox(self.i18n.text("job.auto_start_mumu"))
        self.auto_start_emulator.toggled.connect(self._update_emulator_fields)
        self.close_emulator_after_run = QCheckBox(
            self.i18n.text("job.close_mumu")
        )
        self.close_emulator_after_run.setChecked(True)
        self.close_fos_after_run = QCheckBox(self.i18n.text("job.close_fos"))
        self.close_fos_after_run.setChecked(True)
        self.emulator_executable_path = QLineEdit()
        self.emulator_executable_path.setPlaceholderText(self.i18n.text("job.placeholder_mumu"))
        self.emulator_button = QPushButton(self.i18n.text("button.browse"))
        self.emulator_button.clicked.connect(self._browse_emulator_executable)
        emulator_row = QHBoxLayout()
        emulator_row.addWidget(self.emulator_executable_path)
        emulator_row.addWidget(self.emulator_button)
        self.emulator_container = QWidget()
        self.emulator_container.setLayout(emulator_row)
        self.emulator_instance_index = QSpinBox()
        self.emulator_instance_index.setRange(0, 999)
        self.emulator_instance_index.setValue(0)
        self.emulator_start_timeout = QSpinBox()
        self.emulator_start_timeout.setRange(30, 600)
        self.emulator_start_timeout.setValue(DEFAULT_EMULATOR_START_TIMEOUT_SECONDS)
        self.emulator_start_timeout.setSuffix(self.i18n.text("job.seconds"))
        self.task_index = QSpinBox()
        self.task_index.setRange(1, 2_147_483_647)
        self.task_index.setValue(1)
        self.close_game_after_run = QCheckBox(
            self.i18n.text("job.close_wuthering")
        )
        self.close_game_after_run.setChecked(True)
        self.onedragon_instance_indices = QLineEdit()
        self.onedragon_instance_indices.setPlaceholderText(
            self.i18n.text("job.placeholder_zzz_instance")
        )
        self.onedragon_close_game = QCheckBox(self.i18n.text("job.zzz_close"))
        self.onedragon_close_game.setChecked(False)
        # Keep explicit aliases for callers/tests that use the game-specific
        # naming while the persisted schema remains integration-neutral.
        self.zzz_instance_indices = self.onedragon_instance_indices
        self.zzz_close_game_after_run = self.onedragon_close_game

        self.working_directory = QLineEdit()
        self.working_directory.setPlaceholderText(self.i18n.text("job.placeholder_working"))
        self.working_button = QPushButton(self.i18n.text("button.browse"))
        self.working_button.clicked.connect(self._browse_working_directory)
        working_row = QHBoxLayout()
        working_row.addWidget(self.working_directory)
        working_row.addWidget(self.working_button)
        self.working_container = QWidget()
        self.working_container.setLayout(working_row)

        self.timezone_id = QLineEdit("Asia/Shanghai")
        self.reset_time = QTimeEdit(QTime(4, 0))
        self.reset_time.setDisplayFormat("HH:mm")

        self.executable_label = QLabel(self.i18n.text("job.executable"))
        self.arguments_label = QLabel(self.i18n.text("job.arguments"))
        self.working_label = QLabel(self.i18n.text("job.working_directory"))
        self.task_label = QLabel(self.i18n.text("job.maa_task"))
        self.maa_task_mode_label = QLabel(self.i18n.text("job.maa_task_mode"))
        self.fos_config_label = QLabel(self.i18n.text("job.fos_config"))
        self.auto_start_label = QLabel(self.i18n.text("job.emulator_startup"))
        self.close_emulator_label = QLabel(self.i18n.text("job.after_maa"))
        self.close_fos_label = QLabel(self.i18n.text("job.fos_process"))
        self.emulator_executable_label = QLabel(self.i18n.text("job.mumu_tool"))
        self.emulator_instance_label = QLabel(self.i18n.text("job.mumu_instance"))
        self.emulator_timeout_label = QLabel(self.i18n.text("job.startup_timeout"))
        self.task_index_label = QLabel(self.i18n.text("job.okww_index"))
        self.close_game_label = QLabel(self.i18n.text("job.after_okww"))
        self.onedragon_instance_label = QLabel(self.i18n.text("job.zzz_instance"))
        self.onedragon_close_game_label = QLabel(self.i18n.text("job.zzz_close"))

        basic_group = QGroupBox(self.i18n.text("job.section_basic"))
        basic_form = QFormLayout(basic_group)
        basic_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        basic_form.addRow(self.i18n.text("job.integration"), self.integration_combo)
        basic_form.addRow(self.i18n.text("job.game"), self.game_name)
        basic_form.addRow(self.i18n.text("job.name"), self.job_name)

        runner_group = QGroupBox(self.i18n.text("job.section_runner"))
        form = QFormLayout(runner_group)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        form.addRow(self.executable_label, executable_row)
        form.addRow(self.maa_task_mode_label, self.maa_task_mode)
        form.addRow(self.task_label, self.task_name)
        form.addRow(self.maa_daily_group)
        form.addRow(self.fos_config_label, self.fos_config_container)
        form.addRow(self.auto_start_label, self.auto_start_emulator)
        form.addRow(self.close_emulator_label, self.close_emulator_after_run)
        form.addRow(self.close_fos_label, self.close_fos_after_run)
        form.addRow(self.emulator_executable_label, self.emulator_container)
        form.addRow(self.emulator_instance_label, self.emulator_instance_index)
        form.addRow(self.emulator_timeout_label, self.emulator_start_timeout)
        form.addRow(self.task_index_label, self.task_index)
        form.addRow(self.close_game_label, self.close_game_after_run)
        form.addRow(self.onedragon_instance_label, self.onedragon_instance_indices)
        form.addRow(self.onedragon_close_game_label, self.onedragon_close_game)
        form.addRow(self.arguments_label, self.arguments)
        form.addRow(self.working_label, self.working_container)

        schedule_group = QGroupBox(self.i18n.text("job.section_schedule"))
        schedule_form = QFormLayout(schedule_group)
        schedule_form.addRow(self.i18n.text("job.timezone"), self.timezone_id)
        schedule_form.addRow(self.i18n.text("job.reset_time"), self.reset_time)

        self.help_label = QLabel(
            self.i18n.text("job.help_custom")
        )
        self.help_label.setWordWrap(True)
        self.error_label = QLabel()
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet("color: #a61b1b;")

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setText(
            self.i18n.text("button.save")
        )
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(
            self.i18n.text("button.cancel")
        )
        self.buttons.accepted.connect(self._save)
        self.buttons.rejected.connect(self.reject)

        form_content = QWidget()
        form_layout = QVBoxLayout(form_content)
        form_layout.setContentsMargins(4, 4, 4, 4)
        form_layout.setSpacing(12)
        form_layout.addWidget(basic_group)
        form_layout.addWidget(runner_group)
        form_layout.addWidget(schedule_group)
        form_layout.addWidget(self.help_label)
        form_layout.addWidget(self.error_label)
        form_layout.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(form_content)

        layout = QVBoxLayout(self)
        layout.addWidget(scroll)
        layout.addWidget(self.buttons)

        self._loaded_fos_config_id = ""
        if job is not None:
            self._populate(job)
        self._on_integration_changed()
        self._update_maa_option_fields()

    def _populate(self, job: Job) -> None:
        config = job.runner_config
        index = self.integration_combo.findData(job.runner_type)
        if index >= 0:
            self.integration_combo.setCurrentIndex(index)
        self.game_name.setText(job.game_name)
        self.job_name.setText(job.name)
        self.executable_path.setText(str(config.get("executable_path", "")))
        self.task_name.setText(str(config.get("task_name", "")))
        task_mode = str(config.get("task_mode", EXTERNAL_TASK_MODE))
        mode_index = self.maa_task_mode.findData(task_mode)
        if mode_index >= 0:
            self.maa_task_mode.setCurrentIndex(mode_index)
        if task_mode == MANAGED_TASK_MODE:
            self._managed_task_name = str(config.get("task_name") or self._managed_task_name)
            managed = config.get("managed_daily")
            if isinstance(managed, dict):
                self._populate_managed_daily(managed)
        self._loaded_fos_config_id = str(config.get("config_id", ""))
        self.auto_start_emulator.setChecked(bool(config.get("auto_start_emulator", False)))
        self.close_emulator_after_run.setChecked(
            bool(config.get("close_emulator_after_run", False))
        )
        self.close_fos_after_run.setChecked(
            bool(config.get("close_fos_after_run", job.runner_type == MaaPunishIntegration.runner_type))
        )
        self.emulator_executable_path.setText(
            str(config.get("emulator_executable_path", ""))
        )
        instance_index = config.get("emulator_instance_index", 0)
        if isinstance(instance_index, int) and not isinstance(instance_index, bool):
            self.emulator_instance_index.setValue(max(0, instance_index))
        timeout = config.get(
            "emulator_start_timeout_seconds",
            DEFAULT_EMULATOR_START_TIMEOUT_SECONDS,
        )
        if isinstance(timeout, int) and not isinstance(timeout, bool):
            self.emulator_start_timeout.setValue(timeout)
        task_index = config.get("task_index", 1)
        if isinstance(task_index, int) and not isinstance(task_index, bool) and task_index > 0:
            self.task_index.setValue(task_index)
        self.close_game_after_run.setChecked(bool(config.get("close_game_after_run", True)))
        self.onedragon_instance_indices.setText(str(config.get("instance_indices", "")))
        self.onedragon_close_game.setChecked(bool(config.get("close_game_after_run", False)))
        arguments = config.get("arguments", [])
        self.arguments.setPlainText("\n".join(str(item) for item in arguments))
        self.working_directory.setText(str(config.get("working_directory") or ""))
        self.timezone_id.setText(job.timezone_id)
        self.reset_time.setTime(QTime(job.reset_minute // 60, job.reset_minute % 60))

    def _browse_executable(self) -> None:
        chooser_key = (
            "job.choose_zzz"
            if self.integration_combo.currentData() == ZZZ_ONEDRAGON_RUNNER_TYPE
            else "job.choose_executable"
        )
        path, _ = QFileDialog.getOpenFileName(self, self.i18n.text(chooser_key))
        if path:
            self.executable_path.setText(path)
            if self.integration_combo.currentData() == MaaPunishIntegration.runner_type:
                self._reload_fos_configurations()

    def _browse_working_directory(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, self.i18n.text("job.choose_working")
        )
        if path:
            self.working_directory.setText(path)

    def _browse_emulator_executable(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, self.i18n.text("job.choose_mumu")
        )
        if path:
            self.emulator_executable_path.setText(path)

    def _on_integration_changed(self) -> None:
        runner_type = self.integration_combo.currentData()
        is_maa = runner_type == MaaCliIntegration.runner_type
        is_fos = runner_type == MaaPunishIntegration.runner_type
        is_ok_ww = runner_type == OkWwIntegration.runner_type
        is_onedragon = runner_type == ZZZ_ONEDRAGON_RUNNER_TYPE
        self.auto_start_emulator.setEnabled(True)
        self.maa_task_mode_label.setVisible(is_maa)
        self.maa_task_mode.setVisible(is_maa)
        self.fos_config_label.setVisible(is_fos)
        self.fos_config_container.setVisible(is_fos)
        self.auto_start_label.setVisible(is_maa or is_fos)
        self.auto_start_emulator.setVisible(is_maa or is_fos)
        self.close_fos_label.setVisible(is_fos)
        self.close_fos_after_run.setVisible(is_fos)
        self.task_index_label.setVisible(is_ok_ww)
        self.task_index.setVisible(is_ok_ww)
        self.close_game_label.setVisible(is_ok_ww)
        self.close_game_after_run.setVisible(is_ok_ww)
        self.onedragon_instance_label.setVisible(is_onedragon)
        self.onedragon_instance_indices.setVisible(is_onedragon)
        self.onedragon_close_game_label.setVisible(is_onedragon)
        self.onedragon_close_game.setVisible(is_onedragon)
        specialized = is_maa or is_fos or is_ok_ww or is_onedragon
        self.arguments_label.setVisible(not specialized)
        self.arguments.setVisible(not specialized)
        self.working_label.setVisible(not specialized)
        self.working_container.setVisible(not specialized)
        if is_maa:
            self.executable_label.setText(self.i18n.text("job.maa_executable"))
            self.executable_path.setPlaceholderText(self.i18n.text("job.placeholder_executable"))
            self.game_name.setText(self.i18n.text("game.arknights"))
            self.game_name.setReadOnly(True)
            self.help_label.setText(self.i18n.text("job.help_maa"))
            if self.job is None or self.job.runner_type != MaaCliIntegration.runner_type:
                discovered = discover_maa_cli()
                if discovered:
                    self.executable_path.setText(discovered)
                mumu_cli = discover_mumu_cli()
                if mumu_cli and not self.emulator_executable_path.text().strip():
                    self.emulator_executable_path.setText(mumu_cli)
        elif is_fos:
            self.executable_label.setText(self.i18n.text("job.fos_executable"))
            self.executable_path.setPlaceholderText(self.i18n.text("job.placeholder_fos"))
            self.game_name.setText(self.i18n.text("game.punishing"))
            self.game_name.setReadOnly(True)
            self.close_emulator_label.setText(self.i18n.text("job.after_fos"))
            self.help_label.setText(self.i18n.text("job.help_fos"))
            if self.job is None or self.job.runner_type != MaaPunishIntegration.runner_type:
                discovered = discover_fos()
                if discovered:
                    self.executable_path.setText(discovered)
            self._reload_fos_configurations()
        elif is_ok_ww:
            self.executable_label.setText(self.i18n.text("job.okww_executable"))
            self.executable_path.setPlaceholderText(self.i18n.text("job.placeholder_executable"))
            self.game_name.setText(self.i18n.text("game.wuthering"))
            self.game_name.setReadOnly(True)
            self.help_label.setText(self.i18n.text("job.help_okww"))
            if self.job is None or self.job.runner_type != OkWwIntegration.runner_type:
                discovered = discover_ok_ww()
                if discovered:
                    self.executable_path.setText(discovered)
        elif is_onedragon:
            self.executable_label.setText(self.i18n.text("job.zzz_executable"))
            self.executable_path.setPlaceholderText(self.i18n.text("job.placeholder_zzz_executable"))
            self.game_name.setText(self.i18n.text("game.zzz"))
            self.game_name.setReadOnly(True)
            self.help_label.setText(self.i18n.text("job.help_zzz"))
            if self.job is None or self.job.runner_type != ZZZ_ONEDRAGON_RUNNER_TYPE:
                discovered = discover_zzz_onedragon()
                if discovered:
                    self.executable_path.setText(discovered)
        else:
            self.executable_label.setText(self.i18n.text("job.executable"))
            self.executable_path.setPlaceholderText(self.i18n.text("job.placeholder_executable"))
            self.game_name.setReadOnly(False)
            self.help_label.setText(self.i18n.text("job.help_custom"))
        if not is_fos:
            self.close_emulator_label.setText(self.i18n.text("job.after_maa"))
        self._update_maa_task_mode()
        self._update_emulator_fields()

    def _update_maa_task_mode(self) -> None:
        is_maa = self.integration_combo.currentData() == MaaCliIntegration.runner_type
        managed = is_maa and self.maa_task_mode.currentData() == MANAGED_TASK_MODE
        external = is_maa and not managed
        self.task_label.setVisible(external)
        self.task_name.setVisible(external)
        self.maa_daily_group.setVisible(managed)

    def _update_maa_option_fields(self) -> None:
        self.maa_recruit_times.setEnabled(self.maa_recruit.isChecked())
        for widget in (self.maa_visit_friends, self.maa_shopping, self.maa_credit_fight):
            widget.setEnabled(self.maa_mall.isChecked())
        for widget in (
            self.maa_stage,
            self.maa_fight_times,
            self.maa_series,
            self.maa_medicine,
            self.maa_expiring_medicine,
            self.maa_stone,
        ):
            widget.setEnabled(self.maa_fight.isChecked())
        self.maa_mail.setEnabled(self.maa_award.isChecked())

    def _populate_managed_daily(self, options: dict[str, object]) -> None:
        for key, widget in (
            ("startup", self.maa_startup),
            ("recruit", self.maa_recruit),
            ("infrast", self.maa_infrast),
            ("mall", self.maa_mall),
            ("visit_friends", self.maa_visit_friends),
            ("shopping", self.maa_shopping),
            ("credit_fight", self.maa_credit_fight),
            ("fight", self.maa_fight),
            ("award", self.maa_award),
            ("mail", self.maa_mail),
        ):
            if isinstance(options.get(key), bool):
                widget.setChecked(bool(options[key]))
        for key, widget in (
            ("recruit_times", self.maa_recruit_times),
            ("fight_times", self.maa_fight_times),
            ("medicine", self.maa_medicine),
            ("medicine_expire_days", self.maa_expiring_medicine),
            ("stone", self.maa_stone),
        ):
            value = options.get(key)
            if isinstance(value, int) and not isinstance(value, bool):
                widget.setValue(value)
        stage = options.get("stage")
        if isinstance(stage, str):
            self.maa_stage.setText(stage)
        series = options.get("series")
        index = self.maa_series.findData(series)
        if index >= 0:
            self.maa_series.setCurrentIndex(index)
        self._update_maa_option_fields()

    def _update_emulator_fields(self) -> None:
        runner_type = self.integration_combo.currentData()
        supports_mumu = runner_type in {
            MaaCliIntegration.runner_type,
            MaaPunishIntegration.runner_type,
        }
        visible = supports_mumu and self.auto_start_emulator.isChecked()
        self.emulator_executable_label.setVisible(visible)
        self.emulator_container.setVisible(visible)
        self.emulator_instance_label.setVisible(visible)
        self.emulator_instance_index.setVisible(visible)
        self.emulator_timeout_label.setVisible(visible)
        self.emulator_start_timeout.setVisible(visible)
        self.close_emulator_label.setVisible(visible)
        self.close_emulator_after_run.setVisible(visible)

    def _reload_fos_configurations(self) -> None:
        wanted = self._loaded_fos_config_id or str(self.fos_config_combo.currentData() or "")
        values = discover_fos_configurations(self.executable_path.text().strip())
        self.fos_config_combo.blockSignals(True)
        self.fos_config_combo.clear()
        for configuration in values:
            self.fos_config_combo.addItem(configuration.name, configuration.config_id)
        index = self.fos_config_combo.findData(wanted)
        if index >= 0:
            self.fos_config_combo.setCurrentIndex(index)
        self.fos_config_combo.blockSignals(False)
        self._loaded_fos_config_id = ""
        self._on_fos_config_changed()

    def _on_fos_config_changed(self) -> None:
        config_id = str(self.fos_config_combo.currentData() or "")
        selected = next(
            (
                value
                for value in discover_fos_configurations(self.executable_path.text().strip())
                if value.config_id == config_id
            ),
            None,
        )
        controller = read_fos_controller(selected) if selected is not None else None
        if controller is None:
            return
        supports_mumu = controller.controller_type == "Android" and controller.mumu_index is not None
        self.auto_start_emulator.setEnabled(supports_mumu)
        if not supports_mumu:
            self.auto_start_emulator.setChecked(False)
        if controller.mumu_index is not None:
            self.emulator_instance_index.setValue(controller.mumu_index)
        mumu_cli = discover_fos_mumu_cli(controller)
        if mumu_cli:
            self.emulator_executable_path.setText(mumu_cli)

    def _save(self) -> None:
        payload, errors = self._payload()
        if errors:
            self.error_label.setText("\n".join(errors))
            return
        self.error_label.clear()
        self.payload = payload
        self.accept()

    def _payload(self) -> tuple[dict[str, object], list[str]]:
        errors: list[str] = []
        runner_type = str(self.integration_combo.currentData())
        if runner_type == MaaCliIntegration.runner_type:
            game_name = (
                self.job.game_name
                if self.job is not None and self.job.runner_type == runner_type
                else self.i18n.text("game.arknights")
            )
        elif runner_type == OkWwIntegration.runner_type:
            game_name = (
                self.job.game_name
                if self.job is not None and self.job.runner_type == runner_type
                else self.i18n.text("game.wuthering")
            )
        else:
            game_name = self.game_name.text().strip()
        job_name = self.job_name.text().strip()
        executable_path = self.executable_path.text().strip()
        working_directory = self.working_directory.text().strip()
        timezone_id = self.timezone_id.text().strip()
        if not game_name:
            errors.append(self.i18n.text("error.game_required"))
        if not job_name:
            errors.append(self.i18n.text("error.name_required"))
        if not timezone_id:
            errors.append(self.i18n.text("error.timezone_required"))
        else:
            try:
                ZoneInfo(timezone_id)
            except ZoneInfoNotFoundError:
                errors.append(
                    self.i18n.text("error.timezone_unknown", timezone=timezone_id)
                )

        if runner_type == MaaCliIntegration.runner_type:
            task_mode = str(self.maa_task_mode.currentData())
            config = {
                "config_version": MaaCliIntegration.config_version,
                "executable_path": executable_path,
                "task_mode": task_mode,
                "task_name": (
                    self._managed_task_name
                    if task_mode == MANAGED_TASK_MODE
                    else self.task_name.text().strip()
                ),
            }
            if task_mode == MANAGED_TASK_MODE:
                config["managed_daily"] = {
                    "startup": self.maa_startup.isChecked(),
                    "recruit": self.maa_recruit.isChecked(),
                    "recruit_times": self.maa_recruit_times.value(),
                    "infrast": self.maa_infrast.isChecked(),
                    "mall": self.maa_mall.isChecked(),
                    "visit_friends": self.maa_visit_friends.isChecked(),
                    "shopping": self.maa_shopping.isChecked(),
                    "credit_fight": self.maa_credit_fight.isChecked(),
                    "fight": self.maa_fight.isChecked(),
                    "stage": self.maa_stage.text().strip(),
                    "fight_times": self.maa_fight_times.value(),
                    "series": int(self.maa_series.currentData()),
                    "medicine": self.maa_medicine.value(),
                    "medicine_expire_days": self.maa_expiring_medicine.value(),
                    "stone": self.maa_stone.value(),
                    "award": self.maa_award.isChecked(),
                    "mail": self.maa_mail.isChecked(),
                }
            if self.auto_start_emulator.isChecked():
                config.update(
                    {
                        "auto_start_emulator": True,
                        "emulator_type": MUMU_EMULATOR_TYPE,
                        "emulator_executable_path": self.emulator_executable_path.text().strip(),
                        "emulator_instance_index": self.emulator_instance_index.value(),
                        "emulator_start_timeout_seconds": self.emulator_start_timeout.value(),
                        "close_emulator_after_run": self.close_emulator_after_run.isChecked(),
                    }
                )
            validation = MaaCliIntegration().validate_config(config)
        elif runner_type == MaaPunishIntegration.runner_type:
            game_name = (
                self.job.game_name
                if self.job is not None and self.job.runner_type == runner_type
                else self.i18n.text("game.punishing")
            )
            config = {
                "config_version": MaaPunishIntegration.config_version,
                "executable_path": executable_path,
                "config_id": str(self.fos_config_combo.currentData() or ""),
                "close_fos_after_run": self.close_fos_after_run.isChecked(),
            }
            if self.auto_start_emulator.isChecked():
                config.update(
                    {
                        "auto_start_emulator": True,
                        "emulator_type": MUMU_EMULATOR_TYPE,
                        "emulator_executable_path": self.emulator_executable_path.text().strip(),
                        "emulator_instance_index": self.emulator_instance_index.value(),
                        "emulator_start_timeout_seconds": self.emulator_start_timeout.value(),
                        "close_emulator_after_run": self.close_emulator_after_run.isChecked(),
                    }
                )
            validation = MaaPunishIntegration().validate_config(config)
        elif runner_type == OkWwIntegration.runner_type:
            config = {
                "config_version": OkWwIntegration.config_version,
                "executable_path": executable_path,
                "task_index": self.task_index.value(),
                "close_game_after_run": self.close_game_after_run.isChecked(),
            }
            validation = OkWwIntegration().validate_config(config)
        elif runner_type == ZZZ_ONEDRAGON_RUNNER_TYPE:
            game_name = (
                self.job.game_name
                if self.job is not None and self.job.runner_type == runner_type
                else self.i18n.text("game.zzz")
            )
            instance_value = self.onedragon_instance_indices.text().strip()
            try:
                instance_value = format_instance_indices(instance_value)
            except ValueError:
                # Let the adapter return the same clear validation error while
                # preserving the user's raw input in the form.
                pass
            config = {
                "config_version": ZzzOneDragonIntegration.config_version,
                "executable_path": executable_path,
                "instance_indices": instance_value,
                "close_game_after_run": self.onedragon_close_game.isChecked(),
            }
            validation = ZzzOneDragonIntegration().validate_config(config)
        else:
            config = {
                "config_version": CustomCliIntegration.config_version,
                "executable_path": executable_path,
                "arguments": self.arguments.toPlainText().splitlines(),
                "working_directory": working_directory or None,
            }
            validation = CustomCliIntegration().validate_config(config)
        errors.extend(validation.errors)
        payload = {
            "game_name": game_name,
            "name": job_name,
            "runner_type": runner_type,
            "runner_config_version": int(config["config_version"]),
            "runner_config": config,
            "timezone_id": timezone_id,
            "reset_minute": self.reset_time.time().hour() * 60 + self.reset_time.time().minute(),
            "enabled": True if self.job is None else self.job.enabled,
            "job_id": None if self.job is None else self.job.id,
        }
        return payload, errors


__all__ = ["JobEditorDialog"]
