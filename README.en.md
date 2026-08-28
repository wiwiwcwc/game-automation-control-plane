# Hsiesta

> Let your mobile-game dailies run, and keep a little time for yourself.

[简体中文](README.md) | **English**

[![Latest release](https://img.shields.io/github/v/release/wiwiwcwc/hsiesta?display_name=tag&sort=semver)](https://github.com/wiwiwcwc/hsiesta/releases)
[![Windows package proof](https://github.com/wiwiwcwc/hsiesta/actions/workflows/windows-package.yml/badge.svg?branch=main)](https://github.com/wiwiwcwc/hsiesta/actions/workflows/windows-package.yml)
[![AGPL-3.0-only](https://img.shields.io/github/license/wiwiwcwc/hsiesta)](LICENSE)
[![Windows](https://img.shields.io/badge/platform-Windows-0078D6?logo=windows&logoColor=white)](README.en.md)

<img src="src/game_control_plane/assets/app_icon.png" alt="Hsiesta icon" width="128">

Hsiesta is a Windows desktop console that brings the mobile-game tools you already have installed into one task list, then starts them, tracks their status, and keeps their logs in one place.

Support will expand gradually as each tool's launch, monitoring, and completion behavior is understood and tested.

It only orchestrates external tools. It is not a game client, image-recognition engine, or general-purpose bot. It does not download or bundle third-party tools; a normal process exit is not proof that a daily task finished.

The current source version is `0.1.18`.

## Windows download

### One-click installation (recommended)

Open [GitHub Releases](https://github.com/wiwiwcwc/hsiesta/releases), download
`Hsiesta-0.1.18-Setup.exe`, double-click it, and follow the wizard. The installer
defaults to the current user's `%LOCALAPPDATA%\Programs\Hsiesta`; a Start Menu
shortcut is created by default and the desktop shortcut is optional. The installer
itself does not require administrator privileges, while the existing
`GameAutomationControlPlane.exe` manifest still requests `requireAdministrator`.
That is why installing can be per-user but launching the application may still show
UAC.

Uninstall removes only Hsiesta's program files, shortcuts, and uninstaller. It does
not delete the existing `%LOCALAPPDATA%\GameAutomationControlPlane` database, logs,
or configuration. The package and executable names still use
`GameAutomationControlPlane` so existing installations and local data remain
compatible; the application itself is branded Hsiesta.

> The installer and application are currently unsigned, so Windows SmartScreen may
> show a warning. Confirm that the download came from the official Releases page;
> do not disable Windows Defender or other security software to run it.

<details>
<summary>Advanced verification and portable ZIP</summary>

For portable use or release verification, download the Windows ZIP and its matching
`.sha256` file:

1. Verify the SHA-256 checksum in PowerShell:

   ```powershell
   Get-FileHash .\GameAutomationControlPlane-windows.zip -Algorithm SHA256
   Get-Content .\GameAutomationControlPlane-windows.zip.sha256
   ```

2. Extract the complete ZIP and run `GameAutomationControlPlane.exe`. Keep the `_internal` directory beside the executable.

</details>

Application data is stored under `%LOCALAPPDATA%\GameAutomationControlPlane\` by default. The rebrand does not require moving or recreating existing data; future launches may still apply the application's built-in schema migrations. Set `GAME_CONTROL_PLANE_DATA_DIR` when you need an isolated development or test directory.

## What Hsiesta can do

- Keep each game's daily task together with its executable, arguments, and working directory.
- Run supported preflight checks before launching a task, so configuration problems are visible earlier.
- Keep status, exit code, duration, stdout/stderr, and SQLite run history in one place.
- Run today's queue in order while unrelated manual jobs continue; the same job or MuMu instance is not claimed twice.
- Keep execution separate from your manual “daily complete” decision. Hsiesta never marks a daily complete just because a process returned successfully.

## Supported tools

| Tool / integration | Game | Current scope |
| --- | --- | --- |
| MAA / `maa-cli` | Arknights | Version, task, dry-run, and ADB preflight; managed daily tasks; ownership-aware MuMu monitoring |
| MAA_Punish / FOS | Punishing: Gray Raven | Saved-config discovery, task-flow monitoring, and exact-path FOS/MuMu handling |
| OK-WW | Wuthering Waves | Positive task index, `-t <index>`, optional `-e`, and constrained worker handoff monitoring |
| Zenless Zone Zero OneDragon | Zenless Zone Zero | Connects an installed RuntimeLauncher (preferred) or classic launcher and explicitly calls the one-dragon entry point, with optional instance and `-c` arguments |
| Custom CLI | Other external scripts | Explicit interpreter/executable, arguments, working directory, output, and run history |

OneDragon currently supports Zenless Zone Zero; install and configure OneDragon before using it.

<details>
<summary>Verification boundaries and common questions</summary>

### Is Hsiesta a general-purpose game bot?

No. Hsiesta schedules and monitors external tools that you have installed. It does not implement image recognition, game interaction, or compatibility with arbitrary scripts. A game's appearance in a search result does not mean that it is supported here.

### Why can a run need review after exiting with code 0?

Exit code 0 only means that the external process ended normally. MAA requires complete task evidence and at least one real battle; OneDragon has no completion signal that Hsiesta can trust, so a clean exit still needs log review and manual confirmation.

### What has been verified for each integration?

- MAA / `maa-cli`: preflight, configuration contracts, managed task generation, and result auditing have local test coverage; a complete live MAA daily run is not claimed as verified here.
- MAA_Punish / FOS: saved-config discovery, task-flow monitoring, exact-path process handling, and MuMu ownership have contract coverage; Hsiesta does not replace or bundle FOS.
- OK-WW: task arguments and worker handoff are covered locally; the complete flow and process behavior of your installed version still need validation in your environment.
- OneDragon: launcher discovery, Runtime/classic layout checks, `-o`/`-i`/`-c` construction, and failure paths are covered locally; installed-version differences, account existence, and the live game flow remain user-side checks.

### Which OneDragon directory should I select?

For the classic OneDragon Full-Environment layout, select the complete directory containing `OneDragon-Launcher.exe`, `config/project.yml`, and `config/repository.yml`. The compatibility layout requires the complete `resources/config/*.yml` set. Do not move the YAML files.

### What should I check when startup fails?

Open the task's run log first. Confirm that the executable, working directory, and arguments point to the external tool you installed. If preflight fails, fix the first failed step shown by the wizard. Do not paste a complete shell command into the arguments field, and do not move OneDragon YAML files.

For adapter contracts and failure paths, see [docs/integrations.md](docs/integrations.md). For lifecycle, SQLite, queue, and MuMu ownership details, see [docs/architecture.md](docs/architecture.md).

</details>

<details>
<summary>Run from source and develop</summary>

The supported development path is Windows + Python 3.11:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[test]"
$env:QT_QPA_PLATFORM = "offscreen"
python -m pytest
python -m compileall -q src tests packaging
python -m game_control_plane
```

Read [`AGENTS.md`](AGENTS.md) before changing code. See [`CONTRIBUTING.md`](CONTRIBUTING.md) and [`SECURITY.md`](SECURITY.md) before opening a change. The Windows package workflow is [`windows-package.yml`](.github/workflows/windows-package.yml).

</details>

<details>
<summary>License and disclaimer</summary>

The source code and original project artwork are licensed under [AGPL-3.0-only](LICENSE). MAA, MaaFramework, MAA_Punish/FOS, OK-WW, MuMu, and the referenced games belong to their respective owners. They are not bundled with this repository or its Windows ZIP, and Hsiesta is not affiliated with or endorsed by their maintainers or publishers. Qt/PySide6 notices are in [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).

Automation may be restricted by game, platform, or service terms. Check the applicable rules yourself and accept responsibility for account, data, and system risks. Hsiesta does not guarantee that any third-party tool, game version, account, or environment will work.

</details>
