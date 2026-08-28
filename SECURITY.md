# Security policy

This project is an early-stage Windows desktop application. It has no published
security-support commitment and no dedicated security email address.

## Reporting a vulnerability

If the GitHub repository exposes **Security → Report a vulnerability**, use that
private vulnerability-reporting flow and include the smallest useful
reproduction. GitHub's [private vulnerability reporting guidance](https://docs.github.com/en/code-security/how-tos/report-and-fix-vulnerabilities/report-privately)
describes the feature and its availability requirements.

If private reporting is not enabled, do not publish exploit details, tokens,
account data, or full captured logs in a public issue. Open a minimal issue that
asks the maintainers for a private reporting route, without including sensitive
details. Do not guess or invent an email address.

Please include, when safe:

- application/package version or commit;
- Windows and Python/runtime details;
- a concise reproduction and expected impact; and
- sanitized logs or screenshots only when they do not expose credentials,
  account identifiers, personal paths, or game data.

## Runtime safety notes

- Custom CLI jobs execute a user-selected absolute executable/interpreter with
  an explicit argument list; the application does not build an implicit shell
  command.
- Run logs can contain arbitrary output from the selected program. Treat the
  application data directory as potentially sensitive and restrict access to
  it appropriately.
- Never commit database files, captured run logs, credentials, or real account
  configuration to the repository.
