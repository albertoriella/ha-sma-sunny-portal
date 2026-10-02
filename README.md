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
multi-day endurance test. The next milestone is an asynchronous client with
fully synthetic test fixtures. Home Assistant entities and configuration flow
will be added only after that client is covered by tests.

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
