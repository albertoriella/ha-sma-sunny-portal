"""Tests for config-entry runtime setup."""

from __future__ import annotations

import asyncio
import sys
from types import ModuleType
from typing import Any

import pytest

import custom_components.sma_sunny_portal as integration
from custom_components.sma_sunny_portal import (
    SmaSunnyPortalRuntimeData,
    async_remove_entry,
    async_setup_entry,
    async_unload_entry,
)


class FakeConfigEntries:
    """Apply config-entry updates synchronously like Home Assistant does."""

    def __init__(self) -> None:
        """Initialize update history."""
        self.updates: list[dict[str, Any]] = []
        self.forwarded: list[tuple[FakeEntry, tuple[str, ...]]] = []
        self.unloaded: list[tuple[FakeEntry, tuple[str, ...]]] = []
        self.unload_result = True

    def async_update_entry(self, entry: FakeEntry, *, data: dict[str, Any]) -> bool:
        """Replace entry data and record the update."""
        entry.data = data
        self.updates.append(data)
        return True

    async def async_forward_entry_setups(
        self,
        entry: FakeEntry,
        platforms: tuple[str, ...],
    ) -> None:
        """Record platform forwarding after runtime initialization."""
        assert entry.runtime_data is not None
        self.forwarded.append((entry, platforms))

    async def async_unload_platforms(
        self,
        entry: FakeEntry,
        platforms: tuple[str, ...],
    ) -> bool:
        """Record platform unloading and return its configured result."""
        self.unloaded.append((entry, platforms))
        return self.unload_result


class FakeHass:
    """Minimal Home Assistant object used during setup."""

    def __init__(self) -> None:
        """Initialize config entries."""
        self.config_entries = FakeConfigEntries()


class FakeEntry:
    """Minimal config entry with runtime data."""

    def __init__(self, data: dict[str, Any]) -> None:
        """Initialize synthetic entry data."""
        self.entry_id = "synthetic-entry"
        self.data = data
        self.runtime_data: SmaSunnyPortalRuntimeData | None = None


class FakeTokenStore:
    """Record bootstrap, rotation, and removal without touching disk."""

    instances: list[FakeTokenStore] = []
    loaded_token: str | None = None

    def __init__(self, hass: FakeHass, entry_id: str) -> None:
        """Record construction."""
        self.hass = hass
        self.entry_id = entry_id
        self.saved: list[str] = []
        self.removed = False
        self.instances.append(self)

    async def async_load(self) -> str | None:
        """Return the configured private token."""
        return self.loaded_token

    async def async_save(self, token: str) -> None:
        """Record durable token persistence."""
        self.saved.append(token)

    async def async_remove(self) -> None:
        """Record deletion."""
        self.removed = True


class FakeTokenManager:
    """Rotate once when the first API access token is requested."""

    def __init__(
        self,
        session: object,
        refresh_token: str,
        saver: Any,
    ) -> None:
        """Capture token-manager dependencies."""
        self.session = session
        self.refresh_token = refresh_token
        self.saver = saver

    async def async_get_access_token(self) -> str:
        """Persist a synthetic rotation before returning access."""
        await self.saver("synthetic-refresh-rotated")
        return "synthetic-access-token"


class FakeApiClient:
    """Capture the account-wide access-token provider."""

    def __init__(self, session: object, provider: Any) -> None:
        """Store dependencies."""
        self.session = session
        self.provider = provider


class FakeHistoryStore:
    """Record history-store lifecycle without touching disk."""

    instances: list[FakeHistoryStore] = []

    def __init__(
        self,
        hass: FakeHass,
        entry_id: str,
        plant_id: str,
    ) -> None:
        """Capture history scope."""
        self.hass = hass
        self.entry_id = entry_id
        self.plant_id = plant_id
        self.removed = False
        self.instances.append(self)

    async def async_remove(self) -> None:
        """Record archive deletion."""
        self.removed = True


class FakeCoordinator:
    """Perform one synthetic first refresh."""

    def __init__(
        self,
        hass: FakeHass,
        entry: FakeEntry,
        api_client: FakeApiClient,
        plant_id: str,
        *,
        history_store: FakeHistoryStore,
    ) -> None:
        """Store runtime dependencies."""
        self.hass = hass
        self.entry = entry
        self.api_client = api_client
        self.plant_id = plant_id
        self.history_store = history_store
        self.first_refresh_complete = False

    async def async_config_entry_first_refresh(self) -> None:
        """Trigger one token rotation through the API provider."""
        assert await self.api_client.provider() == "synthetic-access-token"
        self.first_refresh_complete = True


@pytest.fixture
def runtime_doubles(monkeypatch: pytest.MonkeyPatch) -> object:
    """Install local-import doubles used by async_setup_entry."""
    session = object()

    homeassistant = ModuleType("homeassistant")
    homeassistant.__path__ = []  # type: ignore[attr-defined]
    helpers = ModuleType("homeassistant.helpers")
    helpers.__path__ = []  # type: ignore[attr-defined]
    aiohttp_client = ModuleType("homeassistant.helpers.aiohttp_client")
    aiohttp_client.async_get_clientsession = lambda hass: session  # type: ignore[attr-defined]

    coordinator = ModuleType("custom_components.sma_sunny_portal.coordinator")
    coordinator.SmaSunnyPortalCoordinator = FakeCoordinator  # type: ignore[attr-defined]
    history = ModuleType("custom_components.sma_sunny_portal.history")
    history.SmaSunnyPortalHistoryStore = FakeHistoryStore  # type: ignore[attr-defined]
    storage = ModuleType("custom_components.sma_sunny_portal.storage")
    storage.SmaSunnyPortalRefreshTokenStore = FakeTokenStore  # type: ignore[attr-defined]

    monkeypatch.setitem(sys.modules, "homeassistant", homeassistant)
    monkeypatch.setitem(sys.modules, "homeassistant.helpers", helpers)
    monkeypatch.setitem(
        sys.modules, "homeassistant.helpers.aiohttp_client", aiohttp_client
    )
    monkeypatch.setitem(
        sys.modules, "custom_components.sma_sunny_portal.coordinator", coordinator
    )
    monkeypatch.setitem(
        sys.modules, "custom_components.sma_sunny_portal.history", history
    )
    monkeypatch.setitem(
        sys.modules, "custom_components.sma_sunny_portal.storage", storage
    )
    monkeypatch.setattr(integration, "SmaSunnyPortalTokenManager", FakeTokenManager)
    monkeypatch.setattr(integration, "SmaSunnyPortalApiClient", FakeApiClient)

    FakeTokenStore.instances.clear()
    FakeTokenStore.loaded_token = None
    FakeHistoryStore.instances.clear()
    return session


def test_setup_bootstraps_private_store_and_builds_runtime(
    runtime_doubles: object,
) -> None:
    """Setup removes bootstrap credentials after durable private persistence."""
    hass = FakeHass()
    entry = FakeEntry(
        {
            "plant_id": "90000000",
            "refresh_token": "synthetic-refresh-bootstrap",
            "preserved": "value",
        }
    )

    assert asyncio.run(async_setup_entry(hass, entry))

    token_store = FakeTokenStore.instances[-1]
    assert token_store.saved == [
        "synthetic-refresh-bootstrap",
        "synthetic-refresh-rotated",
    ]
    assert entry.data == {"plant_id": "90000000", "preserved": "value"}
    assert hass.config_entries.updates == [entry.data]
    assert entry.runtime_data is not None
    assert entry.runtime_data.token_store is token_store
    assert entry.runtime_data.token_manager.refresh_token == (
        "synthetic-refresh-bootstrap"
    )
    assert entry.runtime_data.api_client.session is runtime_doubles
    assert entry.runtime_data.history_store is FakeHistoryStore.instances[-1]
    assert entry.runtime_data.history_store.plant_id == "90000000"
    assert entry.runtime_data.coordinator.history_store is (
        entry.runtime_data.history_store
    )
    assert entry.runtime_data.coordinator.first_refresh_complete
    assert entry.runtime_data.coordinator.plant_id == "90000000"
    assert hass.config_entries.forwarded == [(entry, ("sensor",))]


def test_setup_prefers_latest_private_token(runtime_doubles: object) -> None:
    """A restart never falls back to a stale config-entry bootstrap token."""
    del runtime_doubles
    FakeTokenStore.loaded_token = "synthetic-refresh-private-latest"
    hass = FakeHass()
    entry = FakeEntry(
        {
            "plant_id": "90000000",
            "refresh_token": "synthetic-refresh-stale-bootstrap",
        }
    )

    assert asyncio.run(async_setup_entry(hass, entry))

    runtime = entry.runtime_data
    assert runtime is not None
    assert runtime.token_manager.refresh_token == "synthetic-refresh-private-latest"
    assert FakeTokenStore.instances[-1].saved == ["synthetic-refresh-rotated"]
    assert "refresh_token" not in entry.data
    assert hass.config_entries.forwarded == [(entry, ("sensor",))]


def test_unload_entry_unloads_sensor_platform(runtime_doubles: object) -> None:
    """Unloading an entry delegates to all forwarded entity platforms."""
    del runtime_doubles
    hass = FakeHass()
    entry = FakeEntry({"plant_id": "90000000"})

    assert asyncio.run(async_unload_entry(hass, entry))
    assert hass.config_entries.unloaded == [(entry, ("sensor",))]


def test_remove_entry_deletes_private_token(runtime_doubles: object) -> None:
    """Removing the integration also removes the account credential."""
    del runtime_doubles
    hass = FakeHass()
    entry = FakeEntry({"plant_id": "90000000"})

    asyncio.run(async_remove_entry(hass, entry))

    assert FakeTokenStore.instances[-1].removed
    assert FakeHistoryStore.instances[-1].removed
