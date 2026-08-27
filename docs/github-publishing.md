# GitHub publishing guide

The repository source code and original project artwork are licensed under
AGPL-3.0-only. Keep the root `LICENSE` file in the first public commit and in
every distributed Windows package.

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

This keeps the choice local to Game Automation Control Plane and avoids
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

## 4. Create the repository

Recommended name: `game-automation-control-plane`.

For a public repository created from this existing working tree:

```powershell
gh repo create game-automation-control-plane `
    --public `
    --source . `
    --remote origin `
    --description "Windows control plane for multiple game automation tools"
git push -u origin main
```

Do not ask GitHub to create another README, `.gitignore`, or license when using
the website instead; this repository already contains all three.

## 5. Repository settings after the first push

- Enable private vulnerability reporting under **Security**.
- Protect `main` and require the Windows package workflow for pull requests.
- Keep Actions permissions read-only unless a later release workflow genuinely
  needs write access.
- Add repository topics such as `windows`, `pyside6`, `game-automation`, and
  `automation-dashboard`.
- Create the first GitHub Release only after its Windows ZIP, checksum,
  third-party notices, and clean-machine smoke test are verified together.

Official references:

- https://docs.github.com/en/account-and-profile/how-tos/email-preferences/setting-your-commit-email-address
- https://cli.github.com/manual/gh_auth_login
- https://cli.github.com/manual/gh_repo_create
