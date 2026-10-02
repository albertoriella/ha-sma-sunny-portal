"""Private durable storage for the rotating SMA refresh token."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import (
    CONF_REFRESH_TOKEN,
    TOKEN_STORAGE_KEY_PREFIX,
    TOKEN_STORAGE_VERSION,
)
from .errors import SmaSunnyPortalTokenPersistenceError


def _validated_refresh_token(value: object) -> str:
    """Return a valid token without ever including its value in an error."""
    if (
        not isinstance(value, str)
        or not value
        or any(character.isspace() for character in value)
    ):
        raise SmaSunnyPortalTokenPersistenceError(
            "Stored SMA refresh token is missing or invalid"
        )
    return value


class SmaSunnyPortalRefreshTokenStore:
    """Persist the newest refresh token immediately and atomically."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        """Initialize private storage scoped to one config entry."""
        self._store = Store[dict[str, Any]](
            hass,
            TOKEN_STORAGE_VERSION,
            f"{TOKEN_STORAGE_KEY_PREFIX}.{entry_id}",
            private=True,
            atomic_writes=True,
        )

    async def async_load(self) -> str | None:
        """Load the latest token, if this entry has stored one."""
        try:
            payload = await self._store.async_load()
        except Exception:
            raise SmaSunnyPortalTokenPersistenceError(
                "Could not load the stored SMA refresh token"
            ) from None

        if payload is None:
            return None
        if not isinstance(payload, dict):
            raise SmaSunnyPortalTokenPersistenceError(
                "Stored SMA authentication data is invalid"
            )
        return _validated_refresh_token(payload.get(CONF_REFRESH_TOKEN))

    async def async_save(self, refresh_token: str) -> None:
        """Atomically write the current token before it can be consumed again."""
        token = _validated_refresh_token(refresh_token)
        try:
            await self._store.async_save({CONF_REFRESH_TOKEN: token})
        except Exception:
            raise SmaSunnyPortalTokenPersistenceError(
                "Could not persist the rotated SMA refresh token"
            ) from None

    async def async_remove(self) -> None:
        """Remove authentication data when the config entry is deleted."""
        try:
            await self._store.async_remove()
        except Exception:
            raise SmaSunnyPortalTokenPersistenceError(
                "Could not remove the stored SMA refresh token"
            ) from None
