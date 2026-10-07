# Architecture

## Scope

The integration will represent one SMA account as one Home Assistant config
entry. A single account-scoped authentication manager will serve all selected
plants so that rotating refresh tokens can never be consumed concurrently by
separate entries.

The first supported data set is expected to include:

- recent measured photovoltaic generation and total consumption;
- quarter-hour photovoltaic and consumption forecasts;
- hourly weather icon identifiers;
- hourly surplus recommendations and classifications.

## Backend boundary

Authentication and data retrieval will be hidden behind an internal backend
interface:

- `portal_ui`: experimental support for the undocumented Sunny Portal UI API;
- `official_oauth`: reserved for an SMA-authorized OAuth client and equivalent
  official API data.

Home Assistant entities must consume normalized domain models and must not
depend directly on endpoint-specific response dictionaries.

## Authentication invariants

The token manager must:

1. hold an account-wide asynchronous refresh lock;
2. use only the newest known refresh token;
3. validate the complete token response;
4. persist the rotated refresh token atomically;
5. expose the short-lived access token only in memory;
6. never include either token in logs or diagnostics;
7. convert terminal authentication failures into a Home Assistant reauth flow.

The long-lived refresh token is stored in a private, config-entry-scoped Home
Assistant `Store` using immediate atomic writes. A bootstrap token may briefly
arrive through config-entry data, but is removed after the private store has
accepted it. The short-lived access token exists only in memory.

The integration must not run concurrently with an external program rotating
the same refresh-token chain.

Until SMA authorizes a dedicated OAuth client and redirect URI, the config flow
provides an explicitly experimental manual bootstrap. It validates both token
rotation and plant access before creating an entry, derives the stable unique
ID from the validated SMA account subject, and preserves the newest token when
a validation attempt must be retried. The reauthentication flow writes every
rotation directly to the private token store before reloading the entry.

## Home Assistant model

A `DataUpdateCoordinator` performs one cloud update approximately every 15
minutes, requests the current and following dates in Home Assistant's configured
time zone, merges overlapping samples by timestamp, and translates expired
authentication into config-entry reauthentication.
Entities read normalized immutable data from the coordinator. The initial
sensor platform selects the first forecast timestamp at or after the current
UTC time and exposes four entities:

- predicted photovoltaic power for the next interval;
- predicted consumption power for the next interval;
- predicted surplus power for the next interval;
- the next forecast interval timestamp.

If Sunny Portal temporarily returns no future prediction, these sensors become
unavailable while the coordinator remains healthy. This distinguishes a valid
empty forecast from a transport failure without inventing zero values.

Planned entities include:

- current photovoltaic and consumption forecast sensors;
- current forecast surplus;
- expected generation and consumption totals;
- best forecast energy window;
- diagnostic timestamps and data freshness.

The photovoltaic forecast is exposed through Home Assistant's native Energy
dashboard provider interface. It uses SMA's hourly `totalPvGeneration`
recommendation values directly, avoiding conversion and rounding drift from
the quarter-hour power curve. Large forecast arrays remain in coordinator
memory instead of being repeated in Recorder-backed state attributes. A future
response-producing action can return the cached series on demand for dashboards
and automations.

## Forecast provenance and evaluation

Long-term evaluation must preserve both when a forecast was issued and the
future interval it predicted. It must not be implemented by copying full curves
into sensor attributes, because Recorder would duplicate the entire payload on
every state update.

The integration uses a bounded private SQLite archive instead. It stores
normalized forecast vintages with these dimensions:

- provider and plant;
- forecast issue time;
- forecast target interval;
- predicted photovoltaic and consumption energy;
- later observed energy and evaluation horizon.

The live coordinator still refreshes every 15 minutes, while the complete
forecast curve is archived at most once per hour. Measured photovoltaic and
consumption power is upserted on every update. Forecast vintages are retained
for 90 days and measurements for 400 days; these defaults can become options
after the read API and card establish their real storage requirements. The
database is config-entry scoped, created with mode `0600`, contains no tokens,
and is deleted with the config entry. A history-write failure is logged without
taking live sensors offline.

The first card view will use either the last day-ahead vintage available before
local midnight or a rolling forecast assembled from the newest vintage that
predated each target interval. Keeping `issued_at` separate from `valid_at`
allows both views without rewriting history. Compact aggregate metrics such as
bias, MAE, RMSE, and WAPE are computed on demand for the bounded history API;
they can later be retained longer and exposed as diagnostics or Home Assistant
statistics. This provider-neutral boundary also permits a future ensemble
forecaster without coupling its learning logic to the SMA transport.

## Private history read API

The integration registers the authenticated Home Assistant WebSocket command
`sma_sunny_portal/history`. The frontend supplies a config-entry ID, a local
calendar date, and a forecast selection mode. The backend resolves local
midnight boundaries using Home Assistant's configured time zone before reading
SQLite, so daylight-saving dates correctly span 23 or 25 hours.

The supported selection modes are deliberately explicit:

- `latest` selects the newest single archived vintage that overlaps the day;
- `day_ahead` selects the newest single vintage issued at or before local
  midnight, which provides a stable no-hindsight comparison;
- `rolling` independently selects the newest vintage issued no later than each
  target timestamp, approximating what was knowable at every interval.

If no pre-midnight vintage exists, `day_ahead` returns no predicted points. It
must never silently fall back to an after-midnight curve because that would
invalidate later forecast-quality comparisons.

Responses contain measured PV and consumption power, forecast PV and
consumption power, derived surplus, and both issue and target timestamps.
Archive-wide first/last availability bounds allow the future card to constrain
calendar navigation. Empty dates return empty arrays rather than fabricated
zeroes. Storage errors use fixed public error codes and never expose database
paths, credentials, plant telemetry, or exception text.

The response also calculates provider-neutral quality metrics without adding a
second persistence format. A prediction is eligible only after its target time
is covered by the measurement series, and it is matched only to a measurement
with the exact same UTC timestamp. This is appropriate for SMA's five-minute
measurements and quarter-hour predictions and avoids interpolation or hindsight.
The matched quarter-hour points produce compared actual and forecast energy,
signed energy error, signed power bias, MAE, RMSE, and WAPE. MAPE is deliberately
omitted because night-time photovoltaic values make pointwise percentages
unstable. Percentage metrics are null when their measured denominator is zero,
and future forecast points do not reduce coverage.

The command is available to authenticated Home Assistant users, matching normal
entity-history visibility. It performs bounded, read-only queries in an
executor thread; the SQLite file remains private (`0600`) and is never served as
a downloadable asset.

## Optional Energy Live frontend

The integration serves one dependency-free JavaScript module from its own
component directory and registers it through Home Assistant's frontend and
static-path APIs. It does not use a CDN, iframe, remote script, custom panel, or
dashboard strategy. The regular Lovelace custom-card boundary keeps the feature
optional and lets standard Masonry and Sections views own card lifecycle and
layout. The module waits until the final Home Assistant custom-element registry
contains the root application element before defining the card and editor. This
avoids losing the definitions if the scoped-registry polyfill replaces the
browser's native registry after an extra frontend module has already executed.

`SMA Energy Live` calls only the authenticated WebSocket commands registered by
the integration. A small `sma_sunny_portal/entries` command exposes config-entry
ID, title, and loaded state, but never plant identifiers, telemetry, or tokens.
This lets the card automatically select the only entry while its visual editor
provides an explicit selector when multiple entries exist. Historical curves
continue to stay out of entity attributes and Recorder.

The card displays one bounded local day at a time and uses the UTC boundaries
returned by the backend, so 23- and 25-hour daylight-saving days retain their
true duration. Measured and forecast PV, consumption, surplus, and deficit use
one shared power axis and one physical zero; deficit is the only negative
series. A clickable accessible legend controls each logical series, initially
with all six enabled, and the scale follows the visible series. Forecast mode
selection is an explicit user control; the UI never substitutes one provenance
mode for another.

The integration deliberately does not create, mutate, or delete a user's
Lovelace dashboard. Automatic whole-dashboard installation is difficult to
reverse, risks overwriting user-managed storage/YAML configuration, and couples
the data integration to a particular layout. Shipping a discoverable card in
the same repository preserves the useful shared experience without crossing
that ownership boundary.

## Tests and fixtures

Network-free tests will cover parsing, time zones, daylight-saving transitions,
token rotation, atomic persistence, retry classification, midnight ingestion
delay, and redaction. Fixtures must be synthetic and must not contain copied
plant, component, account, session, or telemetry identifiers.
