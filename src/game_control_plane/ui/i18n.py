from __future__ import annotations

import re

from PySide6.QtCore import QObject, QSettings, Signal


DEFAULT_LANGUAGE = "zh_CN"
SUPPORTED_LANGUAGES = ("zh_CN", "en_US")


_ZH_CN = {
    "app.title": "游戏自动化控制台",
    "menu.settings": "设置",
    "menu.language": "语言",
    "language.zh_CN": "简体中文",
    "language.en_US": "English",
    "game.arknights": "明日方舟",
    "game.punishing": "战双帕弥什",
    "game.wuthering": "鸣潮",
    "dashboard.eyebrow": "GAME AUTOMATION",
    "dashboard.title": "自动化控制台",
    "dashboard.subtitle": "集中管理游戏日常任务、运行状态与日志",
    "dashboard.pending": "待完成",
    "dashboard.completed": "已完成",
    "dashboard.running": "运行中",
    "dashboard.current": "当前状态",
    "dashboard.idle": "空闲",
    "dashboard.queue_active": "每日队列运行中",
    "dashboard.running_one": "{name}",
    "dashboard.running_many": "{count} 个任务正在运行",
    "dashboard.add": "添加任务",
    "dashboard.run_dailies": "运行今日任务",
    "dashboard.queue_note": "每日队列会按顺序执行队列内任务；其他游戏仍可同时手动运行。任务完成状态仍由你确认。",
    "dashboard.empty_title": "还没有自动化任务",
    "dashboard.empty_body": "添加 MAA、战双、OK-WW 或自定义命令，建立你的游戏日常工作流。",
    "card.disabled": "已停用",
    "card.daily": "今日状态",
    "card.execution": "执行状态",
    "card.last_run": "上次运行",
    "card.pending": "待完成",
    "card.completed": "已完成",
    "card.queued": "排队中",
    "card.running": "运行中",
    "card.never_run": "从未运行",
    "card.exit": "退出码 {code}",
    "card.duration": "耗时 {duration}",
    "state.starting": "正在启动",
    "state.running": "运行中",
    "state.exited": "执行已完成",
    "state.failed": "运行失败",
    "state.needs_attention": "部分完成 · 需要检查",
    "state.interrupted": "已中断",
    "button.run": "运行",
    "button.mark_completed": "标记完成",
    "button.mark_pending": "恢复待完成",
    "button.view_log": "查看日志",
    "button.edit": "编辑",
    "button.disable": "停用",
    "button.enable": "启用",
    "button.remove": "删除",
    "button.move_up": "上移",
    "button.move_down": "下移",
    "button.save": "保存",
    "button.cancel": "取消",
    "button.close": "关闭",
    "button.browse": "浏览…",
    "button.refresh": "刷新",
    "job.add_title": "添加自动化任务",
    "job.edit_title": "编辑自动化任务",
    "job.integration": "接入方式",
    "job.game": "游戏",
    "job.name": "任务名称",
    "job.executable": "可执行程序 / 解释器",
    "job.arguments": "参数",
    "job.working_directory": "工作目录",
    "job.maa_task": "MAA 任务名称",
    "job.maa_task_mode": "MAA 任务来源",
    "job.maa_mode_managed": "由控制台管理日常任务（推荐）",
    "job.maa_mode_external": "使用现有 maa-cli 任务文件",
    "job.maa_daily_group": "MAA 日常内容",
    "job.maa_startup": "启动游戏并进入主页",
    "job.maa_recruit": "自动公招",
    "job.maa_recruit_times": "公招次数上限",
    "job.maa_infrast": "基建换班",
    "job.maa_mall": "信用与购物",
    "job.maa_visit_friends": "访问好友并领取信用",
    "job.maa_shopping": "使用信用点购物",
    "job.maa_credit_fight": "执行一次 OF-1 信用助战",
    "job.maa_fight": "消耗理智作战",
    "job.maa_stage": "关卡",
    "job.maa_stage_placeholder": "留空表示当前或上次关卡",
    "job.maa_fight_times": "总战斗次数上限",
    "job.maa_series": "连续代理次数",
    "job.maa_series_auto": "自动选择当前最大次数",
    "job.maa_series_times": "每轮 ×{times}",
    "job.maa_series_disabled": "关闭连续代理",
    "job.maa_medicine": "可使用理智药数量",
    "job.maa_expiring_medicine": "使用几天内过期的理智药",
    "job.maa_stone": "可使用源石数量",
    "job.maa_award": "领取日常/周常奖励",
    "job.maa_mail": "领取邮件奖励",
    "job.fos_config": "FOS 任务配置",
    "job.emulator_startup": "模拟器启动",
    "job.after_maa": "MAA 成功结束后",
    "job.after_fos": "战双任务成功结束后",
    "job.fos_process": "FOS 助手进程",
    "job.mumu_tool": "MuMu 命令工具",
    "job.mumu_instance": "MuMu 实例编号",
    "job.startup_timeout": "启动等待时间",
    "job.okww_index": "OK-WW 任务序号",
    "job.after_okww": "OK-WW 成功结束后",
    "job.timezone": "时区",
    "job.reset_time": "每日重置时间",
    "job.section_basic": "基本信息",
    "job.section_runner": "运行配置",
    "job.section_schedule": "每日规则",
    "job.placeholder_game": "例如：鸣潮",
    "job.placeholder_name": "例如：每日任务",
    "job.placeholder_executable": "请选择绝对路径",
    "job.placeholder_arguments": "每行一个参数，请勿填写整段 Shell 命令。",
    "job.placeholder_task": "例如：daily",
    "job.placeholder_mumu": "mumu-cli.exe 的绝对路径",
    "job.placeholder_fos": "请选择 FOS.exe",
    "job.placeholder_working": "可选的绝对文件夹路径",
    "job.auto_start_mumu": "自动启动并监控 MuMu",
    "job.close_mumu": "仅当本次由控制台启动时，成功后关闭该 MuMu 实例",
    "job.close_fos": "成功后关闭本任务关联的 FOS",
    "job.close_wuthering": "任务成功后关闭《鸣潮》",
    "job.seconds": " 秒",
    "job.maa_executable": "MAA 可执行程序（maa-cli.exe）",
    "job.fos_executable": "战双助手（FOS.exe）",
    "job.okww_executable": "OK-WW 可执行程序（ok-ww.exe）",
    "job.help_custom": "程序会被直接启动。脚本必须明确选择 Python 或 PowerShell 等解释器，不会通过隐式 Shell 执行。",
    "job.help_maa": "推荐由控制台生成独立任务：可选择信用、好友、购物、体力与连续代理。只有所有已选任务都有完成摘要，且理智作战至少完成一局，才会判定成功并关闭本次启动的 MuMu。",
    "job.help_fos": "选择 FOS 中已经保存的任务配置。控制台会启动或复用 FOS，并等待真正的任务流程结果；可在成功后关闭关联的 FOS，MuMu 实例信息会从 FOS 配置自动读取。",
    "job.help_okww": "OK-WW 会执行所选任务一次。关闭游戏选项会添加 -e；取消后，自动化结束但保留游戏窗口。",
    "job.choose_executable": "选择可执行程序或解释器",
    "job.choose_working": "选择工作目录",
    "job.choose_mumu": "选择 MuMu 命令工具",
    "error.game_required": "请输入游戏名称。",
    "error.name_required": "请输入任务名称。",
    "error.timezone_required": "请输入时区。",
    "error.timezone_unknown": "无法识别时区：{timezone}",
    "preflight.title": "MAA 设置向导",
    "preflight.heading": "运行前检查 MAA",
    "preflight.description": "游戏尚未开始。请先处理第一个失败步骤，然后重新检查。",
    "preflight.step.executable": "MAA 程序",
    "preflight.step.task": "MAA 任务",
    "preflight.step.dry_run": "任务配置",
    "preflight.step.adb": "模拟器连接",
    "fos_preflight.title": "战双设置向导",
    "fos_preflight.heading": "运行前检查战双助手",
    "fos_preflight.description": "游戏尚未开始。请先处理第一个失败步骤，然后重新检查。",
    "fos_preflight.step.executable": "FOS 程序",
    "fos_preflight.step.fos_config": "FOS 任务配置",
    "fos_preflight.step.emulator": "模拟器",
    "fos_preflight.step.launch": "自动运行接口",
    "fos_preflight.all_passed": "全部检查通过，战双任务已经可以运行。",
    "fos_preflight.progress_title": "战双设置检查",
    "fos_preflight.checking": "正在检查战双设置…",
    "fos_preflight.progress.program": "正在检查 FOS 程序…",
    "fos_preflight.progress.config": "正在读取 FOS 任务配置…",
    "fos_preflight.progress.emulator": "正在检查 FOS 关联的 MuMu 实例…",
    "fos_preflight.progress.mumu_wait": "正在等待 MuMu 实例 {instance} 启动 Android… {elapsed}/{timeout} 秒",
    "preflight.all_passed": "全部检查通过，MAA 已可以运行。",
    "preflight.next_step": "下一步",
    "preflight.show_details": "显示技术详情",
    "preflight.hide_details": "收起技术详情",
    "preflight.retry": "重新检查",
    "preflight.edit": "编辑任务",
    "preflight.run": "立即运行",
    "preflight.checking": "正在检查 MAA 设置…",
    "preflight.progress_title": "MAA 设置检查",
    "preflight.progress.program": "正在检查 MAA 程序…",
    "preflight.progress.task": "正在检查所选 MAA 任务…",
    "preflight.progress.managed_task": "正在生成控制台管理的 MAA 日常任务…",
    "preflight.progress.config": "正在安全验证任务配置…",
    "preflight.progress.emulator": "正在检查模拟器连接…",
    "preflight.progress.mumu_check": "正在检查 MuMu 实例 {instance}…",
    "preflight.progress.mumu_start": "正在启动 MuMu 实例 {instance}…",
    "preflight.progress.mumu_wait": "正在等待 MuMu 实例 {instance} 连接 ADB… {elapsed}/{timeout} 秒",
    "history.title": "运行历史 · {title}",
    "history.timestamp": "时间",
    "history.state": "状态",
    "history.duration": "耗时",
    "history.exit_code": "退出码",
    "history.error": "错误摘要",
    "history.stdout": "标准输出 stdout",
    "history.stderr": "标准错误 stderr",
    "history.no_runs": "这个任务还没有运行记录。",
    "history.summary": "运行 {run_id} · {state} · 耗时：{duration} · 退出码：{exit_code}",
    "history.log_missing": "没有可用的运行日志。",
    "history.log_gone": "运行日志已被清理或无法读取。",
    "history.log_tail": "[仅显示日志最后 {limit}。]\n{text}",
    "message.save_failed_title": "无法保存任务",
    "message.start_active_title": "任务已在运行",
    "message.start_active_body": "这个任务正在运行，或已经在每日队列中。",
    "message.start_failed_title": "无法启动任务",
    "message.nothing_title": "没有可运行的任务",
    "message.nothing_body": "目前没有已启用且等待完成的今日任务。",
    "message.preflight_failed_title": "无法检查 MAA 设置",
    "message.preflight_failed_body": "设置检查未能返回结果。",
    "message.fos_preflight_failed_title": "无法检查战双设置",
    "message.fos_preflight_failed_body": "战双设置检查未能返回结果。",
    "message.remove_title": "删除自动化任务？",
    "message.remove_body": "确定删除“{name}”及其运行历史吗？",
    "message.close_running_title": "仍有任务正在运行",
    "message.close_running_body": "仍有 {count} 个任务正在运行。关闭后将停止跟踪；外部程序可能继续运行，也可能终止。下次启动时这些记录会标记为已中断。仍要关闭吗？",
    "message.app_error_title": "应用程序错误",
    "message.app_error_body": "发生了未预期的错误，详情已写入：\n{path}",
}


_EN_US = {
    "app.title": "Game Automation Control Plane",
    "menu.settings": "Settings",
    "menu.language": "Language",
    "language.zh_CN": "简体中文",
    "language.en_US": "English",
    "game.arknights": "Arknights",
    "game.punishing": "Punishing: Gray Raven",
    "game.wuthering": "Wuthering Waves",
    "dashboard.eyebrow": "GAME AUTOMATION",
    "dashboard.title": "Automation Control Plane",
    "dashboard.subtitle": "Manage daily game automations, live status, and logs in one place",
    "dashboard.pending": "Pending",
    "dashboard.completed": "Completed",
    "dashboard.running": "Running",
    "dashboard.current": "Current",
    "dashboard.idle": "Idle",
    "dashboard.queue_active": "Daily queue active",
    "dashboard.running_one": "{name}",
    "dashboard.running_many": "{count} automations running",
    "dashboard.add": "Add automation",
    "dashboard.run_dailies": "Run Today's Dailies",
    "dashboard.queue_note": "The daily queue runs its items sequentially; other games can still run manually at the same time. Completion remains manual.",
    "dashboard.empty_title": "No automations yet",
    "dashboard.empty_body": "Add MAA, MAA_Punish, OK-WW, or a custom command to build your daily workflow.",
    "card.disabled": "Disabled",
    "card.daily": "Daily status",
    "card.execution": "Execution",
    "card.last_run": "Last run",
    "card.pending": "Pending",
    "card.completed": "Completed",
    "card.queued": "Queued",
    "card.running": "Running",
    "card.never_run": "Never run",
    "card.exit": "exit {code}",
    "card.duration": "Duration {duration}",
    "state.starting": "Starting",
    "state.running": "Running",
    "state.exited": "Completed",
    "state.failed": "Failed",
    "state.needs_attention": "Partial · needs attention",
    "state.interrupted": "Interrupted",
    "button.run": "Run",
    "button.mark_completed": "Mark completed",
    "button.mark_pending": "Mark pending",
    "button.view_log": "View log",
    "button.edit": "Edit",
    "button.disable": "Disable",
    "button.enable": "Enable",
    "button.remove": "Remove",
    "button.move_up": "Move up",
    "button.move_down": "Move down",
    "button.save": "Save",
    "button.cancel": "Cancel",
    "button.close": "Close",
    "button.browse": "Browse…",
    "button.refresh": "Refresh",
    "job.add_title": "Add Automation",
    "job.edit_title": "Edit Automation",
    "job.integration": "Integration",
    "job.game": "Game",
    "job.name": "Automation name",
    "job.executable": "Executable / interpreter",
    "job.arguments": "Arguments",
    "job.working_directory": "Working directory",
    "job.maa_task": "MAA task name",
    "job.maa_task_mode": "MAA task source",
    "job.maa_mode_managed": "Manage daily tasks here (recommended)",
    "job.maa_mode_external": "Use an existing maa-cli task file",
    "job.maa_daily_group": "MAA daily content",
    "job.maa_startup": "Start the game and enter Home",
    "job.maa_recruit": "Automatic recruitment",
    "job.maa_recruit_times": "Recruitment limit",
    "job.maa_infrast": "Infrastructure shift",
    "job.maa_mall": "Credits and shopping",
    "job.maa_visit_friends": "Visit friends and collect Credits",
    "job.maa_shopping": "Spend Credits in the store",
    "job.maa_credit_fight": "Run one OF-1 Credit support battle",
    "job.maa_fight": "Spend Sanity in combat",
    "job.maa_stage": "Stage",
    "job.maa_stage_placeholder": "Blank uses the current or previous stage",
    "job.maa_fight_times": "Total battle limit",
    "job.maa_series": "Consecutive battle count",
    "job.maa_series_auto": "Automatically choose the current maximum",
    "job.maa_series_times": "×{times} per series",
    "job.maa_series_disabled": "Disable consecutive battles",
    "job.maa_medicine": "Sanity Potions allowed",
    "job.maa_expiring_medicine": "Use Potions expiring within days",
    "job.maa_stone": "Originite Prime allowed",
    "job.maa_award": "Collect daily/weekly rewards",
    "job.maa_mail": "Collect mail rewards",
    "job.fos_config": "FOS task configuration",
    "job.emulator_startup": "Emulator startup",
    "job.after_maa": "After successful MAA run",
    "job.after_fos": "After successful MAA_Punish run",
    "job.fos_process": "FOS assistant process",
    "job.mumu_tool": "MuMu command tool",
    "job.mumu_instance": "MuMu instance number",
    "job.startup_timeout": "Startup timeout",
    "job.okww_index": "OK-WW task index",
    "job.after_okww": "After successful OK-WW run",
    "job.timezone": "Timezone",
    "job.reset_time": "Daily reset time",
    "job.section_basic": "Basic information",
    "job.section_runner": "Launch configuration",
    "job.section_schedule": "Daily rules",
    "job.placeholder_game": "For example, Wuthering Waves",
    "job.placeholder_name": "For example, Daily tasks",
    "job.placeholder_executable": "Choose an absolute path",
    "job.placeholder_arguments": "One argument per line. Do not enter a shell command.",
    "job.placeholder_task": "For example, daily",
    "job.placeholder_mumu": "Absolute path to mumu-cli.exe",
    "job.placeholder_fos": "Choose FOS.exe",
    "job.placeholder_working": "Optional absolute folder",
    "job.auto_start_mumu": "Start and monitor MuMu automatically",
    "job.close_mumu": "Close this MuMu instance after success only when started here",
    "job.close_fos": "Close the associated FOS after success",
    "job.close_wuthering": "Close Wuthering Waves after the task succeeds",
    "job.seconds": " seconds",
    "job.maa_executable": "MAA executable (maa-cli.exe)",
    "job.fos_executable": "MAA_Punish assistant (FOS.exe)",
    "job.okww_executable": "OK-WW executable (ok-ww.exe)",
    "job.help_custom": "The selected program is launched directly. Scripts must use an explicit interpreter such as Python or PowerShell; no implicit shell is used.",
    "job.help_maa": "The recommended mode generates an isolated task with Credits, friends, shopping, Sanity, and consecutive-battle controls. Success requires every selected task summary and at least one completed Sanity battle before an owned MuMu instance can close.",
    "job.help_fos": "Choose a task configuration already saved in FOS. Control Plane starts or reuses FOS, waits for the real task-flow result, and can close the associated FOS after success; MuMu details are read from the FOS configuration.",
    "job.help_okww": "OK-WW runs the selected task once. The close option adds -e; without it, automation exits and leaves the game open.",
    "job.choose_executable": "Choose executable or interpreter",
    "job.choose_working": "Choose working directory",
    "job.choose_mumu": "Choose MuMu command tool",
    "error.game_required": "Game name is required.",
    "error.name_required": "Automation name is required.",
    "error.timezone_required": "Timezone is required.",
    "error.timezone_unknown": "Unknown timezone: {timezone}",
    "preflight.title": "MAA Setup Guide",
    "preflight.heading": "Check MAA before starting",
    "preflight.description": "The game has not been started yet. Complete the first failed step, then check again.",
    "preflight.step.executable": "MAA program",
    "preflight.step.task": "MAA task",
    "preflight.step.dry_run": "Task configuration",
    "preflight.step.adb": "Emulator connection",
    "fos_preflight.title": "MAA_Punish Setup Guide",
    "fos_preflight.heading": "Check MAA_Punish before starting",
    "fos_preflight.description": "The game has not been started yet. Complete the first failed step, then check again.",
    "fos_preflight.step.executable": "FOS program",
    "fos_preflight.step.fos_config": "FOS task configuration",
    "fos_preflight.step.emulator": "Emulator",
    "fos_preflight.step.launch": "Automatic launch contract",
    "fos_preflight.all_passed": "All checks passed. MAA_Punish is ready to run.",
    "fos_preflight.progress_title": "MAA_Punish setup check",
    "fos_preflight.checking": "Checking MAA_Punish setup…",
    "fos_preflight.progress.program": "Checking the FOS program…",
    "fos_preflight.progress.config": "Reading the selected FOS configuration…",
    "fos_preflight.progress.emulator": "Checking the MuMu instance saved for FOS…",
    "fos_preflight.progress.mumu_wait": "Waiting for MuMu instance {instance} to start Android… {elapsed}/{timeout} seconds",
    "preflight.all_passed": "All checks passed. MAA is ready to run.",
    "preflight.next_step": "Next step",
    "preflight.show_details": "Show details",
    "preflight.hide_details": "Hide details",
    "preflight.retry": "Check again",
    "preflight.edit": "Edit automation",
    "preflight.run": "Run now",
    "preflight.checking": "Checking MAA setup…",
    "preflight.progress_title": "MAA setup check",
    "preflight.progress.program": "Checking the MAA program…",
    "preflight.progress.task": "Checking the selected MAA task…",
    "preflight.progress.managed_task": "Preparing the Control Plane managed MAA task…",
    "preflight.progress.config": "Validating the task configuration safely…",
    "preflight.progress.emulator": "Checking the emulator connection…",
    "preflight.progress.mumu_check": "Checking MuMu instance {instance}…",
    "preflight.progress.mumu_start": "Starting MuMu instance {instance}…",
    "preflight.progress.mumu_wait": "Waiting for MuMu instance {instance} to connect to ADB… {elapsed}/{timeout} seconds",
    "history.title": "Run history · {title}",
    "history.timestamp": "Timestamp",
    "history.state": "State",
    "history.duration": "Duration",
    "history.exit_code": "Exit code",
    "history.error": "Error",
    "history.stdout": "Standard output (stdout)",
    "history.stderr": "Standard error (stderr)",
    "history.no_runs": "No runs recorded for this automation.",
    "history.summary": "Run {run_id} · {state} · Duration: {duration} · Exit: {exit_code}",
    "history.log_missing": "Captured log is not available.",
    "history.log_gone": "Captured log is no longer available.",
    "history.log_tail": "[Showing the last {limit} of this log.]\n{text}",
    "message.save_failed_title": "Could not save automation",
    "message.start_active_title": "Automation is already active",
    "message.start_active_body": "This automation is already running or waiting in the daily queue.",
    "message.start_failed_title": "Could not start automation",
    "message.nothing_title": "Nothing to run",
    "message.nothing_body": "There are no enabled automations waiting for today's completion.",
    "message.preflight_failed_title": "Could not check MAA setup",
    "message.preflight_failed_body": "The setup check did not return a result.",
    "message.fos_preflight_failed_title": "Could not check MAA_Punish setup",
    "message.fos_preflight_failed_body": "The MAA_Punish setup check did not return a result.",
    "message.remove_title": "Remove automation?",
    "message.remove_body": "Remove '{name}' and its stored run history?",
    "message.close_running_title": "Automations are still running",
    "message.close_running_body": "{count} automation(s) are still running. Closing stops tracking them. External processes may continue or terminate. The runs will be marked interrupted on the next launch. Close anyway?",
    "message.app_error_title": "Application error",
    "message.app_error_body": "An unexpected error occurred. Details were written to:\n{path}",
}


_TRANSLATIONS = {"zh_CN": _ZH_CN, "en_US": _EN_US}


class LanguageManager(QObject):
    language_changed = Signal(str)

    def __init__(
        self,
        language: str | None = None,
        *,
        persist: bool = True,
        settings: QSettings | None = None,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self._persist = persist
        self._settings = settings or QSettings(
            "GameAutomationControlPlane", "GameAutomationControlPlane"
        )
        saved = self._settings.value("ui/language", DEFAULT_LANGUAGE, type=str)
        self._language = self._normalized(language or saved)

    @property
    def language(self) -> str:
        return self._language

    def set_language(self, language: str) -> None:
        normalized = self._normalized(language)
        if normalized == self._language:
            return
        self._language = normalized
        if self._persist:
            self._settings.setValue("ui/language", normalized)
            self._settings.sync()
        self.language_changed.emit(normalized)

    def text(self, key: str, **values: object) -> str:
        catalog = _TRANSLATIONS[self._language]
        template = catalog.get(key) or _EN_US.get(key) or key
        try:
            return template.format(**values)
        except (KeyError, ValueError):
            return template

    @staticmethod
    def _normalized(language: str) -> str:
        return language if language in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE


def state_text(manager: LanguageManager, state: str) -> str:
    return manager.text(f"state.{state}")


def game_text(manager: LanguageManager, name: str, runner_type: str) -> str:
    if runner_type == "maa_cli":
        return manager.text("game.arknights")
    if runner_type == "ok_ww":
        return manager.text("game.wuthering")
    if runner_type == "maa_punish":
        return manager.text("game.punishing")
    return name


def preflight_progress_text(manager: LanguageManager, message: str) -> str:
    exact = {
        "Checking the MAA program…": "preflight.progress.program",
        "Preparing the Control Plane MAA task…": "preflight.progress.managed_task",
        "Checking the selected MAA task…": "preflight.progress.task",
        "Validating the task configuration safely…": "preflight.progress.config",
        "Checking the emulator connection…": "preflight.progress.emulator",
    }
    if message in exact:
        return manager.text(exact[message])
    patterns = (
        (r"^Checking MuMu instance (?P<instance>\d+)…$", "preflight.progress.mumu_check"),
        (r"^Starting MuMu instance (?P<instance>\d+)…$", "preflight.progress.mumu_start"),
        (
            r"^Waiting for MuMu instance (?P<instance>\d+) to connect to ADB… "
            r"(?P<elapsed>\d+)/(?P<timeout>\d+) seconds$",
            "preflight.progress.mumu_wait",
        ),
    )
    for pattern, key in patterns:
        match = re.match(pattern, message)
        if match:
            return manager.text(key, **match.groupdict())
    return message


def fos_preflight_progress_text(manager: LanguageManager, message: str) -> str:
    exact = {
        "Checking the FOS program…": "fos_preflight.progress.program",
        "Reading the selected FOS configuration…": "fos_preflight.progress.config",
        "Checking the MuMu instance saved for FOS…": "fos_preflight.progress.emulator",
    }
    if message in exact:
        return manager.text(exact[message])
    match = re.match(
        r"^Waiting for MuMu instance (?P<instance>\d+) to start Android… "
        r"(?P<elapsed>\d+)/(?P<timeout>\d+) seconds$",
        message,
    )
    if match:
        return manager.text("fos_preflight.progress.mumu_wait", **match.groupdict())
    start = re.match(r"^Starting MuMu instance (?P<instance>\d+)…$", message)
    if start:
        return manager.text("preflight.progress.mumu_start", **start.groupdict())
    return message


__all__ = [
    "DEFAULT_LANGUAGE",
    "LanguageManager",
    "SUPPORTED_LANGUAGES",
    "game_text",
    "fos_preflight_progress_text",
    "preflight_progress_text",
    "state_text",
]
