# Mobile Game Daily Task Control Panel

[简体中文首页](README.md) | **English**

[![Latest release](https://img.shields.io/github/v/release/wiwiwcwc/game-automation-control-plane?display_name=tag&sort=semver)](https://github.com/wiwiwcwc/game-automation-control-plane/releases)
[![Windows package proof](https://github.com/wiwiwcwc/game-automation-control-plane/actions/workflows/windows-package.yml/badge.svg?branch=main)](https://github.com/wiwiwcwc/game-automation-control-plane/actions/workflows/windows-package.yml)
[![AGPL-3.0-only](https://img.shields.io/github/license/wiwiwcwc/game-automation-control-plane)](LICENSE)
[![Python 3.11](https://img.shields.io/badge/python-3.11-3776AB?logo=python&logoColor=white)](pyproject.toml)
[![Windows](https://img.shields.io/badge/platform-Windows-0078D6?logo=windows&logoColor=white)](README.en.md)

<img src="src/game_control_plane/assets/app_icon.png" alt="Mobile game daily task control panel icon" width="128">

> A Windows desktop console for running and recording mobile-game daily tasks in one place.

It connects existing tools such as **MAA / maa-cli (Arknights)**, **MAA_Punish / FOS (Punishing: Gray Raven)**, and **OK-WW (Wuthering Waves)** to one task list. It currently covers only these implemented integrations: it is not a generic game bot and does not claim to support every game.

`v0.1.14` was released on 2026-08-28. This is an early-stage Windows-first PySide6 application for users who want a simpler way to run and review mobile-game daily scripts, and for developers building explicit launchers around existing tools.

The current source version is `0.1.15`. For the classic OneDragon Full-Environment package, select the complete directory containing `OneDragon-Launcher.exe`, `config/project.yml`, and `config/repository.yml`; the complete `resources/config/*.yml` compatibility layout is also accepted. Do not move YAML files.

## What it is useful for

- Store a per-game task with an explicit executable, argument list, and working directory.
- Run the supported MAA, MAA_Punish/FOS, and OK-WW preflight checks before launching a task.
- Keep status, exit code, duration, stdout/stderr, and SQLite run history in one place.
- Run today's queue in order while unrelated manual jobs can continue; the same job or MuMu instance is not claimed twice.

## Current integrations

| Tool / integration | Mobile game | Current scope |
| --- | --- | --- |
| MAA / `maa-cli` | Arknights | Version/task/dry-run/ADB preflight, managed daily tasks, and ownership-aware MuMu monitoring |
| MAA_Punish / FOS | Punishing: Gray Raven | Saved-config discovery, task-flow monitoring, and exact-path FOS/MuMu handling |
| OK-WW | Wuthering Waves | Positive task index, `-t <index>`, optional `-e`, and constrained worker handoff monitoring |
| Zenless Zone Zero OneDragon | Zenless Zone Zero | Connects an installed RuntimeLauncher (preferred) or classic launcher, with explicit one-dragon, instance, and optional `-c` arguments |
| Custom CLI | Other external scripts | Explicit interpreter/executable, arguments, working directory, output, and history |

The ZZZ adapter connects only to a launcher the user has already installed; it does not download or bundle OneDragon, its runtime, models, or game files. It is not a generic OneDragon adapter and does not imply support for other games. See [integration status](docs/integrations.md) before treating a behavior as verified.

## Quick start

1. Download `GameAutomationControlPlane-windows.zip` and its `.sha256` file from the [v0.1.14 Release](https://github.com/wiwiwcwc/game-automation-control-plane/releases/tag/v0.1.14).
2. Compare the ZIP with its checksum in PowerShell:

   ```powershell
   Get-FileHash .\GameAutomationControlPlane-windows.zip -Algorithm SHA256
   Get-Content .\GameAutomationControlPlane-windows.zip.sha256
   ```

3. Extract the complete ZIP and run `GameAutomationControlPlane.exe`. Keep the `_internal` directory beside the executable.

> **Security note:** The Windows build is unsigned and may show UAC or SmartScreen prompts. Verify the download before running it and do not disable Windows Defender or other security software. Automation may also be restricted by a game's terms; use it at your own risk.

Application data is stored under `%LOCALAPPDATA%\GameAutomationControlPlane\` by default. Set `GAME_CONTROL_PLANE_DATA_DIR` for an isolated development or test directory.

## Advanced details

<details>
<summary>Verification boundaries and configuration notes</summary>

- MAA/maa-cli preflight, configuration contracts, and result auditing have local test coverage; a complete live MAA daily run is not claimed as verified here.
- MAA_Punish/FOS saved-config discovery, task-flow monitoring, exact-path process handling, and MuMu ownership have contract coverage; this project does not replace or bundle FOS.
- OK-WW task arguments and worker handoff are covered locally; the complete behavior of a user's installed version still needs validation in that environment.
- OneDragon launcher discovery, Runtime/classic layout checks, `-o`/`-i`/`-c` construction, and failure paths are covered locally; installed-version differences, account existence, the live game flow, and an upstream completion signal remain unverified. A normal OneDragon exit is shown as needs attention and never marks today's completion automatically.
- Execution success is separate from marking a daily complete. The queue is an in-memory snapshot; scheduling, plugins, persisted queue recovery, process-tree cancellation, automatic verification, and automatic completion are outside this release.
- See [integration status](docs/integrations.md) and [architecture](docs/architecture.md) for detailed contracts and lifecycle behavior.

</details>

## Development and agents

Use Windows + Python 3.11 for the supported development path:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[test]"
$env:QT_QPA_PLATFORM = "offscreen"
python -m pytest
python -m compileall -q src tests packaging
python -m game_control_plane
```

Read [`AGENTS.md`](AGENTS.md) before changing code. It is the shared guide for Codex, Claude Code, Copilot, and other coding agents. See [`CONTRIBUTING.md`](CONTRIBUTING.md) and [`SECURITY.md`](SECURITY.md) before opening a change.

<details>
<summary>License and external projects</summary>

The source code and original project artwork are licensed under [AGPL-3.0-only](LICENSE). MAA, MaaFramework, MAA_Punish/FOS, OK-WW, MuMu, and the referenced games belong to their respective owners. They are not bundled with this repository or its Windows ZIP, and this project is not affiliated with or endorsed by their maintainers or publishers. Qt/PySide6 notices are in [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).

</details>
