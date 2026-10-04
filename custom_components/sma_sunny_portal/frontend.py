"""Frontend registration for the optional SMA Energy Live card."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Final

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig

from .const import DOMAIN

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

CARD_STATIC_URL: Final = f"/{DOMAIN}/frontend/sma-sunny-portal-energy-card.js"
CARD_ASSET_VERSION: Final = "1"
CARD_MODULE_URL: Final = f"{CARD_STATIC_URL}?v={CARD_ASSET_VERSION}"
CARD_STATIC_PATH: Final = (
    Path(__file__).parent / "frontend_assets" / "sma-sunny-portal-energy-card.js"
)
FRONTEND_REGISTERED: Final = f"{DOMAIN}.frontend_registered"


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
    add_extra_js_url(hass, CARD_MODULE_URL)
    hass.data[FRONTEND_REGISTERED] = True
