"""Home Assistant Energy dashboard forecast support."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .runtime import SmaSunnyPortalRuntimeData

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


async def async_get_solar_forecast(
    hass: HomeAssistant,
    config_entry_id: str,
) -> dict[str, dict[str, float | int]] | None:
    """Return SMA's hourly photovoltaic energy forecast for one entry."""
    if (
        entry := hass.config_entries.async_get_entry(config_entry_id)
    ) is None or not isinstance(entry.runtime_data, SmaSunnyPortalRuntimeData):
        return None

    return {
        "wh_hours": {
            recommendation.time_utc_start.isoformat(): (recommendation.pv_generation_wh)
            for recommendation in (entry.runtime_data.coordinator.data.recommendations)
            if recommendation.pv_generation_wh != 0
            or (
                recommendation.time_utc_start.hour,
                recommendation.time_utc_start.minute,
                recommendation.time_utc_start.second,
            )
            != (0, 0, 0)
        }
    }
