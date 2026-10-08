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
consumption forecast vintage per hour. An authenticated Home Assistant
WebSocket command
reads one local date at a time from that archive without copying large curves
into entity attributes or Recorder. It can return the newest archived curve, a
day-ahead curve frozen at local midnight, or a rolling curve assembled from the
newest forecast available before each target interval. The optional
`SMA Energy Live` Lovelace card consumes that private API and plots measured and
forecast PV, consumption, surplus, and deficit with calendar navigation.

The temporary setup form accepts the numeric plant ID and the newest rotating
refresh token obtained locally from an authenticated browser session. A future
SMA-authorized OAuth client can replace this bootstrap UI without changing the
normalized data models or entities.

Daily energy totals, recommendation windows, and account-level multi-plant
discovery remain future milestones. Historical forecast curves only exist from
the first successful update after archive support is installed; they cannot be
recreated reliably from Home Assistant Recorder later.

The private history command is `sma_sunny_portal/history`. It requires the
config-entry ID, a canonical local date (`YYYY-MM-DD`), and optionally one of
these modes:

- `latest`: newest archived forecast vintage covering the requested date;
- `day_ahead`: newest vintage issued no later than that date's local midnight;
- `rolling`: newest vintage issued before each individual target interval.

The command returns measured and predicted PV, consumption, and surplus power,
plus forecast issue timestamps, archive availability bounds, and compact
accuracy metrics for forecast points whose exact target timestamp already has a
measurement. The metrics include comparison coverage, energy error, bias, MAE,
RMSE, and WAPE for photovoltaic generation and total consumption. Future points
are not counted as missing, and percentage errors remain null when the measured
energy is zero. The command is intended for the integration's own optional
frontend card and other authenticated Home Assistant frontends; it is not a
public SMA endpoint. `day_ahead` deliberately returns no curve when the archive
has no pre-midnight vintage, as happens on the first archive day, instead of
substituting a hindsight forecast.

## Optional Energy Live card

The integration ships a dependency-free custom card and serves it locally; no
separate JavaScript download is required. When Lovelace resources use storage
mode, the integration creates and maintains one persistent module resource
automatically. This makes the module available before dashboards are built on
later Home Assistant starts and avoids the timing window of runtime-only
`add_extra_js_url` registration. Dashboard mode and resource mode are separate:
a YAML dashboard can still use storage-managed resources, which is the normal
mixed configuration.

The operation is idempotent: unrelated resources are preserved, an existing SMA
resource is updated when its version changes, and duplicate resources pointing
to the integration's private static path are consolidated. If resources are
explicitly managed in YAML, Home Assistant exposes them as read-only; the
integration then retains runtime registration as a compatibility fallback. For
deterministic loading in that uncommon mode, add this module to the YAML
resource list:

```yaml
resources:
  - url: /sma_sunny_portal/frontend/sma-sunny-portal-energy-card.js?v=2
    type: module
```

The module also waits for Home Assistant's final scoped custom-element registry
before defining the card and editor. After the first installation or an update,
restart Home Assistant and perform one hard browser refresh. Subsequent ordinary
restarts do not require another hard refresh. Open a dashboard editor, choose
**Add card**, and search for **SMA Energy Live**.

When exactly one SMA config entry exists, the empty card configuration is
enough:

```yaml
type: custom:sma-sunny-portal-energy-card
```

The visual editor can select a specific entry when more than one exists, choose
the initial forecast mode, and override the title. The card provides:

- previous/next day buttons, a calendar input, and a Today shortcut;
- one shared-axis graph with a common zero for PV, consumption, surplus, and
  deficit;
- solid measured PV and consumption curves and dashed forecast curves;
- positive surplus above zero and negative deficit below zero;
- a clickable legend that starts with every series visible and can hide any
  series independently;
- `latest`, `day_ahead`, and `rolling` forecast selection;
- forecast-issue provenance and archive availability bounds;
- English and Italian labels following the Home Assistant language.

The card does not create or overwrite a dashboard. This keeps installation
reversible and lets each user place it in an existing Energy Live view or a new
view without changing unrelated Lovelace configuration. Dates before archive
installation remain empty by design. On the first archive day, `day_ahead` may
also be empty because no pre-midnight snapshot exists yet.

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
