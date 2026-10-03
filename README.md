# SMA Sunny Portal Forecast for Home Assistant

An experimental Home Assistant custom integration for importing photovoltaic
generation, household consumption, weather indicators, and energy-surplus
forecasts from SMA Sunny Portal powered by ennexOS.

> [!WARNING]
> This repository is in an early pre-release phase. It uses an undocumented
> backend and must not be installed with production credentials yet.

## Project goals

- expose forecast data through native Home Assistant entities;
- support the Home Assistant Energy dashboard where its forecast model fits;
- coordinate refresh-token rotation safely and avoid concurrent refreshes;
- keep credentials out of logs, diagnostics, fixtures, and source control;
- provide a migration path to an official SMA OAuth/API backend if SMA makes
  the required access available.

## Current status

The authentication and forecast endpoints have been validated in a private
multi-day endurance test. Synthetic protocol fixtures, normalized immutable
models, an asynchronous HTTP client, serialized refresh-token rotation, private
atomic token storage, the Home Assistant coordinator runtime, and a temporary
manual-bootstrap and reauthentication flow are covered by network-free tests.
The first sensor platform exposes SMA's next forecast interval as predicted PV
power, predicted consumption, predicted surplus, and an explicit UTC timestamp.
The integration also implements Home Assistant's native solar-forecast provider
for the Energy dashboard using SMA's hourly photovoltaic-energy recommendation
totals. Each update merges the current and following local date so tomorrow's
forecast is already available before midnight. The full forecast curve remains
in coordinator memory instead of being copied into Recorder-backed entity
attributes. A private, bounded SQLite archive records real photovoltaic and
consumption measurements on every update and one complete photovoltaic and
consumption forecast vintage per hour. This is the storage foundation for a
future Energy Live card that can move between dates and compare forecasts with
what actually happened.

The temporary setup form accepts the numeric plant ID and the newest rotating
refresh token obtained locally from an authenticated browser session. A future
SMA-authorized OAuth client can replace this bootstrap UI without changing the
normalized data models or entities.

Daily energy totals, recommendation windows, a forecast-series action and
WebSocket API, multi-plant discovery, and the optional Energy Live card remain
future milestones. Historical forecast curves only exist from the first
successful update after archive support is installed; they cannot be recreated
reliably from Home Assistant Recorder later.

See [the architecture notes](docs/architecture.md) for the planned design and
security boundaries.

## Important limitations

- The initial backend may rely on an undocumented Sunny Portal UI API that can
  change without notice.
- A seamless browser-based login requires an OAuth client authorized by SMA.
- Never open an issue containing access tokens, refresh tokens, cookies, HAR
  files, raw portal responses, plant identifiers, or personal telemetry.

## Trademark notice

This independent project is not affiliated with, endorsed by, or supported by
SMA Solar Technology AG. SMA, Sunny Portal, Sunny Home Manager, and ennexOS are
trademarks or product names of their respective owner. Their names are used
only to describe compatibility.

## License

Licensed under the [Apache License 2.0](LICENSE).
