# GitHub publishing guide

The repository source code and original project artwork are licensed under
AGPL-3.0-only. Keep the root `LICENSE` file in the first public commit and in
every distributed Windows package.

This document records the original first-publication workflow. The repository
is public and the current source version is `v0.1.21`; use the steps below as a
checklist for future releases, not as a request to recreate the repository.

## 1. Protect the commit email

In GitHub, open **Settings → Emails**, enable **Keep my email addresses
private**, and copy the exact GitHub-provided `noreply` address shown there.
The format differs by account, so do not guess it.

Configure identity for this repository only:

```powershell
git config --local user.name "YOUR_PUBLIC_GITHUB_NAME"
git config --local user.email "YOUR_GITHUB_NOREPLY_ADDRESS"
git config --local user.useConfigOnly true
git config --local --list
```

This keeps the choice local to Hsiesta and avoids
changing commit identity in unrelated repositories.

## 2. Install and authenticate GitHub CLI

```powershell
winget install --id GitHub.cli
gh auth login --web --git-protocol https
gh auth status
```

Use the browser flow. Do not paste access tokens into project files, shell
history, issues, or chat messages.

## 3. Review and create the first commit

```powershell
git status --short
git add .
git diff --cached --check
git diff --cached --stat
git commit -m "Initial public release"
```

Confirm that no `dist`, `build`, virtual-environment, database, log, or account
configuration files appear in the staged list.

## 4. Repository name and historical bootstrap

The intended canonical GitHub repository is `wiwiwcwc/hsiesta`. When the GitHub
rename is carried out, rename the existing repository rather than creating a
second one: GitHub can then redirect old repository links and Git remotes.
After the rename, update local clones to the canonical remote:

```powershell
git remote set-url origin https://github.com/wiwiwcwc/hsiesta.git
```

If a new repository ever has to be bootstrapped from a separate working tree,
use:

```powershell
gh repo create hsiesta `
    --public `
    --source . `
    --remote origin `
    --description "休汐 Hsiesta: a Windows desktop console for mobile-game dailies"
git push -u origin main
```

Do not ask GitHub to create another README, `.gitignore`, or license when using
the website instead; this repository already contains all three.

## 5. Repository settings and future releases

- Enable private vulnerability reporting under **Security**.
- Protect `main` and require the Windows package workflow for pull requests.
- Keep Actions permissions read-only unless a later release workflow genuinely
  needs write access.
- Add repository topics such as `windows`, `pyside6`, `game-automation`, and
  `automation-dashboard`.
- Create the first GitHub Release only after its Windows ZIP and SHA-256,
  `Hsiesta-<version>-Setup.exe` installer and SHA-256, third-party notices, and
  clean-machine install/uninstall smoke test are verified together. The
  portable ZIP remains available for users who do not want an installed copy.
- The installer is built from the already-proven
  `dist\GameAutomationControlPlane` onedir output. Use
  `packaging\install_inno_setup.ps1` to obtain the pinned official Inno Setup
  7.1.0 compiler; it verifies the download hash and Authenticode publisher
  before execution. Do not add Inno Setup to Python dependencies.

Official references:

- https://docs.github.com/en/account-and-profile/how-tos/email-preferences/setting-your-commit-email-address
- https://cli.github.com/manual/gh_auth_login
- https://cli.github.com/manual/gh_repo_create
