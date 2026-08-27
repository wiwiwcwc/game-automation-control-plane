# Game Automation Control Plane

[简体中文](README.zh-CN.md) | **English**

<img src="src/game_control_plane/assets/app_icon.png" alt="Game Automation Control Plane icon" width="128">

Game Automation Control Plane is a small Windows desktop application for
organizing and running daily game-automation jobs. Version 0.1.13 is currently
unreleased. The project source code and the original hand-drawn project icon
are licensed under the [GNU Affero General Public License v3.0 only](LICENSE).

## Current capabilities

- Use the selected anime-style white-haired operator icon across the Windows
  EXE and application windows, with transparent corners and multi-size assets.
- Use a polished dark desktop interface in Simplified Chinese by default, with
  a persistent English option under **设置 → 语言**.
- Configure and edit Custom CLI jobs grouped by game.
- Configure contract-bound MAA/`maa-cli` jobs; MAA onboarding labels the game
  Arknights, discovers the executable, and can generate a managed daily task
  with recruitment, base, credit, shopping, stamina, stage, repeat-count, and
  reward options. It checks the task and emulator before a manual or queued
  Run. It can start an associated MuMu instance and, when it started that
  instance itself, optionally close it after a verified success.
- Configure MAA_Punish/FOS jobs for Punishing: Gray Raven from FOS's saved
  configurations. The control plane can start the associated MuMu instance,
  follow the real FOS task flow, optionally close the associated FOS process,
  and optionally close only a MuMu instance it owns.
- Configure contract-bound OK-WW jobs; OK-WW onboarding labels the game
  Wuthering Waves, exposes a positive task index, and can leave the game open
  or request that it close after the task.
- Launch an executable or interpreter directly with an explicit argument list.
- Capture stdout/stderr and retain SQLite run history, including duration and
  concise errors. Managed MAA runs distinguish a complete task chain from a
  zero-battle or incomplete result.
- Run today's enabled, pending jobs sequentially in queue order while unrelated
  manually started games continue concurrently.
- Reorder jobs, mark a daily period completed manually, and undo that mark.
- Recover runs that were active when the application closed as interrupted.
- Prune old captured run directories while retaining run metadata and the
  latest failed or needs-attention run for each job.

The current implementation is intentionally game-first and conservative: a
successful process exit does not mark a daily as completed.

## Explicit limitations

Custom CLI, contract-bound MAA/`maa-cli`, MAA_Punish/FOS, and OK-WW
integrations are implemented. Before MAA starts, the UI checks the
executable, exact task name, safe dry-run, and configured ADB device, then shows
a focused setup guide if a step fails. A full live MAA daily run remains
unverified. The OK-WW adapter validates
an explicit executable/positive task index and builds `-t <index>` with an
optional `-e`. On
Windows it follows the launcher's handoff to a trusted `pythonw.exe` or
`python.exe` worker under the same OK-WW installation, so the launcher's own
shutdown is not mistaken for task failure. OneDragon is not included. There is
no scheduler, plugin system,
parallel execution inside one queue, process-tree stop/cancel operation, automatic verification, or
automatic daily completion. The queue is an in-memory snapshot and is not
persisted or resumed after restart. See
[integration status](docs/integrations.md) and the [architecture notes](docs/architecture.md)
for the current boundary.

## Using a packaged Windows ZIP

When a Windows artifact is available from GitHub Actions, extract the complete
ZIP directory and launch `GameAutomationControlPlane.exe`. Keep the executable
with its `_internal` directory; do not copy out only the EXE. The repository
does not publish a GitHub Release. It defines an Actions workflow to build and
upload the artifact and its SHA-256 checksum; an Actions run is required before
a ZIP is available.

Current Windows packages are unsigned. Windows may show UAC and SmartScreen
prompts; verify the downloaded ZIP against the checksum from the same workflow
run. Do not disable antivirus protection to launch the application.

The default Windows data directory is:

```text
%LOCALAPPDATA%\GameAutomationControlPlane\
├── control_plane.sqlite3
├── logs\app.log
└── runs\<run-id>\
    ├── stdout.log
    ├── stderr.log
    └── metadata.json
```

If `%LOCALAPPDATA%` is unavailable, the application falls back to
`%APPDATA%`. For development or tests, set
`GAME_CONTROL_PLANE_DATA_DIR` to an explicit directory before launching.

## Configuring a Custom CLI job

The job editor requires an absolute executable or interpreter path. It passes
arguments directly to Qt's `QProcess`; it does not invoke an implicit shell or
parse a command string.

For a Python script, enter values equivalent to:

```text
Executable / interpreter: C:\Python311\python.exe
Arguments (one per line):
C:\Automation\daily_tasks.py
--profile
main
Working directory: C:\Automation
```

For a PowerShell script, select `powershell.exe` (or `pwsh.exe`) as the
executable and pass `-NoProfile`, `-File`, and the absolute script path as
separate arguments. A script's own interpreter must be explicit.

## Configuring MAA / `maa-cli`

Choose **MAA** in the job editor. The game is labeled **Arknights**, and the
editor looks for `maa-cli` on PATH before checking the expected WinGet package
location under `%LOCALAPPDATA%\Microsoft\WinGet\Packages`. You can always edit
the discovered path explicitly.

New jobs default to **Control Plane managed task**. The editor exposes startup,
recruitment count, infrastructure, friend visits, credit shopping, credit
fight, stage, total fight count, consecutive proxy count (automatic or
`×1`–`×10`), medicine, expiring medicine, Originite, awards, and mail. Before
each preflight, the app writes only that job's `control_plane_*` TOML file to
the directory reported by `maa dir config`, then validates it through
`maa run <task> --batch --dry-run`. Existing user-maintained task names remain
available through **Existing maa-cli task** and are not rewritten.

The current verified contract is for WinGet package
`MaaAssistantArknights.maa-cli` version 0.7.5. When **Run** is selected, the
control plane checks `maa-cli --version`, the exact task returned by `maa list`,
`run <task> --batch --dry-run`, and the ADB address in the default MAA profile.
If a step fails, no real run is recorded or started; a guide shows the first
problem, the next action, and a retry button. See
[integration status](docs/integrations.md).

To avoid opening the emulator manually, enable **Start and monitor MuMu
automatically**, choose MuMu's `mumu-cli.exe`, and enter the instance number shown by
MuMu's multi-instance manager. Run first checks the exact ADB address saved in
MAA's default profile. If it is already ready, MuMu is left alone. Otherwise,
the control plane launches only the saved instance and waits up to the selected
timeout before continuing. While MAA is active, the same association checks the
exact MuMu instance every two seconds. Two consecutive stopped responses end
only this run's `maa-cli` process and record a failed run; temporary status-command
errors do not terminate it. Emulator startup does not run or complete the MAA
task by itself.

Enable **Close this MuMu instance after a successful run when started here** to
clean up an automatically started instance. This is run-scoped ownership: an
instance that was already running before the preflight is never closed. If
multiple queued MAA jobs share that instance, ownership is carried to the last
queued consumer so an earlier item does not close it underneath a later item.
Two concurrently running jobs may not claim the same MuMu instance.

For a managed task, exit code zero is not enough to show a verified success.
The output must contain a completed summary for every enabled task, and an
enabled Fight task must report at least one actual battle. Otherwise the run is
shown as **Partial · needs attention**, its diagnostic logs are retained, and
an emulator owned by Control Plane is deliberately left open for inspection.
External maa-cli tasks keep the legacy exit-code behavior because their custom
task structure cannot be inferred safely.

## Configuring MAA_Punish / FOS

Choose **MAA_Punish** in the job editor. The game is labeled **Punishing: Gray
Raven**. The editor looks for `FOS.exe` on PATH and in common Desktop and
Downloads locations, then lists the saved FOS configurations from
`config\configs`. Select the FOS configuration whose task list and controller
you want to run. The launch contract is:

```text
FOS.exe --direct-run --reuse-existing --config-id <configuration-id>
```

FOS's small command process can exit after handing the request to an existing
GUI, so exit code zero alone is not treated as task completion. An internal
monitor starts at the current end of `debug\gui.log`, ignores old results, and
requires a new task-flow start, the all-tasks-complete message, a clean
`task_flow_finished` record, and `TASK_FLOW_STOP manual=False`. A task failure,
manual/forced stop, startup timeout, or an early FOS exit fails the Control
Plane run. **Close the associated FOS after success** is enabled by default and
can be disabled when FOS should remain resident for reuse. The close operation
targets the configured executable rather than every process named `FOS.exe`;
if the requested close fails, the run does not report a clean success.

For a FOS configuration using the Android controller, the editor imports its
saved MuMu instance number and can enable **Start and monitor MuMu
automatically**. The same ownership rule as MAA applies: **Close this MuMu
instance after a successful run when started here** only closes an instance
that Control Plane started for that run. An already-running instance is never
closed, and MAA/FOS jobs cannot concurrently claim the same exact MuMu
instance. The saved instance number and ADB endpoint are installation-specific
and must be checked on each user's machine.

## Configuring OK-WW

Choose **OK-WW** in the job editor. The game is labeled **Wuthering Waves**,
and the task index defaults to `1`. The editor checks `ok-ww.exe` on PATH, then
the optional `OK_WW_EXECUTABLE` environment variable, then likely Windows
shortcut targets whose existing target is named `ok-ww.exe`. The executable
path remains visible and editable. The adapter launches
`ok-ww.exe -t <index>` directly and adds `-e` when **Close Wuthering Waves
after the task finishes** is selected. The executable's parent is used as the
working directory. Existing configurations that predate this option retain
the previous `-e` behavior.

The upstream README documents `ok-ww.exe -t 1 -e`. Upstream has had a
historical closed regression involving `-e`, so validate the installed/current
version's process-termination behavior before relying on it.
This project does not update OK-WW, start Wuthering Waves, or inspect stale
uninstall registry entries.

## Development

Python 3.11 is the supported development and packaging target. From a fresh
checkout on Windows:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[test]"
$env:QT_QPA_PLATFORM = "offscreen"
python -m pytest
python -m compileall -q src tests packaging
python -m game_control_plane
```

The application itself is started with `python -m game_control_plane` during
development. The test suite uses a harmless fixture CLI and does not require a
game client.

## Windows packaging proof

The repository contains a repeatable PyInstaller onedir definition for a
windowed Windows build:

```powershell
python -m pip install -e ".[test,build]" -c packaging\constraints.txt
$env:QT_QPA_PLATFORM = "offscreen"
python -m pytest
.\packaging\build_windows.ps1 -PythonExecutable python
.\packaging\smoke_test.ps1 -ExecutablePath .\dist\GameAutomationControlPlane\GameAutomationControlPlane.exe
Compress-Archive -Path dist\GameAutomationControlPlane -DestinationPath dist\GameAutomationControlPlane-windows.zip
```

The smoke script sets `GAME_CONTROL_PLANE_PACKAGED_SMOKE=1`, points the app at a
temporary data directory, and waits for a clean GUI exit. That explicit test
flag changes no normal launch behavior. The build includes the SQL migrations
and Qt Windows platform plugin; the Windows workflow checks for those files and
for the absence of obvious development/test payloads before uploading the ZIP.
The packaged executable declares `requireAdministrator`, so a normal double
click opens the standard Windows UAC confirmation prompt automatically. The
user no longer needs to select **Run as administrator** from the context menu.

## Project documents

- [Architecture](docs/architecture.md)
- [Integration status](docs/integrations.md)
- [GitHub publishing guide](docs/github-publishing.md)
- [Contributing](CONTRIBUTING.md)
- [Security](SECURITY.md)
- [Changelog](CHANGELOG.md)
- [Third-party notices](THIRD_PARTY_NOTICES.md)
- [Project artwork](ASSETS.md)
- [Project license](LICENSE)

## Third-party projects and trademarks

MAA, MAA_Punish/FOS, OK-WW, MuMu, and the referenced games are external
projects or products. They are not bundled with this repository, and this
project is not affiliated with or endorsed by their maintainers or publishers.
Their names, trademarks, code, and licenses remain the property of their
respective owners.
