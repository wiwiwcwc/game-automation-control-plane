# Integration status

This page distinguishes two kinds of evidence:

- **Locally verified** means the behavior is implemented in this repository and
  covered by its current tests or a direct local check.
- **Upstream-documented** means an external project's own documentation or
  repository describes an interface. It does not mean Hsiesta has
  implemented or tested that interface.

## Summary

| Integration | Status in this project | Evidence |
| --- | --- | --- |
| Custom CLI | Supported | Implemented in the registry; configuration validation and QProcess execution are locally tested. |
| MAA GUI / `maa-cli` | Managed daily-task editor, result audit, and MuMu ownership-aware startup/cleanup; live full daily unverified | A locally generated managed task passes `run control_plane_daily_job_2 --batch --dry-run` with all six task groups. Tests cover generation, current Fight parameters, incomplete-result detection, and cleanup suppression. |
| MAA_Punish / FOS | Guided saved-config launch, log-based completion, and optional exact-process cleanup; live task observed | A live FOS task reached the complete-success evidence sequence and ownership-based MuMu shutdown. Tests cover command handoff, exact FOS cleanup, cleanup failure, fresh-log evidence, and emulator ownership. |
| OK-WW | Locally verified launcher handoff and close-option wiring | This repository validates an explicit executable and positive task index, builds `-t <index>` with optional `-e`, and follows the Windows launcher to its direct `pythonw.exe`/`python.exe` worker inside the same OK-WW installation. |
| Zenless Zone Zero OneDragon | Launcher adapter, GUI entry, exact owned-run stop, and conservative preflight; live game unverified | Local tests cover launcher discovery, Runtime/classic layouts, explicit arguments, no-argument GUI launch, exact PID/run stop, editor round-trip, and exit-0 review semantics. The installed upstream version, account existence, and full daily flow still need user-side verification. |

## Custom CLI — supported

The registered Custom CLI integration uses configuration version 1. Its
minimum shape is:

```json
{
  "config_version": 1,
  "executable_path": "C:\\Python311\\python.exe",
  "arguments": [
    "C:\\Automation\\daily_tasks.py",
    "--profile",
    "main"
  ],
  "working_directory": "C:\\Automation"
}
```

The executable/interpreter path must be absolute and point to a file. The
optional working directory must be absolute and point to a folder. Arguments
are strings and are passed as a list to `QProcess`; the integration does not
construct or invoke an implicit shell command.

PowerShell scripts therefore use an explicit interpreter and separate
arguments, for example:

```text
Executable: C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe
Arguments:
-NoProfile
-File
C:\Automation\daily.ps1
```

The implementation is in
[`integrations/custom_cli.py`](../src/game_control_plane/integrations/custom_cli.py).
The execution boundary is described in the
[architecture document](architecture.md).

## MAA GUI / `maa-cli` — contract adapter, no end-to-end verification

### Verified Windows contract

The verified Windows contract for this adapter is WinGet package
`MaaAssistantArknights.maa-cli` version 0.7.5. Its installed executable is
`maa-cli.exe` under the package directory below `%LOCALAPPDATA%\Microsoft\WinGet\Packages`.
The observed contract is:

- `maa-cli.exe --version` prints `maa 0.7.5`;
- `maa-cli.exe version` reports `maa-cli v0.7.5` and MaaCore `v6.16.8`;
- `maa-cli.exe list` includes the `daily` task; and
- the documented noninteractive launch is `run <TASK> --batch`.

The local `daily` configuration passes `run daily --batch --dry-run` after two
invalid template parameters were corrected: default infrastructure shifting no
longer declares custom mode `10000` without a filename, and current/last-stage
farming uses an empty `stage` value instead of the unsupported literal
`LastBattle`. MuMu instance 1 was then connected and identified through ADB at
`127.0.0.1:5557`; a full live daily run remains unverified.

A generated managed configuration named `control_plane_daily_job_2` also
passes `run control_plane_daily_job_2 --batch --dry-run` and lists StartUp,
Recruit, Infrast, Mall, Fight, and Award. This verifies the generated task
shape without launching the game; it does not claim that a full live daily has
completed successfully.

### Adapter behavior implemented here

The registered `maa_cli` integration keeps configuration version 1 for
backward compatibility. An external task has this minimum shape:

```json
{
  "config_version": 1,
  "executable_path": "C:\\Path\\To\\maa-cli.exe",
  "task_name": "daily"
}
```

New jobs instead use `task_mode: "managed"` and a `managed_daily` object. The
editor can configure startup, recruitment count, infrastructure, credit and
shopping behaviors, stage, total fight count, consecutive proxy count,
medicine, expiring medicine, Originite, awards, and mail. Preflight resolves
the active configuration directory through `maa dir config`, validates that
the generated task name is application-owned, and atomically replaces only
that job's task TOML before running the same list and dry-run checks. Existing
external TOML tasks are never overwritten or silently migrated.

MuMu automatic startup and runtime monitoring are optional and backward
compatible. When enabled, the same configuration also records the MuMu
command-tool path, an exact instance number, and a 30–600 second startup timeout.
The command contract verified locally is
`mumu-cli.exe control --vmindex <n> launch`. A zero exit code means the launch
request was accepted, so the preflight still polls the ADB address from MAA's
profile and only proceeds after that exact serial reports `device`. An
already-ready device is never relaunched.

The same editor can enable close-after-success. The preflight marks ownership
only when Hsiesta issued the launch request and the configured ADB device
then became ready. Only that run-scoped proof allows
`mumu-cli.exe control --vmindex <n> shutdown` after MAA exits normally with code
zero. An instance that was already running is left open. The installed MuMu
command tool's help output was checked locally for the exact `shutdown`
subcommand. Cleanup failure is shown as a warning and does not rewrite the MAA
task outcome as failed.

While MAA is running, a non-blocking watcher executes
`mumu-cli.exe info --vmindex <n>` every two seconds. Two consecutive responses
confirming that the associated instance or Android has stopped terminate only
the `maa-cli` process owned by that run. Temporary command failures are retried
and do not stop MAA.

The editor discovers `maa-cli` with `shutil.which("maa-cli")` first, then
checks the known WinGet package directory under `%LOCALAPPDATA%`. The path
remains visible and editable. The launch spec is exactly
`run`, `<task_name>`, `--batch`; no profile, address, dry-run, or other
option is added to the real launch. A separate preflight checks `--version`,
the exact task returned by `list`, `run <task> --batch --dry-run`, and the ADB
device in `profiles/default.toml`. TCP profiles are connected through their
configured `adb.exe` before `adb devices -l` is evaluated. Failures open a
four-step guide and do not create a Run record. Emulator polling runs on a
worker thread, so its progress window remains responsive during startup.

After any MAA task exits with code zero, Hsiesta does not treat the run as a
verified daily success. For a managed task, the result auditor checks the
maa-cli summary for every enabled top-level task. If Fight is enabled, it
additionally requires a positive `Fight ... times` result. A missing,
unstarted, zero-battle, or task-chain-error result becomes `needs_attention`
instead of `exited`; the diagnostic output is retained and ownership-based
emulator cleanup is skipped. These outcomes persist stable diagnostic codes and
parameters (`maa_managed_incomplete` with missing/unfinished/zero-battle/task-
chain flags), which the bilingual UI formats while retaining the raw audit
summary as technical detail. Captured stdout/stderr is not modified with a
Hsiesta banner. For an external task, Hsiesta cannot know which
steps its user-maintained TOML intends to run, so even a clean exit becomes
`needs_attention` with a manual log-review prompt; cleanup is skipped for the
same reason. Neither path changes `DailyCompletion`, which remains a manual
confirmation. The external result uses `maa_external_unverified` even if the
job is later edited to managed mode; history reads the persisted run snapshot.

### Upstream documentation

The [official MAA CLI usage documentation](https://docs.maa.plus/en-us/manual/cli/usage.html)
and [`maa-cli` repository](https://github.com/MaaAssistantArknights/maa-cli)
describe its commands and task configuration. The separate
[MAA repository](https://github.com/MaaAssistantArknights/MaaAssistantArknights)
documents the desktop project. These upstream references support the contract
description above; they are not proof that the current user configuration can
run the `daily` task successfully.

## MAA_Punish / FOS — guided adapter with observed live task completion

MAA_Punish ships its Windows workflow through the MFW GUI executable renamed
to `FOS.exe`; it does not expose a separate headless CLI. MFW documents the
direct-run contract used by this adapter:

```text
FOS.exe --direct-run --reuse-existing --config-id <configuration-id>
```

The editor discovers an existing FOS installation conservatively, reads only
its `config/configs/*.json` metadata, and requires the user to choose an exact
saved configuration. For an Android controller it also reads the saved ADB
path/address and MuMu instance metadata. The local configuration currently
selected for verification identifies MuMu instance `0` and ADB endpoint
`127.0.0.1:16384`. These are configuration observations, not proof of a
successful live game task.

The helper process may return zero after forwarding a request to a resident
FOS GUI. Hsiesta therefore runs a packaged internal monitor, snapshots
the current end of `debug/gui.log`, and accepts success only after fresh
evidence for the complete high-level sequence: `TASK_FLOW_START`, the
all-tasks-complete message, `task_flow_finished` with `manual_stop=False`,
`need_stop=False`, and `tasks_started=True`, followed by
`TASK_FLOW_STOP manual=False`. A task-flow exception, task failure, stop
request, manual stop, missing start evidence, or early FOS process exit is a
failed run. Old successful log entries cannot satisfy a new run.

Optional MuMu startup uses the saved instance association. Preflight can start
an inactive instance, wait until both its process and Android are ready, and
return run-scoped ownership. The runtime watcher and optional shutdown use the
same exact instance. An already-running emulator is never owned or closed.

The separate `close_fos_after_run` option defaults to enabled. Only after the
full task-flow evidence succeeds does the internal monitor close FOS, before
the optional MuMu shutdown is started. It first targets the process handle
created for this request. If the request was handed to an already-running FOS,
the fallback enumerates Windows processes and requires the full image path to
equal the configured `FOS.exe`; it never performs a broad name-only kill. A
requested close failure returns a nonzero result rather than displaying a
clean completion. Disable the option when FOS should remain open for reuse.

The [MAA_Punish repository](https://github.com/overflow65537/MAA_Punish) and
[MFW-PyQt6 command-line documentation](https://github.com/overflow65537/MFW-PyQt6#%E5%B8%B8%E7%94%A8%E5%91%BD%E4%BB%A4%E8%A1%8C%E5%8F%82%E6%95%B0)
are the primary upstream references. The adapter and failure-safe evidence
parser are locally tested. A later user-run Punishing: Gray Raven task reached
the complete-success sequence and closed its owned emulator; exact FOS process
cleanup was then added and verified without launching another game task.

## OK-WW — contract adapter, no end-to-end verification

### Verified contract boundary

The official README documents the noninteractive command
`ok-ww.exe -t 1 -e`: `-t`/`--task` is a 1-based task
index, and `-e`/`--exit` requests exit after completion. This project uses that
contract only; it does not update OK-WW, start Wuthering Waves, or launch the
executable during onboarding or tests.

A local test installation contained multiple version indicators and a stale
uninstall entry. Those observations do not establish a generally
runnable/version-compatible installation, so the end-to-end path remains
unverified.

### Adapter behavior implemented here

The registered `ok_ww` integration uses configuration version 1:

```json
{
  "config_version": 1,
  "executable_path": "C:\\Tools\\ok-ww\\ok-ww.exe",
  "task_index": 1,
  "close_game_after_run": true
}
```

The task index must be a positive integer. The launch spec is `-t`,
`<task_index>`, adding `-e` only when close-after-task is enabled, and its
working directory is the executable's parent. The editor labels the game
**Wuthering Waves**, defaults the index to `1`, and keeps the executable path
editable. Configurations saved before the option existed default to enabled to
preserve their prior launch behavior.

Discovery checks an existing `ok-ww.exe` on PATH first, then an existing path
from `OK_WW_EXECUTABLE`, then likely Windows desktop/Start Menu shortcuts by
reading their link data without COM or UI automation. It only accepts an
existing target named `ok-ww.exe`/`ok_ww.exe`; it does not use the stale
uninstall registry entry or assume a `%LOCALAPPDATA%` package location.

Upstream has had a historical closed regression involving `-e`. Focused
project tests validate both launch argument variants and onboarding without
starting OK-WW; they do not prove process-termination behavior for every
upstream version.

The [OK-WW upstream repository](https://github.com/ok-oldking/ok-wuthering-waves)
is the primary reference for the documented CLI contract. Its current README
and release state are evidence about upstream behavior, not proof that the
local executable or game client will complete a task successfully.

## Zenless Zone Zero OneDragon — launcher adapter, live game unverified

This release adds a focused adapter for **Zenless Zone Zero OneDragon**. It is
not a generic OneDragon integration and does not claim support for other games.
The adapter connects to an existing installation only; it never downloads or
bundles OneDragon, its embedded runtime, models, game files, or user account
configuration. No OneDragon YAML is read or rewritten, and no account allowlist
is inferred locally.

### Upstream contract used by this adapter

The upstream source consulted on 2026-08-28 was the `main` branch of the
[official ZenlessZoneZero-OneDragon repository](https://github.com/OneDragon-Anything/ZenlessZoneZero-OneDragon).
The local adapter schema is version `1`; no exact installed OneDragon build was
available for this repository's release, so the real installed version remains
an explicit user-side verification boundary.

The official launcher sources document these arguments:

```text
OneDragon-RuntimeLauncher.exe -o [-i 1,2] [-c]
OneDragon-Launcher.exe        -o [-i 1,2] [-c]
```

`-o` selects the OneDragon application entry point. `-i` accepts a
comma-separated list of positive account-instance indices; leaving it blank
lets OneDragon use its `active_in_od` account. The editor rejects non-numeric,
zero, negative, empty, and duplicate entries, then passes normalized values to
the launcher. Whether an index exists is left to OneDragon. `-c` asks
OneDragon itself to close the game internally after it finishes.

The primary references are the upstream
[launcher base argument parser](https://github.com/OneDragon-Anything/ZenlessZoneZero-OneDragon/blob/main/src/one_dragon/launcher/launcher_base.py),
[executable launcher](https://github.com/OneDragon-Anything/ZenlessZoneZero-OneDragon/blob/main/src/one_dragon/launcher/exe_launcher.py),
[runtime launcher](https://github.com/OneDragon-Anything/ZenlessZoneZero-OneDragon/blob/main/src/zzz_od/win_exe/runtime_launcher.py),
[classic launcher](https://github.com/OneDragon-Anything/ZenlessZoneZero-OneDragon/blob/main/src/zzz_od/win_exe/launcher.py),
and [RuntimeLauncher layout notes](https://github.com/OneDragon-Anything/ZenlessZoneZero-OneDragon/blob/main/docs/develop/one_dragon/runtime_launcher.md).

### Discovery and preflight boundary

Discovery checks PATH, the explicit `ZZZ_ONEDRAGON_EXECUTABLE` environment
variable, and a small set of common Desktop/Downloads/Start Menu locations.
It prefers the exact `OneDragon-RuntimeLauncher.exe` name and falls back to
the exact `OneDragon-Launcher.exe` name. It does not scan an entire drive,
search arbitrary process names, or inspect uninstall metadata.

For RuntimeLauncher, the selected executable's parent must contain adjacent
`.runtime` and `src` directories, matching the upstream package layout. For
the classic launcher, the check accepts either the official Full-Environment
root pair `config/project.yml` and `config/repository.yml`, or the complete
`resources/config/project.yml` and `resources/config/repository.yml`
compatibility layout. It never combines one file from each layout, reads YAML
contents, or asks the user to move YAML files. The preflight constructs an
explicit argument list and working directory but never starts the game or
launcher.

### GUI and automatic-run boundary

The OneDragon task card exposes two deliberately separate actions. **Open
OneDragon GUI** launches the exact configured launcher from its parent
directory with no arguments, which is the upstream GUI entry point. It is a
detached UI action: it creates no Hsiesta `Run`, does not enter the daily queue,
and is not tracked for completion. The user can start, pause, or inspect the
task in that official GUI. **Run automatically** uses the documented `-o`
arguments above and is headless. Hsiesta does not provide a GUI-display switch
or fake an attach protocol; the GUI action is blocked while the same task has
an active or queued automatic run so two independent OneDragon contexts are
not launched accidentally. This protection only covers Hsiesta's own task
card: a detached GUI is not tracked, and a GUI opened outside Hsiesta cannot
be detected or reverse-blocked. Close the official GUI before starting the
headless automatic run.

### Result and safety boundary

OneDragon has no reliable external completion protocol that this release can
audit. A clean launcher exit therefore becomes `needs_attention`, persists the
stable `onedragon_unverified` diagnostic, retains stdout/stderr, and never
writes `DailyCompletion`; the UI shows “进程已正常结束 · 结果未验证” /
“Process ended normally · result unverified” while the user must review the
OneDragon log and use **Mark completed** if the in-game daily really finished.
When the user presses **Stop**, Hsiesta first requests a graceful QProcess stop.
If the launcher remains alive, it records the root PID, full executable path,
and process-creation token captured at launch, then uses a short-grace native
PID-tree stop only after revalidating that identity. On Windows, the stop
holds handles opened from one trusted root snapshot, checks every held
creation token and continuous root-relative parent chain, and terminates
child-first/root-last through those same handles. Each Windows capture attempt
gets a system FILETIME cutoff before its snapshot; every root/descendant opened
from that snapshot must have a creation token no newer than the cutoff. A PID
from that snapshot is not accepted merely because a replacement has the same
parent or image. A new descendant found by the fresh parent-chain check causes
all handles to close and the entire capture to retry with a new cutoff, up to a
small fixed limit; persistent churn is fail-closed. After termination, a fresh
snapshot must show that the owned root and all descendants are gone, otherwise
the result is a stop failure/cleanup warning. A PID reuse, changed parent
chain, handle/query failure, or termination failure is fail-closed. A stop is
scoped to the exact run ID and its owned launcher tree; it is never a
name-based kill and never affects another task. If the root PID cannot be
revalidated, the run is recorded as a stop failure and any external process is
left for manual review. “Owned tree” means the currently validated tree for one
capture attempt, not a historical list of PIDs.
The adapter does not follow an asynchronous worker, close the game itself, take
over the game window, or modify OneDragon YAML and account settings. If the
launcher exits while an unverified worker may remain, Hsiesta records
`needs_attention` and does not follow or terminate that worker. It does not
infer completion from `ZenlessZoneZero.exe` closing. The complete live ZZZ
daily flow and behavior of every installed OneDragon version remain
unverified.

## Evidence required for future integration work

An additional adapter, or a claim of end-to-end support for this MAA adapter,
should not be added from a product name alone. It should have at least:

1. a current, primary upstream invocation/configuration reference;
2. a locally available and version-identified executable or SDK;
3. a validation path that produces a clear failed run when the dependency is
   missing or incompatible;
4. a deterministic launch and output-capture test; and
5. an explicit decision about how success, failure, and daily completion map to
   Hsiesta without silently marking a daily complete.
