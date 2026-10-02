"""Credential validation shared by setup and reauthentication flows."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date

import aiohttp

from .api import SmaSunnyPortalApiClient
from .auth import SmaSunnyPortalTokenManager
from .identity import account_id_from_access_token
from .models import ConsumerBalance

type RotatedTokenObserver = Callable[[str], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class BootstrapValidationResult:
    """Validated identity, newest token, and normalized portal response."""

    account_id: str
    refresh_token: str
    consumer_balance: ConsumerBalance


async def async_validate_credentials(
    session: aiohttp.ClientSession,
    plant_id: str,
    refresh_token: str,
    date_local: date,
    *,
    async_observe_rotated_token: RotatedTokenObserver | None = None,
) -> BootstrapValidationResult:
    """Rotate credentials once and verify access to the selected plant."""
    latest_refresh_token = refresh_token

    async def async_capture_refresh_token(rotated_token: str) -> None:
        nonlocal latest_refresh_token
        latest_refresh_token = rotated_token
        if async_observe_rotated_token is not None:
            await async_observe_rotated_token(rotated_token)

    token_manager = SmaSunnyPortalTokenManager(
        session,
        refresh_token,
        async_capture_refresh_token,
    )
    access_token = await token_manager.async_get_access_token()
    account_id = account_id_from_access_token(access_token)
    api_client = SmaSunnyPortalApiClient(
        session,
        token_manager.async_get_access_token,
    )
    consumer_balance = await api_client.async_get_consumer_balance(
        plant_id,
        date_local,
    )

    return BootstrapValidationResult(
        account_id=account_id,
        refresh_token=latest_refresh_token,
        consumer_balance=consumer_balance,
    )
