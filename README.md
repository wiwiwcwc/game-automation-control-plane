# 休汐 Hsiesta

> 让手游日常自动运行，留一点时间给自己。

[English](README.en.md) | **简体中文**

[![Latest release](https://img.shields.io/github/v/release/wiwiwcwc/hsiesta?display_name=tag&sort=semver)](https://github.com/wiwiwcwc/hsiesta/releases)
[![Windows package proof](https://github.com/wiwiwcwc/hsiesta/actions/workflows/windows-package.yml/badge.svg?branch=main)](https://github.com/wiwiwcwc/hsiesta/actions/workflows/windows-package.yml)
[![AGPL-3.0-only](https://img.shields.io/github/license/wiwiwcwc/hsiesta)](LICENSE)
[![Windows](https://img.shields.io/badge/platform-Windows-0078D6?logo=windows&logoColor=white)](README.md)

<img src="src/game_control_plane/assets/app_icon.png" alt="休汐 Hsiesta 图标" width="128">
<!-- 我老婆 -->

休汐（Hsiesta）是一款面向 Windows 的手游日常控制台：把已经安装好的 MAA / maa-cli、MAA_Punish / FOS、OK-WW 和 OneDragon 等工具集中到一张任务清单里，统一启动、查看状态和回看日志。

目前支持的工具仍在持续扩展；后续会在确认每个项目的启动、监控与完成判定方式后，逐步接入更多手游日常工具。

休汐只负责编排外部工具，不是游戏客户端、图像识别引擎或通用机器人。它不会下载或捆绑第三方工具；进程正常退出，也不等于日常已经完成。

当前源码版本为 `0.1.17`，具体支持范围和验证边界以项目文档为准。

## Windows 下载

前往 [Releases](https://github.com/wiwiwcwc/hsiesta/releases)，下载对应版本的 Windows ZIP 和同名 `.sha256` 校验文件。当前包内的目录、EXE 和 ZIP 文件名仍保留 `GameAutomationControlPlane`，这是为了兼容已有安装和数据，不影响应用显示品牌。

1. 在 PowerShell 中核对 SHA-256：

   ```powershell
   Get-FileHash .\GameAutomationControlPlane-windows.zip -Algorithm SHA256
   Get-Content .\GameAutomationControlPlane-windows.zip.sha256
   ```

2. 完整解压 ZIP 后运行 `GameAutomationControlPlane.exe`，不要单独复制 EXE；旁边的 `_internal` 目录是必需的。

> **安全提醒：** Windows 构建未签名，首次运行可能出现 UAC 或 SmartScreen 提示。请先确认下载来源和校验值，不要为了运行而关闭 Windows Defender。自动化行为也可能受到游戏发行商或平台条款限制，请自行确认并承担相应风险。

程序数据默认位于 `%LOCALAPPDATA%\GameAutomationControlPlane\`；本次品牌更名无需移动或重建已有数据，后续启动仍可能按内置迁移更新数据库 schema。开发和测试可以设置 `GAME_CONTROL_PLANE_DATA_DIR` 使用临时目录。

## 它能帮你做什么

- 按游戏整理日常任务：每个任务都能保存明确的可执行文件、参数和工作目录。
- 启动前把配置检查一遍：减少“进程退出了，但日常其实没做完”的误判。
- 给每次运行留记录：状态、退出码、耗时、标准输出、错误输出和 SQLite 历史都能回看。
- 让今天的任务按顺序执行：不相关的手动任务仍可并行，同一个任务或 MuMu 实例不会被重复占用。
- 把执行和确认分开：程序不会擅自把一次运行结果写成“今日已完成”，需要时由你手动确认。

## 已适配工具

| 工具 / 集成 | 对应游戏 | 目前覆盖的范围 |
| --- | --- | --- |
| MAA / `maa-cli` | 明日方舟 / Arknights | 版本、任务、dry-run、ADB 预检；受控每日任务；按所有权启动和监控 MuMu |
| MAA_Punish / FOS | 战双帕弥什 / Punishing: Gray Raven | 读取已保存配置、跟踪任务流，并按精确路径处理 FOS 和 MuMu |
| OK-WW | 鸣潮 / Wuthering Waves | 任务序号、`-t <index>`、可选 `-e`，以及受限的 worker 交接监控 |
| 绝区零 OneDragon | 绝区零 / Zenless Zone Zero | 连接已安装的 RuntimeLauncher 或经典 Launcher，显式调用一条龙入口；可选账号实例和 `-c` |
| Custom CLI | 其他外部脚本 | 明确的解释器 / 可执行文件、逐项参数、工作目录、输出和历史 |

OneDragon 目前支持绝区零版本，使用前需要先安装并配置对应的 OneDragon。

<details>
<summary>验证边界与常见问题</summary>

### 这是通用游戏机器人吗？

不是。休汐只调度已经安装的外部工具，不实现图像识别、游戏操作或通用脚本兼容。其他游戏也不会因为出现在搜索关键词里就自动获得支持。

### 为什么退出码为 0 还可能显示“需要检查”？

退出码只说明外部进程正常结束，不等于游戏日常已经完成。MAA 需要完整的任务摘要和至少一局真实战斗；OneDragon 没有本项目可以信任的外部完成信号，正常退出后仍需查看日志并手动确认。

### 各适配器已经验证到什么程度？

- MAA / `maa-cli`：预检、配置合约、受控任务生成和结果审计有本地测试；完整真实日常尚未在本项目中端到端验证。
- MAA_Punish / FOS：保存配置读取、任务流监控、精确路径进程处理和 MuMu 所有权有合约测试；本项目不替代或捆绑 FOS。
- OK-WW：任务参数和 worker 交接有本地覆盖；当前安装版本的完整游戏流程和进程结束行为仍需在目标环境验证。
- OneDragon：启动器发现、Runtime / 经典目录预检、`-o` / `-i` / `-c` 参数和失败路径有本地覆盖；启动器版本、账号是否存在和真实游戏流程仍需用户自行确认。

### OneDragon 目录应该怎么选？

使用经典 OneDragon Full-Environment 布局时，请选择同时包含 `OneDragon-Launcher.exe`、`config/project.yml` 和 `config/repository.yml` 的完整目录；兼容布局则需要完整的 `resources/config/*.yml`。不要移动 YAML 文件。

### 遇到启动失败先看什么？

先打开任务的运行日志，确认可执行文件路径、工作目录和参数是否对应已经安装的外部工具。预检失败时，按向导中的第一个失败步骤处理；不要把完整 Shell 命令粘进参数框，也不要移动 OneDragon 的 YAML 文件。

更多参数和失败路径见 [`docs/integrations.md`](docs/integrations.md)，生命周期、SQLite、队列和 MuMu 所有权见 [`docs/architecture.md`](docs/architecture.md)。

</details>

<details>
<summary>从源码运行与开发测试</summary>

支持的开发路径是 Windows + Python 3.11：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[test]"
$env:QT_QPA_PLATFORM = "offscreen"
python -m pytest
python -m compileall -q src tests packaging
python -m game_control_plane
```

打包命令和 CI 证明见 [`AGENTS.md`](AGENTS.md) 与 [`windows-package.yml`](.github/workflows/windows-package.yml)。提交贡献前请阅读 [`CONTRIBUTING.md`](CONTRIBUTING.md) 和 [`SECURITY.md`](SECURITY.md)。

</details>

<details>
<summary>许可证与免责声明</summary>

项目源码和项目所有者原创手绘图标采用 [AGPL-3.0-only](LICENSE)。MAA、MaaFramework、MAA_Punish / FOS、OK-WW、MuMu 及相关游戏属于各自权利人，本项目不隶属、不代表认可，也不会把这些第三方工具随仓库或 Windows ZIP 捆绑发布。Qt / PySide6 的许可材料见 [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)。

自动化行为可能受到游戏发行商、平台或服务条款限制；使用者应自行确认适用规则，并承担账号、数据和系统风险。项目不保证任何第三方工具、游戏版本、账号状态或运行环境一定可用。

</details>
