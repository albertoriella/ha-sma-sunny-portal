"""Asynchronous client for the Sunny Portal UI API."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from datetime import date
from urllib.parse import quote

import aiohttp

from .const import API_BASE_URL, DEFAULT_REQUEST_TIMEOUT_SECONDS
from .errors import (
    SmaSunnyPortalAuthenticationError,
    SmaSunnyPortalConnectionError,
    SmaSunnyPortalDataError,
    SmaSunnyPortalRateLimitError,
    SmaSunnyPortalResponseError,
)
from .models import ConsumerBalance
from .parser import parse_consumer_balance

type AccessTokenProvider = Callable[[], Awaitable[str]]


class SmaSunnyPortalApiClient:
    """Retrieve and normalize data from the Sunny Portal UI API."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        access_token_provider: AccessTokenProvider,
        *,
        base_url: str = API_BASE_URL,
        request_timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS,
    ) -> None:
        """Initialize the client with a shared session and token provider."""
        self._session = session
        self._access_token_provider = access_token_provider
        self._base_url = base_url.rstrip("/")
        self._timeout = aiohttp.ClientTimeout(total=request_timeout_seconds)

    async def async_get_consumer_balance(
        self,
        plant_id: str,
        date_local: date,
        *,
        load_timeframes: bool = False,
    ) -> ConsumerBalance:
        """Return one normalized local-day consumer balance."""
        if not plant_id:
            raise ValueError("plant_id must not be empty")

        access_token = await self._access_token_provider()
        if not access_token or any(character.isspace() for character in access_token):
            raise SmaSunnyPortalAuthenticationError(
                "Token provider returned an unusable access token"
            )

        encoded_plant_id = quote(plant_id, safe="")
        url = (
            f"{self._base_url}/measurements/{encoded_plant_id}"
            "/consumerbalance/consumption"
        )
        params = {
            "dateBeginLocal": date_local.isoformat(),
            "interval": "Day",
            "loadTimeframes": str(load_timeframes).lower(),
        }
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {access_token}",
        }

        try:
            async with self._session.get(
                url,
                params=params,
                headers=headers,
                timeout=self._timeout,
            ) as response:
                self._raise_for_status(response.status)
                try:
                    payload = await response.json(content_type=None)
                except (
                    aiohttp.ContentTypeError,
                    json.JSONDecodeError,
                    UnicodeError,
                ) as err:
                    raise SmaSunnyPortalDataError(
                        "Sunny Portal returned a non-JSON response"
                    ) from err
        except (TimeoutError, aiohttp.ClientError) as err:
            raise SmaSunnyPortalConnectionError("Could not reach Sunny Portal") from err

        return parse_consumer_balance(payload)

    @staticmethod
    def _raise_for_status(status: int) -> None:
        """Convert HTTP status codes without exposing response bodies."""
        if status in {401, 403}:
            raise SmaSunnyPortalAuthenticationError(
                f"Sunny Portal rejected authentication (HTTP {status})"
            )
        if status == 429:
            raise SmaSunnyPortalRateLimitError(
                "Sunny Portal rate limit reached (HTTP 429)"
            )
        if status >= 400:
            raise SmaSunnyPortalResponseError(
                f"Sunny Portal request failed (HTTP {status})"
            )
