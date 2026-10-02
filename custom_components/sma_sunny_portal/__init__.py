"""The SMA Sunny Portal Forecast integration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .api import SmaSunnyPortalApiClient
from .auth import SmaSunnyPortalTokenManager
from .const import CONF_PLANT_ID, CONF_REFRESH_TOKEN
from .errors import SmaSunnyPortalAuthenticationError
from .runtime import SmaSunnyPortalRuntimeData

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

    type SmaSunnyPortalConfigEntry = ConfigEntry[SmaSunnyPortalRuntimeData]


def _required_entry_string(entry: SmaSunnyPortalConfigEntry, key: str) -> str:
    """Return a non-empty config-entry string without exposing its value."""
    value = entry.data.get(key)
    if (
        not isinstance(value, str)
        or not value
        or any(character.isspace() for character in value)
    ):
        raise SmaSunnyPortalAuthenticationError(
            f"Stored SMA configuration field {key} is missing or invalid"
        )
    return value


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SmaSunnyPortalConfigEntry,
) -> bool:
    """Set up one SMA account from a Home Assistant config entry."""
    from homeassistant.helpers.aiohttp_client import async_get_clientsession

    from .coordinator import SmaSunnyPortalCoordinator
    from .storage import SmaSunnyPortalRefreshTokenStore

    plant_id = _required_entry_string(entry, CONF_PLANT_ID)
    token_store = SmaSunnyPortalRefreshTokenStore(hass, entry.entry_id)
    refresh_token = await token_store.async_load()

    if refresh_token is None:
        refresh_token = _required_entry_string(entry, CONF_REFRESH_TOKEN)
        await token_store.async_save(refresh_token)

    if CONF_REFRESH_TOKEN in entry.data:
        hass.config_entries.async_update_entry(
            entry,
            data={
                key: value
                for key, value in entry.data.items()
                if key != CONF_REFRESH_TOKEN
            },
        )

    session = async_get_clientsession(hass)
    token_manager = SmaSunnyPortalTokenManager(
        session,
        refresh_token,
        token_store.async_save,
    )
    api_client = SmaSunnyPortalApiClient(
        session,
        token_manager.async_get_access_token,
    )
    coordinator = SmaSunnyPortalCoordinator(
        hass,
        entry,
        api_client,
        plant_id,
    )

    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = SmaSunnyPortalRuntimeData(
        token_store=token_store,
        token_manager=token_manager,
        api_client=api_client,
        coordinator=coordinator,
    )
    return True


async def async_unload_entry(
    hass: HomeAssistant,
    entry: SmaSunnyPortalConfigEntry,
) -> bool:
    """Unload an entry; the coordinator shutdown is registered by Home Assistant."""
    del hass, entry
    return True


async def async_remove_entry(
    hass: HomeAssistant,
    entry: SmaSunnyPortalConfigEntry,
) -> None:
    """Delete the private refresh-token store with its config entry."""
    from .storage import SmaSunnyPortalRefreshTokenStore

    await SmaSunnyPortalRefreshTokenStore(hass, entry.entry_id).async_remove()
