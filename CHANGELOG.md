# Changelog

All notable changes to this project are documented in this file. The project
uses [Semantic Versioning](https://semver.org/).

## [0.1.0] - 2026-10-08

### Added

- Manual config flow and reauthentication for one selected ennexOS plant per
  SMA account.
- Serialized refresh-token rotation with private atomic persistence.
- Normalized current-day and next-day forecast ingestion.
- Native Home Assistant forecast sensors and Energy dashboard solar forecast.
- Private bounded SQLite archive for forecast vintages and measurements.
- Authenticated history API with latest, day-ahead, and rolling provenance.
- PV and consumption accuracy metrics: energy error, bias, MAE, RMSE, and WAPE.
- Optional SMA Energy Live card with calendar navigation, selectable curves,
  shared zero, Energy palette, forecast provenance, and accuracy summary.
- English and Italian translations, synthetic fixtures, and network-free tests.

### Security

- Access tokens remain in memory and refresh tokens are excluded from logs,
  entities, diagnostics, fixtures, and source control.
- Config-entry removal deletes the private token store and forecast archive.
- CI validates the repository with Hassfest, HACS, Ruff, pytest, JavaScript
  checks, and a full-history Gitleaks scan.

### Known limitations

- The backend is an undocumented Sunny Portal UI API and may change without
  notice.
- Initial setup requires a refresh token and plant ID obtained locally from a
  browser developer session.
- Multi-plant selection within one SMA account is not implemented.

[0.1.0]: https://github.com/albertoriella/ha-sma-sunny-portal/releases/tag/v0.1.0
