# Changelog

All notable changes are recorded here. Version 0.1.20 is the current source
version of the project.

## [0.1.20] — 2026-08-30

### Fixed

- Fixed OneDragon stop validation rejecting valid Windows process snapshots
  because the Toolhelp snapshot includes the synthetic PID 0 System Idle
  Process entry.
- MAA / `maa-cli` tasks that use an external, user-maintained task file now
  enter `needs_attention` after exit code 0 instead of appearing as a verified
  completion. Hsiesta keeps the captured logs, skips owned MuMu cleanup, and
  asks for manual confirmation because it cannot infer the external task's
  intended steps.
- Added localized Chinese and English review prompts for external MAA runs.

## [0.1.19] — 2026-08-29

### Added

- Added an explicit **Open OneDragon GUI** action to OneDragon task cards.
  It starts the configured launcher with no arguments in its installation
  directory, without creating a Hsiesta run or attaching to an automatic run.
- Added a OneDragon-only **Stop** action that records an interrupted run and
  can terminate only the verified launcher PID tree owned by that run.

### Changed

- OneDragon automatic runs are labelled **Run automatically** and remain the
  official `-o` headless mode. Hsiesta blocks its own GUI action while that
  task is active or queued, but a detached GUI is not tracked and a GUI opened
  elsewhere cannot be detected; close the official GUI before an automatic run.
- Exact OneDragon stops now take a FILETIME cutoff before each Windows tree
  capture, hold root-tree process handles through validation, retry only a
  bounded number of times when a new descendant appears, and verify that no
  owned process remains afterward. PID reuse or parent changes fail closed
  without name-based cleanup.
- Normal Hsiesta shutdown now stops owned active processes and waits for their
  terminal run persistence before closing SQLite. Stop failures remain visible
  and do not mark a daily complete.

## [0.1.18] — 2026-08-28

### Added

- Added a separate Inno Setup installer with per-user installation under
  `%LOCALAPPDATA%\Programs\Hsiesta`, Start Menu shortcuts, optional desktop
  shortcut, and data-safe silent install/uninstall smoke coverage.
- Added a pinned, hash- and Authenticode-verified Inno Setup 7.1.0 bootstrap
  for local and Windows Actions builds.

### Changed

- Kept the existing PyInstaller onedir build, portable ZIP, executable and
  application-data identifiers unchanged; uninstall never removes the
  `%LOCALAPPDATA%\GameAutomationControlPlane` data directory.

## [0.1.17] — 2026-08-28

### Changed

- Softened the bilingual homepage integration messaging and added a clear
  note that more mobile-game daily tools will be added gradually.
- Kept the existing package, executable, ZIP, and application-data identifiers
  unchanged for compatibility.

## [0.1.16] — 2026-08-28

### Changed

- Rebranded the desktop application as **休汐 Hsiesta** and refreshed the
  bilingual README and GitHub-facing copy.
- Kept the existing application data directory, UI settings keys, managed MAA
  task names, Python package, console command, and Windows executable layout so
  existing installations can be upgraded without data migration.

## [0.1.15] — 2026-08-28

### Fixed

- Fixed classic `OneDragon-Launcher.exe` preflight to accept the official
  Full-Environment root `config/project.yml` and `config/repository.yml`
  layout, while retaining the complete `resources/config` compatibility
  layout.
- Updated bilingual guidance to select a complete official directory instead
  of moving OneDragon YAML files.

## [0.1.14] — 2026-08-28

### Added

- Added a focused **Zenless Zone Zero OneDragon** integration for an existing
  `OneDragon-RuntimeLauncher.exe` or official `OneDragon-Launcher.exe`.
- Added conservative launcher discovery, Runtime/classic layout preflight,
  bilingual editor fields, and tests for explicit `-o`, optional `-i`, and
  optional `-c` arguments.

### Changed

- OneDragon exit code 0 is recorded as `needs_attention`; captured logs remain
  available and the Control Plane never marks a daily complete automatically.
- Documented the upstream launcher contract and the unverified live-game and
  installed-version boundaries.

## [0.1.13] — 2026-08-27

### Changed

- Prepared the source tree for public GitHub review with bilingual README
  navigation, privacy-safe examples, contribution templates, stricter ignore
  rules, version consistency coverage, and CI-generated SHA-256 checksums.
- Added a constraints file for the tested Windows packaging dependency set.
- Added Qt/PySide6 third-party notices, LGPL/GPL license texts, corresponding
  source links, and a Windows build wrapper that verifies and exposes those
  materials in the packaged application directory.
- Documented the project owner's rights to the original hand-drawn icon.
- Licensed the project source code and original project artwork under
  AGPL-3.0-only, and included the project license in Windows packages.

## [0.1.12] — 2026-08-27

### Changed

- Replaced the project icon with the user-selected anime artwork and rebuilt
  the transparent PNG and multi-size Windows ICO assets.

## [0.1.11] — 2026-08-27

### Added

- Added an original anime-style cyber-operator project icon, including a
  transparent PNG for Qt windows and a multi-size ICO embedded in the Windows
  executable.

## [0.1.10] — Unreleased

### Added

- Added a separate, default-enabled MAA_Punish option to close the associated
  FOS process after a fully verified successful task flow.

### Fixed

- FOS cleanup now targets the process launched for the request, or an exact
  executable-path match when an existing FOS instance was reused. A requested
  close failure no longer appears as a clean completion.

## [0.1.9] — Unreleased

### Added

- Added a Control Plane managed MAA daily-task editor for startup, recruitment,
  infrastructure, credit/friend/shopping actions, stage and stamina strategy,
  consecutive proxy count, and rewards.
- Added managed-task output auditing so an incomplete chain or zero completed
  battles is shown as **needs attention** even when `maa-cli` exits with code
  zero.

### Changed

- MAA preflight now writes an application-owned task file atomically under the
  active `maa dir config` directory and validates it with a dry run.
- Ownership-based emulator shutdown is skipped when a managed MAA result needs
  attention, preserving the instance and logs for diagnosis.
- Existing external maa-cli task configurations remain supported and are not
  rewritten automatically.

## [0.1.8] — Unreleased

### Added

- Added a guided MAA_Punish/FOS integration for Punishing: Gray Raven with
  conservative FOS discovery and selection of saved FOS configurations.
- Added optional ownership-aware MuMu startup, runtime monitoring, and
  close-after-success behavior shared with the existing MAA integration.
- Added a packaged internal FOS monitor that follows the current run's
  `debug/gui.log` task flow and distinguishes accepted GUI handoff from actual
  task completion or failure.

### Changed

- MuMu resource locking now prevents an MAA and an FOS job from controlling
  the same instance concurrently while still allowing unrelated games and
  emulator instances to run at the same time.

## [0.1.7] — Unreleased

### Added

- Simplified Chinese is now the default interface language, with a persistent
  **Settings → Language → English** option that updates the dashboard live.
- Chinese and English text now cover the dashboard, job editor, MAA setup
  shell/progress, run history, and application message boxes. Raw automation
  logs and third-party technical errors remain unchanged for diagnosis.

### Changed

- Replaced the plain native layout with a cohesive dark desktop theme, clearer
  typography, teal primary actions, text-backed status colors, summary tiles,
  and responsive two-row card actions.
- Reorganized the job editor into scrollable Basic information, Launch
  configuration, and Daily rules sections.
- The dashboard now uses localized game names for the built-in MAA and OK-WW
  integrations without rewriting existing stored game records.

## [0.1.6] — Unreleased

### Added

- MAA jobs can close the exact MuMu instance after a successful run, but only
  when that instance was started by Control Plane for the current manual run or
  daily queue.
- OK-WW jobs can choose whether `-e` closes Wuthering Waves after the selected
  task; older saved jobs preserve the previous close-after behavior.
- Different jobs can run concurrently. Duplicate starts of the same job and
  concurrent use of the same associated MuMu instance remain blocked.

### Changed

- The daily queue remains sequential internally but can coexist with unrelated
  manually started jobs.
- MuMu shutdown runs asynchronously. A shutdown failure is shown as a cleanup
  warning without changing an already successful automation result to failed.

## [0.1.5] — Unreleased

### Fixed

- An active MAA run now monitors its explicitly associated MuMu instance.
- Two consecutive stopped-instance responses terminate only the `maa-cli`
  process owned by that run, then record `emulator_disconnected` instead of
  leaving MAA active without its emulator.
- Temporary `mumu-cli info` failures do not stop MAA, avoiding a monitoring
  error being mistaken for a closed emulator.

## [0.1.4] — Unreleased

### Added

- MAA jobs can optionally associate a MuMu instance and start it automatically
  when the configured ADB device is not already ready.
- The preflight uses MuMu's command tool with the exact saved instance number,
  then waits for the MAA profile's ADB address before launching the real task.
- A responsive progress window reports startup status while the emulator boots;
  readiness, launch failure, and timeout paths have focused test coverage.

## [0.1.3] — Unreleased

### Added

- MAA Run actions now perform a four-step preflight for the executable, task
  name, safe dry-run, and configured ADB device before starting automation.
- Failed MAA checks open a step-by-step setup guide with a focused next action,
  retry, edit, and expandable technical details.
- The same gate is applied before the dashboard's daily queue begins, so a
  misconfigured MAA item cannot be launched through the queue by accident.

## [0.1.2] — Unreleased

### Changed

- The packaged Windows executable now requests administrator privileges on
  every launch, allowing it to start elevated automation launchers such as
  OK-WW without requiring the context-menu **Run as administrator** action.

## [0.1.1] — Unreleased

### Fixed

- OK-WW runs are no longer marked failed when `ok-ww.exe` hands execution to
  its packaged Python worker and then intentionally exits.
- Added a Windows-only, path-restricted handoff monitor with a short discovery
  grace period; MAA CLI and Custom CLI execution behavior is unchanged.
- Added coverage for late worker discovery, successful and failed worker exits,
  unrelated-process filtering, and launcher fallback.

## [0.1.0] — Unreleased

### Added

- Windows PySide6 desktop dashboard for configuring Custom CLI automations.
- SQLite persistence with numbered migrations for games, jobs, runs, and daily
  completions.
- Versioned Custom CLI configuration with explicit executable/interpreter,
  argument list, and optional working directory.
- Contract-bound MAA/`maa-cli` integration with versioned executable/task
  configuration, conservative WinGet discovery, Arknights onboarding, and the
  documented `run <task> --batch` launch spec. End-to-end task execution is
  intentionally not claimed.
- Contract-bound OK-WW integration with versioned executable/task-index
  configuration, conservative PATH/env/shortcut discovery, Wuthering Waves
  onboarding, and the documented `-t <index> -e` launch spec. Local execution
  and process-termination compatibility are intentionally not claimed.
- Non-blocking `QProcess` execution with durable state, stdout/stderr capture,
  run history, durations, and startup recovery of interrupted runs.
- In-memory sequential queue for enabled, pending jobs in user-controlled order.
- Manual mark-completed and undo/pending controls kept separate from process
  exit status.
- Safe startup log retention with failure preservation and path confinement.
- Repeatable Windows PyInstaller onedir packaging, smoke launch, and Actions
  artifact workflow.

### Not included

- Live OneDragon completion verification, or end-to-end verification of the
  current MAA `daily` task/configuration or OK-WW process termination.
- Scheduling, plugins, parallel execution, process-tree stop/cancel, automatic
  verification, or automatic daily completion.
- Updater, code signing, GitHub Release publication, or a project license.
