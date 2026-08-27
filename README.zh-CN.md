# 游戏自动化控制台

**简体中文** | [English](README.md)

<img src="src/game_control_plane/assets/app_icon.png" alt="游戏自动化控制台图标" width="128">

Game Automation Control Plane 是一个 Windows 优先的桌面控制台，用于统一管理多个游戏自动化工具。它不会重新实现游戏操作，而是负责启动外部工具、记录运行状态、保存日志并组织每日任务。

当前版本为尚未正式发布的 `0.1.13`。项目源码及项目所有者原创手绘的图标均采用 [GNU Affero 通用公共许可证第 3 版（仅此版本）](LICENSE)授权。

## 当前支持

- **MAA / maa-cli（明日方舟）**：运行前检查任务和 ADB，可生成受控的每日任务，并可按实例启动、监控和关闭 MuMu。
- **MAA_Punish / FOS（战双帕弥什）**：读取 FOS 配置、跟踪真实任务流程，可选择在成功后关闭对应 FOS 和由本程序启动的模拟器实例。
- **OK-WW（鸣潮）**：按任务序号启动，并可选择任务完成后关闭游戏。
- **Custom CLI**：使用明确的可执行文件、参数和工作目录运行其他自动化脚本。
- 默认简体中文界面，可在 **设置 → 语言** 切换英文。
- 每个任务独立记录运行状态、退出码、耗时、标准输出和错误输出。
- “执行成功”和“今日已完成”分开记录，避免仅凭退出码误判游戏日常已经完成。

详细的能力边界请参阅[集成状态](docs/integrations.md)和[架构说明](docs/architecture.md)。

## 获取和运行

GitHub Actions 会在 Windows 上运行测试、构建目录版程序，并上传 ZIP 和对应的 SHA-256 校验文件。下载后请完整解压目录，再运行 `GameAutomationControlPlane.exe`；不要只复制 EXE，程序还需要旁边的 `_internal` 目录。

当前 Windows 构建未进行代码签名，因此系统可能显示 UAC 或 SmartScreen 提示。请使用同一次 Actions 构建提供的 SHA-256 文件核对下载内容，不要为了运行程序而关闭 Windows Defender。

程序数据默认保存在：

```text
%LOCALAPPDATA%\GameAutomationControlPlane\
├── control_plane.sqlite3
├── logs\app.log
└── runs\<run-id>\
```

## 从源码开发

支持的开发与打包环境为 Windows 和 Python 3.11：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[test,build]" -c packaging\constraints.txt
$env:QT_QPA_PLATFORM = "offscreen"
python -m pytest
python -m game_control_plane
```

构建 Windows 目录版：

```powershell
.\packaging\build_windows.ps1 -PythonExecutable python
.\packaging\smoke_test.ps1 -ExecutablePath .\dist\GameAutomationControlPlane\GameAutomationControlPlane.exe
```

贡献前请阅读[贡献指南](CONTRIBUTING.md)和[安全策略](SECURITY.md)。首次建库可按 [GitHub 发布指南](docs/github-publishing.md)操作。变更历史见 [CHANGELOG.md](CHANGELOG.md)，Qt/PySide6 的随包许可材料见[第三方声明](THIRD_PARTY_NOTICES.md)，图标权利说明见[项目美术资源](ASSETS.md)。

## 第三方项目说明

MAA、MAA_Punish/FOS、OK-WW、MuMu 及文中涉及的游戏均为外部项目或产品，本仓库不捆绑它们，也不代表得到其维护者或发行商的认可。相关名称、商标、代码和许可证归各自权利人所有。
