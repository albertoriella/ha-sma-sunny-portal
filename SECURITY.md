# Security policy

## Reporting a vulnerability

Do not disclose vulnerabilities, credentials, tokens, cookies, private plant
identifiers, or raw customer telemetry in a public issue.

Until private vulnerability reporting is enabled for this repository, contact
the maintainer privately through the contact method listed on the maintainer's
GitHub profile. Include only the minimum information needed to reproduce the
problem and redact all credentials.

## Credential handling principles

- Access and refresh tokens must never be logged.
- Rotated refresh tokens must be persisted atomically before further API work.
- Diagnostics must redact account, plant, component, and session identifiers.
- Tests must use synthetic fixtures rather than captured customer responses.
- Authentication failures must stop refresh retries and initiate reauthentication.
