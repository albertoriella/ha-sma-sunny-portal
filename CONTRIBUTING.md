# Contributing

Thank you for helping improve SMA Sunny Portal Forecast.

## Before opening an issue

- Search existing issues first.
- Confirm the problem still occurs on the newest published release.
- Include the Home Assistant version, integration version, forecast mode, and
  concise reproduction steps.
- Share only the smallest relevant, redacted log excerpt.

Never attach refresh or access tokens, cookies, authorization headers, HAR
files, raw Sunny Portal responses, plant/account/component identifiers,
geographic coordinates, or personal telemetry. Use
[the security policy](SECURITY.md) for suspected vulnerabilities.

## Development setup

Use Python 3.14 and Node.js for the frontend checks:

```bash
python -m venv .venv
.venv/bin/python -m pip install --requirement requirements-test.txt
.venv/bin/python -m ruff format --check .
.venv/bin/python -m ruff check .
.venv/bin/python -m pytest
node --check custom_components/sma_sunny_portal/frontend_assets/sma-sunny-portal-energy-card.js
node tests/test_frontend_registration.mjs
```

Tests must be deterministic and network-free. Create synthetic fixtures that
cannot be mistaken for real customer data. Do not sanitize a captured response
and commit it: model the minimum contract from scratch instead.

## Pull requests

1. Keep each change focused and explain the user-visible behavior.
2. Add or update tests for every behavior change.
3. Update documentation and the changelog when appropriate.
4. Run the complete validation suite before pushing.
5. Preserve entity unique IDs and normalized models unless the change includes
   an explicit migration strategy.

Transport-specific response dictionaries belong behind the backend/parser
boundary. Entities, history, and frontend APIs should consume normalized models
so a future SMA-authorized OAuth/API backend can replace the experimental one
without renaming entities.

Maintainers create releases and change the version in `manifest.json`. Pull
requests should not independently bump the release version unless requested.
