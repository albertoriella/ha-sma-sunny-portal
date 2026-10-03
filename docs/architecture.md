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
minutes, requests the current date in Home Assistant's configured time zone,
and translates expired authentication into config-entry reauthentication.
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

The photovoltaic forecast may also be exposed through the Home Assistant
Energy dashboard by converting quarter-hour power samples into hourly energy.
Large forecast arrays remain in coordinator memory instead of being repeated
in Recorder-backed state attributes. A future response-producing action can
return the cached series on demand for dashboards and automations.

## Tests and fixtures

Network-free tests will cover parsing, time zones, daylight-saving transitions,
token rotation, atomic persistence, retry classification, midnight ingestion
delay, and redaction. Fixtures must be synthetic and must not contain copied
plant, component, account, session, or telemetry identifiers.
