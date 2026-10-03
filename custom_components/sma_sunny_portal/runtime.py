"""Runtime objects owned by one Home Assistant config entry."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .api import SmaSunnyPortalApiClient
from .auth import SmaSunnyPortalTokenManager

if TYPE_CHECKING:
    from .coordinator import SmaSunnyPortalCoordinator
    from .history import SmaSunnyPortalHistoryStore
    from .storage import SmaSunnyPortalRefreshTokenStore


@dataclass(frozen=True, slots=True)
class SmaSunnyPortalRuntimeData:
    """Keep account-scoped objects together for platforms and unload."""

    token_store: SmaSunnyPortalRefreshTokenStore
    token_manager: SmaSunnyPortalTokenManager
    api_client: SmaSunnyPortalApiClient
    history_store: SmaSunnyPortalHistoryStore
    coordinator: SmaSunnyPortalCoordinator
