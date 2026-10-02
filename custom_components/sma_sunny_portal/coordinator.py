"""Home Assistant data coordinator for SMA Sunny Portal."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import date

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
        """Fetch and normalize the current local day."""
        try:
            return await self._api_client.async_get_consumer_balance(
                self._plant_id,
                self._local_date_provider(),
            )
        except SmaSunnyPortalAuthenticationError as err:
            raise ConfigEntryAuthFailed(
                "SMA Sunny Portal authentication must be renewed"
            ) from err
        except SmaSunnyPortalError as err:
            raise UpdateFailed(f"Error updating SMA Sunny Portal: {err}") from err
