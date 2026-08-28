# 手游日常任务控制台 | Game Automation Control Plane

[English](README.en.md) | **简体中文**

[![Latest release](https://img.shields.io/github/v/release/wiwiwcwc/game-automation-control-plane?display_name=tag&sort=semver)](https://github.com/wiwiwcwc/game-automation-control-plane/releases)
[![Windows package proof](https://github.com/wiwiwcwc/game-automation-control-plane/actions/workflows/windows-package.yml/badge.svg?branch=main)](https://github.com/wiwiwcwc/game-automation-control-plane/actions/workflows/windows-package.yml)
[![AGPL-3.0-only](https://img.shields.io/github/license/wiwiwcwc/game-automation-control-plane)](LICENSE)
[![Python 3.11](https://img.shields.io/badge/python-3.11-3776AB?logo=python&logoColor=white)](pyproject.toml)
[![Windows](https://img.shields.io/badge/platform-Windows-0078D6?logo=windows&logoColor=white)](README.md)

<img src="src/game_control_plane/assets/app_icon.png" alt="手游日常任务控制台图标" width="128">
<!-- 我老婆 -->

> 一个用于集中运行和记录手游日常任务的 Windows 桌面控制台。

它把 **MAA / maa-cli（明日方舟）**、**MAA_Punish / FOS（战双帕弥什）**、**OK-WW（鸣潮）** 等现有工具接到同一个任务列表里，统一管理启动参数、运行状态和日志。目前只接入这些已经做过适配的工具；它不是通用游戏机器人，也不承诺支持所有游戏。

`v0.1.14` 已于 2026-08-28 发布。项目仍处于早期阶段，适合希望少开几个窗口、集中管理手游日常脚本，或想在 Windows 上开发外部工具编排器的用户。

当前源码版本为 `0.1.15`。经典 OneDragon Full-Environment 请直接选择包含 `OneDragon-Launcher.exe`、`config/project.yml` 和 `config/repository.yml` 的完整目录；兼容的 `resources/config/*.yml` 布局也可用，不要移动 YAML 文件。

## 你会得到什么

- 按游戏保存任务：可编辑可执行文件、参数和工作目录，适合 Custom CLI 及已支持的自动化工具。
- 启动前先检查：对 MAA、MAA_Punish/FOS 和 OK-WW 执行各自的配置/任务预检，减少“进程退出了但日常没做完”的误判。
- 运行记录可回看：保存状态、退出码、耗时、标准输出/错误输出和 SQLite 历史。
- 队列更可控：今日任务按顺序运行；不相关的手动任务可以并行，同一任务或同一 MuMu 实例不会重复占用。

## 当前支持

| 工具/集成 | 手游日常 | 目前能做什么 |
| --- | --- | --- |
| MAA / `maa-cli` | 明日方舟 / Arknights | 版本、任务、dry-run、ADB 预检；受控每日任务；按所有权启动/监控 MuMu |
| MAA_Punish / FOS | 战双帕弥什 / Punishing: Gray Raven | 读取保存配置、跟踪任务流、按精确路径处理 FOS 和 MuMu |
| OK-WW | 鸣潮 / Wuthering Waves | 任务序号、`-t <index>`、可选 `-e` 和受限的 worker 交接监控 |
| 绝区零 OneDragon | 绝区零 / Zenless Zone Zero | 连接已安装的 RuntimeLauncher（优先）或经典 Launcher，显式运行一条龙；可选账号实例和 `-c` |
| Custom CLI | 其他外部脚本 | 明确的解释器/可执行文件、逐项参数、工作目录、输出和历史 |

绝区零 OneDragon 适配器只连接用户已经安装的启动器，不下载或捆绑 OneDragon、运行时、模型或游戏文件；它不是通用 OneDragon 适配器，也不承诺支持其他游戏。其他游戏也不会因为出现在搜索关键词里就自动获得支持。需要接入新工具时，请先看[集成状态](docs/integrations.md)和根目录 [`AGENTS.md`](AGENTS.md)。

## 快速开始

1. 从 [v0.1.14 Release](https://github.com/wiwiwcwc/game-automation-control-plane/releases/tag/v0.1.14) 下载 `GameAutomationControlPlane-windows.zip` 和同名 `.sha256` 文件。
2. 在 PowerShell 中核对 SHA-256：

   ```powershell
   Get-FileHash .\GameAutomationControlPlane-windows.zip -Algorithm SHA256
   Get-Content .\GameAutomationControlPlane-windows.zip.sha256
   ```

3. 完整解压 ZIP 后运行 `GameAutomationControlPlane.exe`，不要单独复制 EXE；旁边的 `_internal` 目录是必需的。

> **安全提醒：** Windows 构建未签名，首次运行可能出现 UAC 或 SmartScreen 提示。请先确认下载来源和校验值，不要为了运行而关闭 Windows Defender 或其他安全软件。自动化行为也可能受到游戏发行商或平台条款限制，请自行承担账号和系统风险。

程序数据默认位于 `%LOCALAPPDATA%\GameAutomationControlPlane\`；开发和测试可设置 `GAME_CONTROL_PLANE_DATA_DIR` 使用临时目录。

## 进阶信息

<details>
<summary>验证边界、配置细节与已知限制</summary>

- MAA/maa-cli 的预检、配置合约和结果审计有本地测试，但完整真实 MAA 每日任务尚未在本项目中端到端验证。
- MAA_Punish/FOS 的保存配置读取、任务流监控、精确路径进程处理和 MuMu 所有权有合约测试；本项目不替代或捆绑 FOS。
- OK-WW 的任务序号、`-t <index>`、可选 `-e` 和 worker 交接有本地覆盖；当前安装版本的完整游戏流程及进程结束行为仍需在目标环境验证。
- 绝区零 OneDragon 的启动器发现、Runtime/经典目录预检、`-o`/`-i`/`-c` 参数和失败路径有本地覆盖；启动器版本差异、账号是否存在、真实游戏日常流程及上游完成信号仍未在本项目中实机验证。OneDragon 正常退出也只会进入“需要检查”，不会自动标记今日完成。
- 执行成功与“今日已完成”是两件事；队列是内存快照，不提供调度器、插件系统、队列持久化、进程树取消、自动验证或自动标记完成。
- 详细参数和失败路径见 [`docs/integrations.md`](docs/integrations.md)；生命周期、SQLite、并发和 MuMu 所有权见 [`docs/architecture.md`](docs/architecture.md)。

</details>

## 从源码开发

Windows + Python 3.11：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[test]"
$env:QT_QPA_PLATFORM = "offscreen"
python -m pytest
python -m compileall -q src tests packaging
python -m game_control_plane
```

打包命令和 CI 证明见 [`AGENTS.md`](AGENTS.md) 与 [`windows-package.yml`](.github/workflows/windows-package.yml)。

## 文档与贡献

- [集成状态](docs/integrations.md) · [架构说明](docs/architecture.md)
- [AGENTS.md：Codex / Claude / Copilot 开发入口](AGENTS.md) · [Copilot instructions](.github/copilot-instructions.md)
- [贡献指南](CONTRIBUTING.md) · [安全策略](SECURITY.md)
- [第三方声明与 Qt/PySide6 许可证](THIRD_PARTY_NOTICES.md) · [项目许可证](LICENSE)

欢迎提交测试、文档和小而可验证的适配改进。请不要提交真实账号配置、令牌、个人路径、数据库或运行日志；新集成要说明上游项目、版本、启动合约、失败证据和未验证范围。

<details>
<summary>许可证与第三方项目说明</summary>

项目源码和项目所有者原创手绘图标采用 [AGPL-3.0-only](LICENSE)。MAA、MaaFramework、MAA_Punish/FOS、OK-WW、MuMu 及相关游戏属于各自权利人，本项目不隶属、不代表认可，也不会把这些第三方工具随仓库或 Windows ZIP 捆绑发布。Qt/PySide6 的许可材料见 [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)。

</details>
