# 游戏自动化控制台 | Game Automation Control Plane

[English](README.en.md) | **简体中文**

[![Latest release](https://img.shields.io/github/v/release/wiwiwcwc/game-automation-control-plane?display_name=tag&sort=semver)](https://github.com/wiwiwcwc/game-automation-control-plane/releases)
[![Windows package proof](https://github.com/wiwiwcwc/game-automation-control-plane/actions/workflows/windows-package.yml/badge.svg?branch=main)](https://github.com/wiwiwcwc/game-automation-control-plane/actions/workflows/windows-package.yml)
[![AGPL-3.0-only](https://img.shields.io/github/license/wiwiwcwc/game-automation-control-plane)](LICENSE)
[![Python 3.11](https://img.shields.io/badge/python-3.11-3776AB?logo=python&logoColor=white)](pyproject.toml)
[![Windows](https://img.shields.io/badge/platform-Windows-0078D6?logo=windows&logoColor=white)](README.md)

<img src="src/game_control_plane/assets/app_icon.png" alt="游戏自动化控制台项目图标" width="128">

> 面向 Windows 的多游戏自动化控制平面：把 MAA/maa-cli、MAA_Punish/FOS、OK-WW 和其他 Custom CLI 任务集中管理、启动、观察并记录。

`v0.1.13` 于 2026-08-27 发布。这是一个仍在早期阶段的、以 Windows 为优先的 PySide6 桌面应用；它负责编排外部自动化工具，不重新实现图像识别或游戏操作，也不捆绑任何第三方游戏工具。

## 为什么使用

Game Automation Control Plane 适合希望在一个轻量控制台里管理多个游戏自动化任务的用户和开发者：

- 按游戏组织 Custom CLI、MAA/maa-cli、MAA_Punish/FOS 和 OK-WW 任务，保存明确的可执行文件、参数和工作目录。
- 对受支持的 MAA、MAA_Punish/FOS 和 OK-WW 合约做启动前检查，避免只凭进程退出码把不完整的任务误判为成功。
- 记录每次运行的状态、退出码、耗时、标准输出/错误输出和 SQLite 历史，方便回看失败原因。
- 今日队列按用户保存的顺序逐项运行；不相关的手动任务可以并行，但同一个任务或同一个关联 MuMu 实例不会被重复占用。
- 对由控制台启动的 MuMu 实例采用运行级所有权：已经在运行的实例不会被控制台擅自关闭。

## 当前成熟度与边界

这是 `0.1.x` 早期发布版本。当前发布流水线已在 Windows 上运行完整测试、PyInstaller 目录版打包、包内容检查、冒烟启动、ZIP 和 SHA-256 生成；这些是工程化证据，不等同于所有游戏环境都已完成实机验证。

- MAA/maa-cli 的执行前检查、配置合约和结果审计已有本地测试；完整的真实 MAA 每日任务仍未在本项目中端到端验证。
- OK-WW 的任务序号、`-t <index>`、可选 `-e` 和启动器向同目录 Python worker 的交接合约有本地覆盖；当前用户安装版本的完整游戏流程和进程结束行为仍需在目标环境验证。
- MAA_Punish/FOS 的保存配置读取、任务流监控、精确路径进程关闭和 MuMu 所有权逻辑已有合约测试；不宣称替代上游 FOS 或保证每个账号环境成功。
- 本版本没有内置 OneDragon 适配器，也没有调度器、插件系统、队列持久化/重启恢复、进程树取消、自动验证或自动标记每日完成。
- Windows 构建未进行代码签名，首次运行可能出现 UAC 或 SmartScreen 提示。请核对同一次构建的 SHA-256，不要为了运行而关闭 Windows Defender 或其他安全软件。

## 支持矩阵

| 集成 | 游戏/用途 | 控制台负责的能力 | 当前证据边界 |
| --- | --- | --- | --- |
| Custom CLI | 任意外部自动化脚本 | 明确的绝对可执行文件/解释器、逐项参数、工作目录、输出捕获和运行历史 | 本地测试覆盖；脚本本身由用户负责 |
| MAA / `maa-cli` | 明日方舟 / Arknights | 版本、任务名、dry-run、ADB 预检；可生成受控每日任务；可按所有权启动、监控和关闭 MuMu | 合约与测试覆盖；完整实机每日流程未验证 |
| MAA_Punish / FOS | 战双帕弥什 / Punishing: Gray Raven | 读取 FOS 保存配置，跟踪真实任务流，按精确路径处理 FOS，并支持所有权范围内的 MuMu 清理 | 合约与测试覆盖；不替代或捆绑 FOS |
| OK-WW | 鸣潮 / Wuthering Waves | 正整数任务序号、`-t <index>`，可选 `-e`，以及受限的 worker 交接监控 | 合约与测试覆盖；当前安装版本的完整行为未验证 |
| OneDragon | 未内置适配 | 可通过 Custom CLI 以显式参数调用外部程序 | 没有内置 OneDragon 集成 |

MAA、MaaFramework、MAA_Punish/FOS、OK-WW、MuMu 和相关游戏均是外部项目或产品。它们的名称、商标、代码、服务条款和许可证归各自权利人所有；本项目不代表得到其维护者或发行商认可。

## 快速开始：下载 Windows 版本

1. 打开 [v0.1.13 Release](https://github.com/wiwiwcwc/game-automation-control-plane/releases/tag/v0.1.13)，同时下载 `GameAutomationControlPlane-windows.zip` 和 `GameAutomationControlPlane-windows.zip.sha256`。
2. 使用同一次 Release 提供的校验文件验证 ZIP。PowerShell 示例：

   ```powershell
   Get-FileHash .\GameAutomationControlPlane-windows.zip -Algorithm SHA256
   Get-Content .\GameAutomationControlPlane-windows.zip.sha256
   ```

3. 完整解压 ZIP 目录，运行 `GameAutomationControlPlane.exe`。不要把 EXE 单独复制出来；它需要旁边的 `_internal` 目录。
4. 首次启动可能显示标准 UAC 确认和 SmartScreen 提示。确认下载来源和校验值后再决定是否运行。

程序默认把数据保存在 `%LOCALAPPDATA%\GameAutomationControlPlane\`：

```text
control_plane.sqlite3
logs\app.log
runs\<run-id>\
    stdout.log
    stderr.log
    metadata.json
```

`%LOCALAPPDATA%` 不可用时会回退到 `%APPDATA%`。开发和测试可设置 `GAME_CONTROL_PLANE_DATA_DIR` 指向明确的临时目录。

## 从源码运行

支持的开发和打包路径是 Windows + Python 3.11。测试使用安全的 fixture CLI，不要求安装游戏客户端或模拟器。

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[test]"
$env:QT_QPA_PLATFORM = "offscreen"
python -m pytest
python -m compileall -q src tests packaging
python -m game_control_plane
```

如需本地构建 Windows 目录版：

```powershell
python -m pip install -e ".[test,build]" -c packaging\constraints.txt
.\packaging\build_windows.ps1 -PythonExecutable python
.\packaging\smoke_test.ps1 -ExecutablePath .\dist\GameAutomationControlPlane\GameAutomationControlPlane.exe
```

完整的 CI 证明见 [`windows-package.yml`](.github/workflows/windows-package.yml)。

## 开发者与 AI/Coding Agent 入口

开始修改前请先阅读根目录 [`AGENTS.md`](AGENTS.md)。它记录目录结构、受保护的不变量、集成适配步骤、模拟器所有权、并发和每日完成语义，以及开发/测试/打包命令。GitHub Copilot 的简要入口在 [`copilot-instructions.md`](.github/copilot-instructions.md)。

推荐的阅读顺序：

1. [集成状态](docs/integrations.md)：区分本地验证、上游文档和未验证边界。
2. [架构说明](docs/architecture.md)：了解 PySide6 UI、QProcess、SQLite、队列和生命周期。
3. [贡献指南](CONTRIBUTING.md)：运行测试并遵守变更范围、许可证和文档要求。
4. [安全策略](SECURITY.md)：不要在 issue 或日志中公开令牌、账号数据、真实路径或完整敏感日志。

## 文档导航

- [English README](README.en.md)
- [集成状态](docs/integrations.md)
- [架构说明](docs/architecture.md)
- [贡献指南](CONTRIBUTING.md)
- [安全策略](SECURITY.md)
- [变更记录](CHANGELOG.md)
- [第三方声明与 Qt/PySide6 许可证](THIRD_PARTY_NOTICES.md)
- [项目图标与原创美术说明](ASSETS.md)
- [GitHub 发布指南](docs/github-publishing.md)
- [AGPL-3.0-only 项目许可证](LICENSE)

## 路线图

路线图只记录有证据支撑的下一步，不把愿望写成现有能力：

- 在隔离的真实环境补充 MAA 每日任务的端到端验证记录。
- 在代表性的当前 OK-WW 安装上补充 worker 交接、任务完成和关闭行为证据。
- 评估安装器、更新器和代码签名；在证据和维护能力不足时保持 ZIP 分发。
- 根据实际需求重新评估调度、队列持久化、取消和更多外部工具适配，而不是默认引入复杂度。

## 贡献与问题反馈

欢迎提交小而可验证的修复、测试、文档和适配改进。请在 PR 或 issue 中说明：目标上游版本、Windows/Python 环境、复现步骤、预期行为和已验证范围。涉及游戏账号、令牌、个人路径或运行日志时，请先做脱敏；不要把真实配置或数据库提交到仓库。

新的集成应先确认上游接口和本地版本，再实现发现、预检、启动、结果证据、失败路径、清理和测试；请保持“执行成功”与“今日已完成”分离。

## 免责声明与许可证

本项目是用于组织外部自动化任务的开源 Windows 桌面工具，不保证任何第三方工具、游戏版本、账号状态或运行环境的可用性。自动化行为可能受到游戏发行商、平台或服务条款限制；使用者应自行确认适用规则并承担账号、数据和系统风险。

本项目源码和项目所有者原创手绘图标采用 [GNU Affero General Public License v3.0 only](LICENSE)。PySide6/Qt 等第三方材料及其许可证见 [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)；第三方工具不会随本仓库或 Windows ZIP 捆绑发布。
