"""Safe rotating-token management for SMA Sunny Portal."""

from __future__ import annotations

import asyncio
import json
import math
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any

import aiohttp

from .const import (
    ACCESS_TOKEN_EXPIRY_MARGIN_SECONDS,
    DEFAULT_REQUEST_TIMEOUT_SECONDS,
    OAUTH_CLIENT_ID,
    OAUTH_SCOPE,
    TOKEN_ENDPOINT,
)
from .errors import (
    SmaSunnyPortalAuthenticationError,
    SmaSunnyPortalConnectionError,
    SmaSunnyPortalDataError,
    SmaSunnyPortalRateLimitError,
    SmaSunnyPortalResponseError,
    SmaSunnyPortalTokenPersistenceError,
)

type SaveRefreshToken = Callable[[str], Awaitable[None]]
type MonotonicClock = Callable[[], float]


@dataclass(frozen=True, slots=True)
class _TokenResponse:
    """Validated fields returned by the Keycloak token endpoint."""

    access_token: str
    refresh_token: str
    expires_in: int
    refresh_expires_in: int


def _token_string(mapping: Mapping[str, Any], key: str) -> str:
    """Return a non-empty token without ever including it in an error."""
    value = mapping.get(key)
    if (
        not isinstance(value, str)
        or not value
        or any(character.isspace() for character in value)
    ):
        raise SmaSunnyPortalDataError(f"Token response field {key} is invalid")
    return value


def _positive_integer(mapping: Mapping[str, Any], key: str) -> int:
    """Return a required positive integer token lifetime."""
    value = mapping.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise SmaSunnyPortalDataError(f"Token response field {key} is invalid")
    return value


def _parse_token_response(payload: object) -> _TokenResponse:
    """Validate the complete token response needed for safe rotation."""
    if not isinstance(payload, Mapping):
        raise SmaSunnyPortalDataError("Token response must be an object")

    token_type = payload.get("token_type")
    if not isinstance(token_type, str) or token_type.casefold() != "bearer":
        raise SmaSunnyPortalDataError("Token response field token_type is invalid")

    return _TokenResponse(
        access_token=_token_string(payload, "access_token"),
        refresh_token=_token_string(payload, "refresh_token"),
        expires_in=_positive_integer(payload, "expires_in"),
        refresh_expires_in=_positive_integer(payload, "refresh_expires_in"),
    )


class SmaSunnyPortalTokenManager:
    """Serialize refreshes and persist every rotated refresh token."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        refresh_token: str,
        async_save_refresh_token: SaveRefreshToken,
        *,
        token_endpoint: str = TOKEN_ENDPOINT,
        client_id: str = OAUTH_CLIENT_ID,
        scope: str = OAUTH_SCOPE,
        request_timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS,
        expiry_margin_seconds: float = ACCESS_TOKEN_EXPIRY_MARGIN_SECONDS,
        clock: MonotonicClock = time.monotonic,
    ) -> None:
        """Initialize one account-wide token manager."""
        if not refresh_token or any(character.isspace() for character in refresh_token):
            raise ValueError("refresh_token must be a non-empty token")
        if not math.isfinite(expiry_margin_seconds) or expiry_margin_seconds < 0:
            raise ValueError("expiry_margin_seconds must be finite and non-negative")
        if not math.isfinite(request_timeout_seconds) or request_timeout_seconds <= 0:
            raise ValueError("request_timeout_seconds must be finite and positive")

        self._session = session
        self._refresh_token = refresh_token
        self._async_save_refresh_token = async_save_refresh_token
        self._token_endpoint = token_endpoint
        self._client_id = client_id
        self._scope = scope
        self._timeout = aiohttp.ClientTimeout(total=request_timeout_seconds)
        self._expiry_margin_seconds = expiry_margin_seconds
        self._clock = clock

        self._refresh_lock = asyncio.Lock()
        self._access_token: str | None = None
        self._access_token_expires_at = 0.0
        self._refresh_expires_in_seconds: int | None = None
        self._refresh_token_needs_persistence = False

    @property
    def refresh_expires_in_seconds(self) -> int | None:
        """Return the lifetime reported for the most recent refresh token."""
        return self._refresh_expires_in_seconds

    @property
    def has_pending_refresh_token_persistence(self) -> bool:
        """Return whether a rotated token still needs durable persistence."""
        return self._refresh_token_needs_persistence

    async def async_get_access_token(self) -> str:
        """Return a usable access token, refreshing at most once concurrently."""
        if self._access_token_is_usable() and not self._refresh_token_needs_persistence:
            assert self._access_token is not None
            return self._access_token

        async with self._refresh_lock:
            if self._refresh_token_needs_persistence:
                await self._async_persist_refresh_token()

            if self._access_token_is_usable():
                assert self._access_token is not None
                return self._access_token

            return await self._async_refresh()

    def invalidate_access_token(self) -> None:
        """Force the next caller to refresh, for example after HTTP 401."""
        self._access_token = None
        self._access_token_expires_at = 0.0

    def _access_token_is_usable(self) -> bool:
        """Return whether the cached access token is inside its safe lifetime."""
        return (
            self._access_token is not None
            and self._clock() < self._access_token_expires_at
        )

    async def _async_refresh(self) -> str:
        """Rotate tokens, persist the refresh token, then expose access."""
        payload = await self._async_request_refresh()
        token_response = _parse_token_response(payload)
        usable_lifetime = token_response.expires_in - self._expiry_margin_seconds
        if usable_lifetime <= 0:
            raise SmaSunnyPortalDataError(
                "Token response access-token lifetime is too short"
            )

        self._refresh_token = token_response.refresh_token
        self._access_token = token_response.access_token
        self._access_token_expires_at = self._clock() + usable_lifetime
        self._refresh_expires_in_seconds = token_response.refresh_expires_in
        self._refresh_token_needs_persistence = True

        await self._async_persist_refresh_token()
        return token_response.access_token

    async def _async_persist_refresh_token(self) -> None:
        """Persist the current rotated token before allowing it to advance."""
        try:
            await self._async_save_refresh_token(self._refresh_token)
        except Exception:
            raise SmaSunnyPortalTokenPersistenceError(
                "Could not persist the rotated refresh token"
            ) from None
        self._refresh_token_needs_persistence = False

    async def _async_request_refresh(self) -> object:
        """Request one token rotation without logging request or response data."""
        data = {
            "grant_type": "refresh_token",
            "scope": self._scope,
            "refresh_token": self._refresh_token,
            "client_id": self._client_id,
        }
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        }

        try:
            async with self._session.post(
                self._token_endpoint,
                data=data,
                headers=headers,
                timeout=self._timeout,
            ) as response:
                self._raise_for_status(response.status)
                try:
                    return await response.json(content_type=None)
                except (
                    aiohttp.ContentTypeError,
                    json.JSONDecodeError,
                    UnicodeError,
                ):
                    raise SmaSunnyPortalDataError(
                        "Token endpoint returned a non-JSON response"
                    ) from None
        except (TimeoutError, aiohttp.ClientError) as err:
            raise SmaSunnyPortalConnectionError(
                "Could not reach the SMA token endpoint"
            ) from err

    @staticmethod
    def _raise_for_status(status: int) -> None:
        """Classify token endpoint failures without exposing response bodies."""
        if status in {400, 401, 403}:
            raise SmaSunnyPortalAuthenticationError(
                f"SMA rejected the refresh token (HTTP {status})"
            )
        if status == 429:
            raise SmaSunnyPortalRateLimitError(
                "SMA token endpoint rate limit reached (HTTP 429)"
            )
        if status >= 400:
            raise SmaSunnyPortalResponseError(
                f"SMA token request failed (HTTP {status})"
            )
