# Security policy

## Supported version

Security fixes are currently made only on the latest public beta. Older beta
builds are not supported after a replacement is published.

## Report a vulnerability

Do not open a public Issue for credentials, path traversal, unsafe file writes,
privacy leaks, or another exploitable defect. Use **Report a vulnerability** in
the repository's GitHub Security tab. Include the affected version, a minimal
reproduction, impact, and suggested mitigation. Do not attach private artwork,
real API keys, or confidential projects.

If private vulnerability reporting is unavailable, open a public Issue that
contains no exploit detail or sensitive data and asks the maintainer to enable a
private channel.

## Credentials and logs

GATalk stores saved API keys in Windows Credential Manager. The project, logs,
diagnostic export, and Git history must not contain credentials. The public
release audit scans the complete tracked history for common key and private-path
patterns, but pattern scanning cannot prove that every possible secret is absent.

## Scope

Provider outages, quota errors, model output quality, and third-party service
policy changes are not application vulnerabilities unless GATalk exposes data or
performs an unauthorized request.
