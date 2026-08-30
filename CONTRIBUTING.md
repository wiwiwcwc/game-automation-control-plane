# Contributing

This repository is an early-stage project, and `v0.1.20` is its current source
version. By submitting a contribution,
you agree to license it under the project's
[GNU Affero General Public License v3.0 only](LICENSE).

## Development setup

Use Python 3.11 on Windows for the supported development and packaging path:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[test,build]" -c packaging\constraints.txt
```

Run the complete test suite with Qt's headless platform:

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
python -m pytest
python -m compileall -q src tests packaging
```

To exercise the desktop app, run `python -m game_control_plane` without the
smoke-test environment variable. To build and smoke-test a Windows package,
follow the commands in [README.md](README.md) or use the workflow in
[`.github/workflows/windows-package.yml`](.github/workflows/windows-package.yml).
The Windows build must use [`packaging/build_windows.ps1`](packaging/build_windows.ps1)
so the pinned Qt/PySide6 notices are checked and placed in the package root.
The optional installer layer consumes that onedir output via
[`packaging/build_installer.ps1`](packaging/build_installer.ps1); it is not part
of the Python development or pytest workflow.

## Change expectations

- Keep the game-first UI and the current explicit scope visible in user-facing
  behavior.
- Preserve the separation between process execution and manual
  `DailyCompletion`.
- Keep Custom CLI launches explicit: an executable/interpreter plus an argument
  list, never an implicit shell command.
- Add or update focused tests for behavior changes. The fixture CLI under
  [`tests/fixtures`](tests/fixtures) is safe for deterministic tests.
- For new integrations, document the primary upstream interface, the exact
  local version tested, failure behavior, and how daily completion remains
  explicit. See [integration status](docs/integrations.md).
- Label statements as locally verified or upstream-documented when the
  distinction matters. Do not turn an unverified product assumption into a
  supported adapter claim.
- Avoid adding credentials, real game-account data, captured logs, or generated
  `build/`/`dist/` output to a change.

## Documentation changes

Keep examples Windows-friendly and ensure paths and commands match the source.
Update [CHANGELOG.md](CHANGELOG.md) for user-visible changes and keep
[docs/architecture.md](docs/architecture.md) aligned with lifecycle or
persistence changes.
