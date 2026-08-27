# Copilot instructions

Read the repository-level [`AGENTS.md`](../AGENTS.md) before proposing or
editing code. It is the source of truth for architecture, integration
contracts, emulator ownership, queue concurrency, daily-completion semantics,
security boundaries, and release checks.

Quick reminders:

- This is a Windows-first PySide6 control plane, not a game client or a bundled
  copy of MAA, MAA_Punish/FOS, OK-WW, MuMu, MaaFramework, or OneDragon.
- Keep external launches explicit and non-blocking; do not introduce implicit
  shell commands or GUI-thread waits.
- Do not equate exit code zero with a verified daily success, and never mark a
  daily complete automatically from a run result.
- Preserve exact run IDs, MuMu instance ownership, and exact-path FOS cleanup;
  never broad-kill by process image name.
- Do not write user configuration during inspection, commit credentials/logs/
  databases/generated build output, or delete local pre-AGPL backups.
- Run focused tests for the change, then use `python -m pytest` and
  `python -m compileall -q src tests packaging` for release-facing changes.

For integration work, update `docs/integrations.md`, add contract tests, and
state whether evidence is local, upstream-documented, or live-game verified.
