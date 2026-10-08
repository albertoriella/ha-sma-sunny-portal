# SMA Sunny Portal Forecast for Home Assistant

[![Validate](https://github.com/albertoriella/ha-sma-sunny-portal/actions/workflows/validate.yml/badge.svg)](https://github.com/albertoriella/ha-sma-sunny-portal/actions/workflows/validate.yml)
[![License](https://img.shields.io/github/license/albertoriella/ha-sma-sunny-portal)](LICENSE)

An independent Home Assistant custom integration for photovoltaic generation,
household-consumption, weather, and surplus forecasts from Sunny Portal powered
by ennexOS.

> [!WARNING]
> Version 0.1 is an advanced preview. It uses an undocumented Sunny Portal UI
> API and a manually obtained rotating refresh token. The API can change
> without notice, and this project is not affiliated with or supported by SMA.

## What works in v0.1.0

- four native entities for the next predicted interval: photovoltaic power,
  consumption power, surplus power, and its UTC timestamp;
- native photovoltaic forecast support in the Home Assistant Energy dashboard;
- current-day and next-day forecast ingestion every 15 minutes;
- a private SQLite archive of forecast vintages and actual measurements;
- `latest`, `day_ahead`, and `rolling` historical forecast selection;
- photovoltaic and consumption accuracy metrics, including energy error, bias,
  MAE, RMSE, and WAPE;
- an optional, dependency-free **SMA Energy Live** Lovelace card with calendar
  navigation, selectable curves, shared zero, and Home Assistant Energy colors;
- automatic refresh-token rotation, private atomic token storage, and a Home
  Assistant reauthentication flow.

The current setup supports one selected plant for each SMA account. Different
SMA accounts can create separate entries, but selecting several plants from one
account is not implemented yet. Automatic account discovery, browser OAuth,
daily forecast totals, and recommendation windows are future work.

## Requirements

- Home Assistant 2026.9.0 or newer;
- an account for [Sunny Portal powered by ennexOS](https://ennexos.sunnyportal.com/);
- access to the browser developer tools for the temporary manual setup;
- HACS is optional but is the recommended installation and update method.

Version 0.1.0 was developed and live-tested with Home Assistant 2026.9.4.

## Installation

### HACS custom repository

The repository must be public before HACS can install it. Until it is included
in HACS's default catalogue, add it as a custom repository:

1. Open **HACS** and select **Integrations**.
2. Open the three-dot menu and choose **Custom repositories**.
3. Enter `https://github.com/albertoriella/ha-sma-sunny-portal` and select
   **Integration** as the category.
4. Add the repository, find **SMA Sunny Portal Forecast**, and install it.
5. Restart Home Assistant.

[![Open your Home Assistant instance and add this HACS repository](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=albertoriella&repository=ha-sma-sunny-portal&category=integration)

### Manual installation

1. Download a GitHub release or clone the repository.
2. Copy `custom_components/sma_sunny_portal` into the Home Assistant
   `config/custom_components` directory.
3. Restart Home Assistant.

Do not copy the repository root or the test suite into `custom_components`.

## Configuration

Read the [manual authentication guide](docs/manual-authentication.md) before
starting. It explains how to obtain the numeric plant ID and the newest refresh
token locally without publishing either value.

Then open **Settings → Devices & services → Add integration**, search for
**SMA Sunny Portal Forecast**, and enter the two values. The setup validates the
account and plant before creating the entry. The submitted refresh token is
rotated immediately, saved in a private config-entry-scoped Home Assistant
store, and removed from the config-entry data.

> [!IMPORTANT]
> A refresh token is a credential. Never include it, the plant ID, cookies, HAR
> files, raw portal responses, or unredacted telemetry in an issue. Do not keep
> using the captured browser session after Home Assistant starts managing that
> refresh-token chain.

### Energy dashboard

After the integration has loaded, open the Energy dashboard configuration and
select the SMA config entry as the solar forecast provider for the relevant
solar source. The provider uses SMA's hourly photovoltaic-energy recommendation
values and includes tomorrow's curve before local midnight when SMA supplies it.

## Optional SMA Energy Live card

The card is shipped with the integration; no separate JavaScript download is
needed. In normal Lovelace storage-resource mode, the integration creates and
maintains one module resource automatically. After the first installation or a
card update, restart Home Assistant and perform one hard browser refresh.

Open a dashboard editor, select **Add card**, and search for
**SMA Energy Live**. With one loaded config entry, the minimal YAML is:

```yaml
type: custom:sma-sunny-portal-energy-card
```

The visual editor can select an entry, initial forecast mode, and custom title.
The card provides:

- previous/next day buttons, a calendar input, and a Today shortcut;
- one shared-axis graph with a common physical zero;
- solid actual and dashed forecast curves for PV and consumption;
- orange PV, theme-aware neutral consumption, blue deficit/import, and purple
  surplus/export;
- a clickable legend with every curve initially visible;
- `latest`, `day_ahead`, and `rolling` forecast modes;
- forecast provenance, archive bounds, and an expandable accuracy summary;
- English and Italian labels following the Home Assistant language.

The integration deliberately does not create or overwrite a dashboard. Add the
card wherever it is useful. If Lovelace resources are explicitly managed in
YAML, declare the module manually:

```yaml
resources:
  - url: /sma_sunny_portal/frontend/sma-sunny-portal-energy-card.js?v=3
    type: module
```

## Forecast history and accuracy

The integration stores full forecast curves outside Recorder so that every
forecast keeps both its issue time and target time. It archives at most one
complete forecast vintage per hour and upserts actual measurements on every
coordinator update. Forecasts are retained for 90 days and measurements for
400 days.

The authenticated `sma_sunny_portal/history` WebSocket command and the bundled
card support:

- `latest`: newest archived forecast vintage covering the selected date;
- `day_ahead`: newest vintage issued no later than local midnight;
- `rolling`: newest forecast that was available before each target interval.

History begins with the first successful update after archive support is
installed. Earlier curves cannot be reconstructed from Recorder. The first
archive day can legitimately have no `day_ahead` curve because no pre-midnight
snapshot exists.

Accuracy includes only forecast targets that already have an actual measurement
at exactly the same timestamp. Future points do not reduce coverage, the current
day is marked partial, and percentage metrics remain unavailable when measured
energy is zero.

## Data and security

- The short-lived access token exists only in memory.
- The rotating refresh token is stored in a private Home Assistant `Store` and
  is never exposed as an entity or frontend response.
- The history database is config-entry scoped, mode `0600`, and contains no
  authentication tokens.
- Full curves remain outside Recorder-backed entity attributes.
- Tests and fixtures are synthetic; captured customer responses are forbidden.
- Removing the config entry deletes its private token store and history archive.

See [SECURITY.md](SECURITY.md) for vulnerability reporting and
[the architecture notes](docs/architecture.md) for the design boundaries.

## Updating and removal

HACS can install updates after a GitHub release is published. Restart Home
Assistant after updating; perform a hard browser refresh when the card asset
version changes.

For complete removal:

1. remove each SMA Sunny Portal Forecast config entry in Home Assistant;
2. remove any dashboard cards using `custom:sma-sunny-portal-energy-card`;
3. uninstall the integration through HACS or delete its component directory;
4. if it remains, remove the SMA module from **Settings → Dashboards →
   Resources**.

Removing the config entry first is important because that is when Home
Assistant asks the integration to delete its private token and history files.

## Troubleshooting

- **Invalid authentication:** capture a new token from a newly authenticated,
  dedicated browser session and complete the reauthentication flow.
- **Card custom element does not exist:** confirm the module resource is present,
  restart Home Assistant, and hard-refresh the browser once.
- **No historical curve:** choose `rolling` or `latest` and select a date on or
  after archive installation; `day_ahead` needs a pre-midnight snapshot.
- **No tomorrow forecast:** SMA may not have published the following day yet.
  The integration merges today and tomorrow whenever both are available.

Check logs for `sma_sunny_portal`, but redact identifiers and telemetry before
sharing excerpts.

## Development

```bash
python -m pip install --requirement requirements-test.txt
python -m ruff format --check .
python -m ruff check .
python -m pytest
node --check custom_components/sma_sunny_portal/frontend_assets/sma-sunny-portal-energy-card.js
node tests/test_frontend_registration.mjs
```

Contributions are welcome; read [CONTRIBUTING.md](CONTRIBUTING.md) first. See
[CHANGELOG.md](CHANGELOG.md) for release history. Maintainers can use the
[release checklist](docs/release-checklist.md) for public releases.

## Important limitations

- The undocumented Sunny Portal UI API can change or disappear without notice.
- A seamless browser-based login requires an OAuth client authorized by SMA.
- The browser and Home Assistant must not rotate the same refresh-token chain
  concurrently.
- One SMA account currently supports one selected plant in Home Assistant.
- The integration is not a control interface and does not write plant settings.

## Trademark notice

This independent project is not affiliated with, endorsed by, or supported by
SMA Solar Technology AG. SMA, Sunny Portal, Sunny Home Manager, and ennexOS are
trademarks or product names of their respective owner. Their names are used only
to describe compatibility.

## License

Licensed under the [Apache License 2.0](LICENSE).
