# Agent guide

This file is the operating guide for Codex, Claude Code, GitHub Copilot, and
other coding agents working in this repository. Read it before changing code;
then read the relevant documents under `docs/` and the tests that define the
behavior you will touch.

## Project scope

Hsiesta (休汐) is a Windows-first PySide6 desktop control plane for organizing
external game-automation jobs. It coordinates configured
launchers, captures their output, stores run history in SQLite, and presents a
small dashboard. It is not a game client, image-recognition engine, emulator,
or replacement for MAA, MAA_Punish/FOS, OK-WW, MuMu, MaaFramework, or OneDragon.

The supported release path is Windows and Python 3.11. The current version is
declared in both `pyproject.toml` and `src/game_control_plane/__init__.py`.
Keep those values aligned and update `CHANGELOG.md` for user-visible changes.

## Read first

- `README.md` for the supported user-facing scope and honest verification
  boundary.
- `docs/integrations.md` for the difference between locally verified behavior,
  upstream-documented contracts, and unverified live-game behavior.
- `docs/architecture.md` for lifecycle, persistence, UI, and queue design.
- `CONTRIBUTING.md` and `SECURITY.md` before preparing a contribution.

## Source map

- `src/game_control_plane/ui/`: PySide6 dashboard, editor, dialogs, theme, and
  localization.
- `src/game_control_plane/application/`: execution, queueing, process handoff,
  emulator watchdog, result audit, and post-run actions.
- `src/game_control_plane/integrations/`: explicit contracts for Custom CLI,
  MAA/maa-cli, MAA_Punish/FOS, OK-WW, and the focused Zenless Zone Zero
  OneDragon launcher.
- `src/game_control_plane/domain/`: job/run models and daily-cycle semantics.
- `src/game_control_plane/persistence/`: SQLite store and numbered migrations.
- `src/game_control_plane/platform/`: application data paths, logging, and
  retention safeguards.
- `packaging/`: PyInstaller spec, Windows build wrapper, portable smoke test,
  and the optional Inno Setup installer layer.
- `tests/unit/` and `tests/integration/`: the primary behavioral contract.

## Protected invariants

### Execution and completion

- Launch external programs with an explicit executable/interpreter and an
  explicit argument list. Never turn a command string into an implicit shell
  invocation.
- Keep `QProcess` and other run monitoring non-blocking on the GUI thread.
- A process exit code of zero is not automatically a verified game success.
  Managed MAA requires complete task evidence and at least one real battle;
  FOS requires the complete task-flow markers; OneDragon has no trusted
  completion protocol and always needs manual review after a clean exit.
  Preserve diagnostics when a run needs attention.
- Keep execution result separate from the user's manual `DailyCompletion`.
  A successful run must not silently mark a daily complete.

### Queue and concurrency

- The daily queue is an in-memory snapshot of enabled, pending jobs in
  `queue_order`; it runs one queued item at a time and is not resumed after a
  restart.
- Unrelated manual jobs may run concurrently. Reject a duplicate start of the
  same job and prevent two runs from claiming the same exact MuMu executable
  and instance.
- Match completion signals and cleanup to the exact run ID. Do not let one
  queued item consume another item's result.

### MuMu and FOS ownership

- Only close a MuMu instance that this run started and owns. An instance that
  was already running before preflight must remain open.
- When multiple queued jobs share an instance, transfer ownership to the last
  queued consumer so an earlier item cannot close it underneath a later item.
- For FOS cleanup, target the launched process or an exact configured
  executable-path match. Never broad-kill every process named `FOS.exe`.
- A requested cleanup failure must remain visible as a warning/failure rather
  than being reported as an unqualified clean success.

### Integration boundaries

When adding or changing an adapter, document the upstream project and exact
local version, then implement and test these stages separately:

1. conservative executable/config discovery;
2. schema and preflight validation;
3. explicit launch arguments and working directory;
4. non-blocking monitoring and result evidence;
5. failure, timeout, handoff, and cleanup behavior;
6. focused unit/integration tests and an update to `docs/integrations.md`.

Do not bundle third-party tools, DLLs, game assets, or external repositories.
Do not invent an upstream contract from a name or a screenshot. Do not claim a
live game workflow is verified unless it has been run and recorded in the
appropriate evidence boundary.

For the focused Zenless Zone Zero OneDragon adapter, use only the official
launcher contract `-o`, optional `-i` with comma-separated positive indices,
and optional `-c`. Prefer `OneDragon-RuntimeLauncher.exe` and require adjacent
`.runtime` and `src`; for the classic launcher, accept only one complete pair:
`config/project.yml` and `config/repository.yml` from the official
Full-Environment layout, or `resources/config/*.yml` as a compatibility
layout. Do not mix the two layouts. Do not read or
rewrite OneDragon YAML/account settings, infer an account allowlist, bundle its
runtime/models/game files, follow an unverified worker, take over the game
window, or force-stop by process name. A user-requested stop may terminate
only the exact launcher PID tree captured and revalidated for that run. On
Windows, take a FILETIME cutoff before each trusted root snapshot, hold handles
for the root tree, and validate creation tokens and continuous root-relative
ancestry through child-first/root-last termination. A new descendant causes a
bounded full recapture; a PID reused after the cutoff, parent-chain change,
handle/query failure, termination failure, or residual tree fails closed
without falling back to a name kill. If the identity cannot be proved, record a
stop failure and leave the external process for inspection. Installed
account existence and the actual ZZZ daily flow remain user-side verification
boundaries.

### Data, configuration, and security

- Application data belongs under `%LOCALAPPDATA%\GameAutomationControlPlane`;
  tests may use `GAME_CONTROL_PLANE_DATA_DIR`.
- Never commit databases, captured logs, account configuration, credentials,
  tokens, signing material, real personal paths, or generated `build/` and
  `dist/` output.
- Do not write user or upstream configuration as a side effect of inspection.
  An integration may write only the application-owned `control_plane_*` task
  file when its documented contract explicitly requires it; preserve existing
  user-maintained task names and settings.
- Do not delete or overwrite local backups, including any pre-AGPL backup, even
  when cleaning generated output.

### Packaging and release

- Use `packaging/build_windows.ps1` and `packaging/smoke_test.ps1`; keep the
  SQL migration, Qt platform plugin, project license, and third-party notices
  in the package.
- The optional `packaging/hsiesta.iss` layer consumes the already-built
  `dist/GameAutomationControlPlane` onedir directory. Use
  `packaging/build_installer.ps1` to inject the version and
  `packaging/installer_smoke_test.ps1` to prove install/uninstall behavior; do
  not add Inno Setup to Python dependencies or bundle external automation
  tools, runtimes, models, or game files.
- The installer uses `PrivilegesRequired=lowest` and installs per-user, but the
  existing `GameAutomationControlPlane.exe` manifest still requests
  `requireAdministrator`. Keep this installer/runtime UAC distinction visible
  in user documentation. Uninstall must never remove
  `%LOCALAPPDATA%/GameAutomationControlPlane` or its SQLite data, logs, or
  settings.
- For a reproducible installer proof, obtain official Inno Setup 7.1.0 through
  `packaging/install_inno_setup.ps1`, which checks the pinned SHA-256 and
  Authenticode publisher before execution. Keep the portable ZIP and checksum
  workflow unchanged alongside the installer artifacts.
- Keep Actions permissions read-only. A release requires a successful Windows
  package proof, its ZIP and SHA-256, installer and installer SHA-256, and a
  verified license-material payload.
- Do not modify repository permissions, branch protection, or security settings
  as part of normal code or documentation work.

## Development commands

From a Windows checkout with Python 3.11:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[test]"
$env:QT_QPA_PLATFORM = "offscreen"
python -m pytest
python -m compileall -q src tests packaging
```

For the packaging proof:

```powershell
python -m pip install -e ".[test,build]" -c packaging\constraints.txt
$env:QT_QPA_PLATFORM = "offscreen"
python -m pytest
.\packaging\build_windows.ps1 -PythonExecutable python
.\packaging\smoke_test.ps1 -ExecutablePath .\dist\GameAutomationControlPlane\GameAutomationControlPlane.exe
$iscc = & .\packaging\install_inno_setup.ps1 -InstallDirectory (Join-Path $env:TEMP "hsiesta-inno-setup-7.1.0")
.\packaging\build_installer.ps1 -IsccPath $iscc
.\packaging\installer_smoke_test.ps1 -InstallerPath .\dist\Hsiesta-0.1.21-Setup.exe
```

If a non-interactive environment cannot run the installed executable because
its existing manifest requests elevation, use the installer smoke script's
`-SkipPackagedSmoke` option only after the standalone onedir smoke above has
passed; install, payload, shortcut, uninstall, and user-data assertions still
run.

Use the narrowest relevant checks first, then run the full suite and packaging
checks for release-facing changes. Report exactly what was verified and what
remains unverified.
