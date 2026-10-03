"""Home Assistant data coordinator for SMA Sunny Portal."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import date, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import SmaSunnyPortalApiClient
from .const import DEFAULT_UPDATE_INTERVAL, NAME
from .errors import SmaSunnyPortalAuthenticationError, SmaSunnyPortalError
from .models import ConsumerBalance

_LOGGER = logging.getLogger(__name__)

type LocalDateProvider = Callable[[], date]


def _current_local_date() -> date:
    """Return today's date in Home Assistant's configured time zone."""
    return dt_util.now().date()


def _merge_consumer_balances(
    *balances: ConsumerBalance,
) -> ConsumerBalance:
    """Merge date-scoped payloads and prefer later payloads on overlap."""
    measurements = {
        item.time_utc: item
        for balance in balances
        for item in balance.measurements
    }
    predictions = {
        item.time_utc: item
        for balance in balances
        for item in balance.predictions
    }
    weather_forecasts = {
        item.time_utc: item
        for balance in balances
        for item in balance.weather_forecasts
    }
    recommendations = {
        item.time_utc_start: item
        for balance in balances
        for item in balance.recommendations
    }
    consumers = {
        item.component_id: item
        for balance in balances
        for item in balance.consumers
    }

    return ConsumerBalance(
        measurements=tuple(
            sorted(measurements.values(), key=lambda item: item.time_utc)
        ),
        predictions=tuple(
            sorted(predictions.values(), key=lambda item: item.time_utc)
        ),
        weather_forecasts=tuple(
            sorted(weather_forecasts.values(), key=lambda item: item.time_utc)
        ),
        recommendations=tuple(
            sorted(
                recommendations.values(),
                key=lambda item: item.time_utc_start,
            )
        ),
        consumers=tuple(
            sorted(consumers.values(), key=lambda item: item.component_id)
        ),
    )


class SmaSunnyPortalCoordinator(DataUpdateCoordinator[ConsumerBalance]):
    """Fetch one normalized consumer-balance payload for all entities."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        api_client: SmaSunnyPortalApiClient,
        plant_id: str,
        *,
        local_date_provider: LocalDateProvider = _current_local_date,
    ) -> None:
        """Initialize the account coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=NAME,
            config_entry=config_entry,
            update_interval=DEFAULT_UPDATE_INTERVAL,
            always_update=False,
        )
        self._api_client = api_client
        self._plant_id = plant_id
        self._local_date_provider = local_date_provider

    async def _async_update_data(self) -> ConsumerBalance:
        """Fetch and merge the current and following local days."""
        try:
            current_date = self._local_date_provider()
            current_balance, next_balance = await asyncio.gather(
                self._api_client.async_get_consumer_balance(
                    self._plant_id,
                    current_date,
                ),
                self._api_client.async_get_consumer_balance(
                    self._plant_id,
                    current_date + timedelta(days=1),
                ),
            )
            return _merge_consumer_balances(current_balance, next_balance)
        except SmaSunnyPortalAuthenticationError as err:
            raise ConfigEntryAuthFailed(
                "SMA Sunny Portal authentication must be renewed"
            ) from err
        except SmaSunnyPortalError as err:
            raise UpdateFailed(f"Error updating SMA Sunny Portal: {err}") from err
