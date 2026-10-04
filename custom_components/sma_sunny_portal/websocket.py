"""WebSocket commands for private SMA forecast history."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import probatio
from homeassistant.components import websocket_api
from homeassistant.components.websocket_api import ActiveConnection
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .errors import SmaSunnyPortalHistoryError
from .history import FORECAST_HISTORY_MODES, ForecastHistoryMode

WEBSOCKET_COMMAND_HISTORY = f"{DOMAIN}/history"
WEBSOCKET_COMMAND_ENTRIES = f"{DOMAIN}/entries"


def _parse_iso_date(value: str) -> date | None:
    """Parse only the canonical YYYY-MM-DD representation."""
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.isoformat() == value else None


def _serialize_timestamp(value: datetime | None) -> str | None:
    """Serialize one aware timestamp for the Home Assistant frontend."""
    return value.isoformat() if value is not None else None


@websocket_api.websocket_command(
    {
        probatio.Required("type"): WEBSOCKET_COMMAND_HISTORY,
        probatio.Required("config_entry_id"): str,
        probatio.Required("date"): str,
        probatio.Optional("mode", default="latest"): probatio.In(
            FORECAST_HISTORY_MODES
        ),
    }
)
@websocket_api.async_response
async def websocket_get_history(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return one local day of actual and forecast SMA power curves."""
    requested_date = _parse_iso_date(msg["date"])
    if requested_date is None:
        connection.send_error(
            msg["id"],
            "invalid_date",
            "Date must use the YYYY-MM-DD format",
        )
        return

    entry = hass.config_entries.async_get_entry(msg["config_entry_id"])
    if entry is None or entry.domain != DOMAIN:
        connection.send_error(
            msg["id"],
            "entry_not_found",
            "SMA Sunny Portal config entry not found",
        )
        return

    runtime_data = getattr(entry, "runtime_data", None)
    if runtime_data is None:
        connection.send_error(
            msg["id"],
            "entry_not_loaded",
            "SMA Sunny Portal config entry is not loaded",
        )
        return

    local_zone = ZoneInfo(hass.config.time_zone)
    start_local = datetime.combine(requested_date, time.min, tzinfo=local_zone)
    end_local = datetime.combine(
        requested_date + timedelta(days=1),
        time.min,
        tzinfo=local_zone,
    )
    start_utc = start_local.astimezone(UTC)
    end_utc = end_local.astimezone(UTC)
    mode: ForecastHistoryMode = msg.get("mode", "latest")

    try:
        archived_day = await runtime_data.history_store.async_get_day(
            start_utc,
            end_utc,
            mode,
        )
    except SmaSunnyPortalHistoryError:
        connection.send_error(
            msg["id"],
            "history_unavailable",
            "SMA forecast history is temporarily unavailable",
        )
        return

    connection.send_result(
        msg["id"],
        {
            "config_entry_id": entry.entry_id,
            "date": requested_date.isoformat(),
            "timezone": hass.config.time_zone,
            "mode": mode,
            "day_start_utc": start_utc.isoformat(),
            "day_end_utc": end_utc.isoformat(),
            "archive": {
                "first_available_utc": _serialize_timestamp(
                    archived_day.first_available_utc
                ),
                "last_available_utc": _serialize_timestamp(
                    archived_day.last_available_utc
                ),
            },
            "measurements": [
                {
                    "time_utc": item.time_utc.isoformat(),
                    "pv_generation_w": item.pv_generation_w,
                    "total_consumption_w": item.total_consumption_w,
                    "surplus_w": (item.pv_generation_w - item.total_consumption_w),
                }
                for item in archived_day.measurements
            ],
            "predictions": [
                {
                    "time_utc": item.time_utc.isoformat(),
                    "issued_at_utc": item.issued_at_utc.isoformat(),
                    "pv_generation_w": item.pv_generation_w,
                    "total_consumption_w": item.total_consumption_w,
                    "surplus_w": (item.pv_generation_w - item.total_consumption_w),
                }
                for item in archived_day.predictions
            ],
        },
    )


@websocket_api.websocket_command(
    {
        probatio.Required("type"): WEBSOCKET_COMMAND_ENTRIES,
    }
)
@websocket_api.async_response
async def websocket_get_entries(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """List configured integration entries without exposing plant credentials."""
    entries = sorted(
        hass.config_entries.async_entries(DOMAIN),
        key=lambda entry: (entry.title.casefold(), entry.entry_id),
    )
    connection.send_result(
        msg["id"],
        {
            "entries": [
                {
                    "entry_id": entry.entry_id,
                    "title": entry.title,
                    "loaded": getattr(entry, "runtime_data", None) is not None,
                }
                for entry in entries
            ]
        },
    )


def async_register_websocket_commands(hass: HomeAssistant) -> None:
    """Register the integration's authenticated WebSocket commands."""
    websocket_api.async_register_command(hass, websocket_get_history)
    websocket_api.async_register_command(hass, websocket_get_entries)
