# Security policy

## Supported versions

Only the latest published release receives security fixes. The `main` branch is
development code and may change before the next release.

## Reporting a vulnerability

Do not disclose vulnerabilities, credentials, tokens, cookies, private plant
identifiers, or raw customer telemetry in a public issue.

Use [GitHub private vulnerability reporting](https://github.com/albertoriella/ha-sma-sunny-portal/security/advisories/new).
If that form is unavailable, contact the maintainer privately through the
contact method on the maintainer's GitHub profile. Include only the minimum
information needed to reproduce the problem and redact all credentials.

If a live token or session value was exposed, revoke or replace it immediately.
Do not wait for a project response before rotating a compromised credential.

## Credential handling principles

- Access and refresh tokens must never be logged.
- Rotated refresh tokens must be persisted atomically before further API work.
- Diagnostics must redact account, plant, component, and session identifiers.
- Tests must use synthetic fixtures rather than captured customer responses.
- Authentication failures must stop refresh retries and initiate reauthentication.
- The portal browser and Home Assistant must never rotate the same refresh-token
  chain concurrently.
