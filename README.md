# SMA Sunny Portal Forecast for Home Assistant

An experimental Home Assistant custom integration for importing photovoltaic
generation, household consumption, weather indicators, and energy-surplus
forecasts from SMA Sunny Portal powered by ennexOS.

> [!WARNING]
> This repository is in the bootstrap phase. It does not provide a functional
> Home Assistant integration yet and must not be installed in production.

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
The next milestone is the first set of forecast sensors.

The temporary setup form accepts the numeric plant ID and the newest rotating
refresh token obtained locally from an authenticated browser session. A future
SMA-authorized OAuth client can replace this bootstrap UI without changing the
normalized data models or entities.

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
