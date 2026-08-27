# Architecture

This document describes the 0.1.13 implementation, not a promise about future
integrations. The main path is:

```text
Game → Job → Integration / Execution → Run
                         └──────────────┘
DailyCompletion is a separate durable ledger keyed by Job and reset period.
```

## Core model

| Object | Durable responsibility |
| --- | --- |
| Game | Names a game and groups related jobs. It does not run anything itself. |
| Job | Stores the automation name, enabled flag, queue order, timezone/reset settings, integration type, and versioned JSON runner configuration. |
| Integration | Validates a job configuration and turns it into an explicit launch specification. The registry contains `custom_cli`, contract-bound `maa_cli`, `maa_punish`, and contract-bound `ok_ww` integrations. |
| Execution | Owns independent asynchronous Qt `QProcess` objects per active run, persists state transitions, and captures output. |
| Run | Records one attempted launch, its trigger, state, exit information, errors, launch snapshot, and captured-log paths. |
| DailyCompletion | Records a manual completion for one job and one computed daily period. It is intentionally separate from process exit. |

The model definitions live in
[`domain/models.py`](../src/game_control_plane/domain/models.py), and the
SQLite mapping lives in [`persistence/store.py`](../src/game_control_plane/persistence/store.py).

## Execution lifecycle

`ExecutionService` creates a run directory under the configured `runs` path,
then asks the selected integration to validate the job and build a launch
specification. Custom CLI requires an absolute executable/interpreter path and
a list of string arguments. The contract-bound MAA integration requires an
absolute `maa-cli.exe` path and a task name, then builds `run <task> --batch`.
The contract-bound OK-WW integration requires an absolute `ok-ww.exe` path and
a positive task index, then builds `-t <index>` and conditionally adds `-e`,
with the executable's parent as its working directory.

The MAA_Punish integration requires an absolute `FOS.exe` path and an existing
saved configuration ID. Its launch specification invokes this application's
internal FOS monitor. That monitor starts/reuses FOS with `--direct-run`,
`--reuse-existing`, and `--config-id`, then follows only newly appended
`debug/gui.log` content until it observes a full successful task flow or a
failure. This keeps the queue attached to the real automation lifetime even
when a resident FOS GUI accepts the request and the helper process exits.

The launch specification is passed directly to `QProcess` as:

- `program`: the explicit executable/interpreter;
- `arguments`: the explicit argument list;
- `workingDirectory`: the optional absolute working directory;
- standard input connected to the null device because jobs are non-interactive.

The process is asynchronous and non-blocking for the UI. stdout and stderr are
drained into separate files and exposed to the run-history dialog. A normal
exit with code 0 usually produces `exited`; a nonzero exit or process crash
produces `failed`. Managed MAA tasks add a post-exit output audit: each enabled
task needs a completed summary and an enabled Fight task needs a positive
battle count. Missing evidence produces `needs_attention` with error kind
`automation_incomplete`. Invalid configuration and failed-to-start paths also
produce a durable failed run. None of those outcomes writes a
`DailyCompletion` row.

Before a MAA or MAA_Punish job reaches `ExecutionService`, the dashboard runs a
separate preflight gate for both manual Run and the daily queue. MAA checks the executable,
exact task name, safe dry-run, and configured ADB device. For a managed task,
it first validates the editor settings and atomically writes a job-scoped
`control_plane_*` TOML file under the directory returned by `maa dir config`.
A failed preflight
opens a setup guide and does not create a Run record. The preflight is kept out
of `LaunchSpec`, so the real command remains exactly `run <task> --batch`.
When optional MuMu startup is enabled and that exact ADB device is absent, the
preflight asks `mumu-cli.exe` to launch the saved instance number and polls the
MAA profile address until it is ready or the configured timeout expires. These
blocking probes run on a worker thread while the progress UI remains responsive.
During the resulting MAA run, a separate asynchronous `mumu-cli info` watcher
checks the same saved instance. Two consecutive confirmations that its process
or Android has stopped cause `ExecutionService` to terminate, then force-stop
only the `QProcess` it owns. The durable run is recorded as failed with
`emulator_disconnected`; status-command errors alone never trigger termination.
The preflight also returns a run-scoped ownership flag only when it actually
issued `launch` and then reached ADB readiness. After a successful MAA run, the
optional cleanup uses that flag to run `shutdown` for the exact instance. An
already-running instance is never owned or closed. Cleanup runs asynchronously;
its failure is retained as a warning without changing MAA's successful result.
The cleanup is skipped for `needs_attention`, leaving the owned instance open
for diagnosis.
For MAA_Punish, preflight validates FOS, the selected saved configuration and
controller, its optional MuMu association, and the direct-run contract. The
same runtime watcher and ownership-scoped shutdown apply to its internal FOS
monitor process. After a fully verified task flow, that monitor can close the
configured FOS process before returning success. It first closes the exact
process it launched; when FOS reused an existing instance, Windows process
inspection requires an exact executable-path match rather than a broad image-
name kill. Failure to perform an explicitly requested FOS close returns a
nonzero monitor result, so the UI cannot claim a clean completion.

`ExecutionService` stores active state by run ID. Different jobs may run at the
same time, while a second start of the same job is rejected. An associated MuMu
executable and instance number form an exclusive resource, preventing MAA and
MAA_Punish jobs from controlling the same instance concurrently. Output files, handoff
state, watchdogs, errors, and finalization remain isolated per run.

The implementation is in
[`application/execution_service.py`](../src/game_control_plane/application/execution_service.py).

## UI, theme, and localization

The PySide6 interface uses one application-wide dark stylesheet with explicit
focus, hover, disabled, success, warning, and failure states. Status meaning is
always carried by text as well as color. The dashboard uses summary tiles and
responsive two-row card actions; the job editor uses scrollable grouped forms
so Chinese labels and high-DPI scaling do not force controls off screen.

`LanguageManager` keeps stable translation keys in code and stores only the
selected language code in `QSettings`. Simplified Chinese is the fallback and
first-launch default; English can be selected from the Settings menu and the
dashboard retranslates immediately. Database enum values, runner types, job
configuration, stdout/stderr, and third-party technical output are never
translated or rewritten. The implementation is in
[`ui/i18n.py`](../src/game_control_plane/ui/i18n.py) and
[`ui/theme.py`](../src/game_control_plane/ui/theme.py).

## Queue semantics

The dashboard's **Run Today's Dailies** action asks `QueueService` to take a
snapshot of jobs that are enabled and currently `pending`, in persisted
`queue_order`. It then:

1. starts exactly one job at a time;
2. records `trigger_type=queue` for those runs;
3. waits for the current `run_finished` signal before starting the next item;
4. continues after invalid configuration, failed-to-start, crashes, and
   nonzero exits; and
5. returns to idle after the snapshot is exhausted.

The queue remains sequential internally, but it can coexist with unrelated
manual runs. Its snapshot excludes jobs that are already running, and completion
signals are matched to the queue's exact run ID. When multiple queued MAA or MAA_Punish jobs
share an instance started during preflight, ownership is transferred to the
last queued consumer so the instance is not closed between those jobs.

The queue is deliberately in memory. It is not a database table, is not
resumed after restart, and has no cancel/stop or parallel-execution path. A
successful item still leaves its daily status pending until the user marks it
completed. See [`application/queue_service.py`](../src/game_control_plane/application/queue_service.py).

## Daily reset and completion

Each job stores an IANA `timezone_id` and a `reset_minute` measured from local
midnight. `daily_cycle.py` uses Python `zoneinfo` (with the `tzdata` dependency)
to convert the current local period start into a UTC ISO key. This handles the
timezone's offset rules without making the queue a scheduler.

The UI exposes **Mark completed** and **Mark pending**. These operations write
or delete a row in `daily_completions`; completion source is currently manual.
There is no automatic completion based on exit code, output, or a game-specific
verification result.

## Persistence and filesystem layout

`Database` applies numbered SQL files from
[`persistence/migrations`](../src/game_control_plane/persistence/migrations)
and records applied versions in `schema_migrations`. The current migration
creates games, jobs, runs, daily completions, and supporting indexes. The
PyInstaller spec explicitly includes the migration directory so a packaged
first launch can initialize SQLite.

The default Windows data root is `%LOCALAPPDATA%\GameAutomationControlPlane`.
It contains the database, `logs\app.log`, and one captured-run directory per
run. `GAME_CONTROL_PLANE_DATA_DIR` is an explicit development/test override.

At startup, log retention may remove captured run directories older than 30
days. It only accepts validated direct children of the configured runs root,
preserves the latest failed run for each job, and leaves SQLite run metadata in
place. Orphan directories are not removed.

## Historical non-goals for 0.1.0

- Built-in OneDragon adapter.
- End-to-end OK-WW execution or process-termination compatibility verification.
- End-to-end MAA task verification or assumptions about the current MaaCore
  configuration.
- Scheduling or background polling.
- Process-tree termination, cancellation, or a stop button.
- Parallel queue execution or persisted queue recovery.
- Automatic verification or automatic daily completion.
- Installer, updater, code signing, or release publication.

## Source map

- UI composition: [`ui/main_window.py`](../src/game_control_plane/ui/main_window.py)
- Integration boundary: [`integrations/base.py`](../src/game_control_plane/integrations/base.py)
- Current integration: [`integrations/custom_cli.py`](../src/game_control_plane/integrations/custom_cli.py)
- MAA contract integration: [`integrations/maa_cli.py`](../src/game_control_plane/integrations/maa_cli.py)
- MAA preflight: [`integrations/maa_preflight.py`](../src/game_control_plane/integrations/maa_preflight.py)
- OK-WW contract integration: [`integrations/ok_ww.py`](../src/game_control_plane/integrations/ok_ww.py)
- MAA_Punish contract integration: [`integrations/maa_punish.py`](../src/game_control_plane/integrations/maa_punish.py)
- FOS task-flow monitor: [`integrations/fos_runner.py`](../src/game_control_plane/integrations/fos_runner.py)
- App-data paths: [`platform/paths.py`](../src/game_control_plane/platform/paths.py)
- Packaging entry point/spec: [`packaging/entrypoint.py`](../packaging/entrypoint.py), [`packaging/game_control_plane.spec`](../packaging/game_control_plane.spec)
- Windows build wrapper and license placement: [`packaging/build_windows.ps1`](../packaging/build_windows.ps1)
