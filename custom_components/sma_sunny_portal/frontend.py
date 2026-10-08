"""Frontend registration for the optional SMA Energy Live card."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Final
from urllib.parse import urlsplit

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.components.lovelace import LOVELACE_DATA, MODE_STORAGE
from homeassistant.components.lovelace.resources import ResourceStorageCollection

from .const import DOMAIN

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

CARD_STATIC_URL: Final = f"/{DOMAIN}/frontend/sma-sunny-portal-energy-card.js"
CARD_ASSET_VERSION: Final = "2"
CARD_MODULE_URL: Final = f"{CARD_STATIC_URL}?v={CARD_ASSET_VERSION}"
CARD_STATIC_PATH: Final = (
    Path(__file__).parent / "frontend_assets" / "sma-sunny-portal-energy-card.js"
)
FRONTEND_REGISTERED: Final = f"{DOMAIN}.frontend_registered"


def _is_card_resource(resource: dict[str, object]) -> bool:
    """Return whether a Lovelace resource belongs to this integration."""
    url = resource.get("url")
    if not isinstance(url, str):
        return False

    try:
        return urlsplit(url).path == CARD_STATIC_URL
    except ValueError:
        return False


async def _async_register_storage_resource(hass: HomeAssistant) -> bool:
    """Persist and reconcile the card module in Lovelace storage mode."""
    lovelace_data = hass.data.get(LOVELACE_DATA)
    if lovelace_data is None or lovelace_data.resource_mode != MODE_STORAGE:
        return False

    resources = lovelace_data.resources
    if not isinstance(resources, ResourceStorageCollection):
        return False

    # async_items() itself does not guarantee that the storage collection has
    # been loaded. The public information call does, including on HA versions
    # where resources are loaded lazily.
    await resources.async_get_info()
    matches = [
        resource for resource in resources.async_items() if _is_card_resource(resource)
    ]

    if not matches:
        await resources.async_create_item(
            {
                "res_type": "module",
                "url": CARD_MODULE_URL,
            }
        )
        return True

    keeper = matches[0]
    keeper_id = keeper.get("id")
    if not isinstance(keeper_id, str):
        return False

    updates: dict[str, str] = {}
    if keeper.get("type") != "module":
        updates["res_type"] = "module"
    if keeper.get("url") != CARD_MODULE_URL:
        updates["url"] = CARD_MODULE_URL

    if updates:
        await resources.async_update_item(keeper_id, updates)

    # Entries with this exact private static path can only load our card. Keep
    # one canonical resource so module imports remain deterministic.
    for duplicate in matches[1:]:
        duplicate_id = duplicate.get("id")
        if isinstance(duplicate_id, str):
            await resources.async_delete_item(duplicate_id)

    return True


async def async_register_frontend(hass: HomeAssistant) -> None:
    """Serve and load the dependency-free optional Lovelace card."""
    if hass.data.get(FRONTEND_REGISTERED):
        return

    await hass.http.async_register_static_paths(
        [
            StaticPathConfig(
                CARD_STATIC_URL,
                str(CARD_STATIC_PATH),
                False,
            )
        ]
    )

    try:
        resource_registered = await _async_register_storage_resource(hass)
    except Exception:  # noqa: BLE001
        _LOGGER.exception(
            "Could not persist the SMA Energy Live Lovelace resource; "
            "falling back to a frontend module URL"
        )
        resource_registered = False

    if not resource_registered:
        add_extra_js_url(hass, CARD_MODULE_URL)

    hass.data[FRONTEND_REGISTERED] = True
