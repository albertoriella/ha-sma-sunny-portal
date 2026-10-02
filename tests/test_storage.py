"""Tests for private refresh-token storage."""

from __future__ import annotations

import asyncio
import importlib
import sys
from types import ModuleType
from typing import Any

import pytest

from custom_components.sma_sunny_portal.errors import (
    SmaSunnyPortalTokenPersistenceError,
)

MODULE_NAME = "custom_components.sma_sunny_portal.storage"


class FakeStore:
    """Small stand-in for Home Assistant's storage helper."""

    instances: list[FakeStore] = []

    def __class_getitem__(cls, item: object) -> type[FakeStore]:
        """Support Store[...] at runtime."""
        del item
        return cls

    def __init__(
        self,
        hass: object,
        version: int,
        key: str,
        **kwargs: Any,
    ) -> None:
        """Record construction options."""
        self.hass = hass
        self.version = version
        self.key = key
        self.kwargs = kwargs
        self.loaded: object = None
        self.saved: list[object] = []
        self.removed = False
        self.load_error: Exception | None = None
        self.save_error: Exception | None = None
        self.remove_error: Exception | None = None
        self.instances.append(self)

    async def async_load(self) -> object:
        """Return configured storage data."""
        if self.load_error is not None:
            raise self.load_error
        return self.loaded

    async def async_save(self, payload: object) -> None:
        """Record one immediate save."""
        if self.save_error is not None:
            raise self.save_error
        self.saved.append(payload)

    async def async_remove(self) -> None:
        """Record removal."""
        if self.remove_error is not None:
            raise self.remove_error
        self.removed = True


@pytest.fixture
def storage_module(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    """Import storage.py against minimal Home Assistant API doubles."""
    homeassistant = ModuleType("homeassistant")
    homeassistant.__path__ = []  # type: ignore[attr-defined]
    core = ModuleType("homeassistant.core")
    core.HomeAssistant = object  # type: ignore[attr-defined]
    helpers = ModuleType("homeassistant.helpers")
    helpers.__path__ = []  # type: ignore[attr-defined]
    storage = ModuleType("homeassistant.helpers.storage")
    storage.Store = FakeStore  # type: ignore[attr-defined]

    monkeypatch.setitem(sys.modules, "homeassistant", homeassistant)
    monkeypatch.setitem(sys.modules, "homeassistant.core", core)
    monkeypatch.setitem(sys.modules, "homeassistant.helpers", helpers)
    monkeypatch.setitem(sys.modules, "homeassistant.helpers.storage", storage)
    sys.modules.pop(MODULE_NAME, None)
    FakeStore.instances.clear()

    module = importlib.import_module(MODULE_NAME)
    yield module
    sys.modules.pop(MODULE_NAME, None)


def test_store_is_private_entry_scoped_and_atomic(storage_module: ModuleType) -> None:
    """Credentials use immediate private atomic Home Assistant storage."""
    token_store = storage_module.SmaSunnyPortalRefreshTokenStore(
        object(), "synthetic-entry"
    )
    store = FakeStore.instances[-1]

    assert token_store is not None
    assert store.version == 1
    assert store.key == "sma_sunny_portal.auth.synthetic-entry"
    assert store.kwargs == {"private": True, "atomic_writes": True}


def test_store_round_trip_never_transforms_token(storage_module: ModuleType) -> None:
    """The exact rotated token is written and can be loaded again."""
    token_store = storage_module.SmaSunnyPortalRefreshTokenStore(
        object(), "synthetic-entry"
    )
    store = FakeStore.instances[-1]

    asyncio.run(token_store.async_save("synthetic-refresh-rotated"))
    store.loaded = {"refresh_token": "synthetic-refresh-rotated"}
    loaded = asyncio.run(token_store.async_load())

    assert store.saved == [{"refresh_token": "synthetic-refresh-rotated"}]
    assert loaded == "synthetic-refresh-rotated"


def test_store_accepts_missing_initial_data(storage_module: ModuleType) -> None:
    """A new config entry has no private token before bootstrap."""
    token_store = storage_module.SmaSunnyPortalRefreshTokenStore(
        object(), "synthetic-entry"
    )

    assert asyncio.run(token_store.async_load()) is None


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {},
        {"refresh_token": ""},
        {"refresh_token": "contains whitespace"},
    ],
)
def test_store_rejects_malformed_data_without_echoing_it(
    storage_module: ModuleType,
    payload: object,
) -> None:
    """Corrupt credentials fail closed and never appear in errors."""
    token_store = storage_module.SmaSunnyPortalRefreshTokenStore(
        object(), "synthetic-entry"
    )
    FakeStore.instances[-1].loaded = payload

    with pytest.raises(SmaSunnyPortalTokenPersistenceError) as raised:
        asyncio.run(token_store.async_load())

    assert "contains whitespace" not in str(raised.value)


def test_store_redacts_storage_failures(storage_module: ModuleType) -> None:
    """Underlying storage exception text cannot leak a token."""
    token_store = storage_module.SmaSunnyPortalRefreshTokenStore(
        object(), "synthetic-entry"
    )
    FakeStore.instances[-1].save_error = RuntimeError(
        "synthetic-refresh-secret must not leak"
    )

    with pytest.raises(SmaSunnyPortalTokenPersistenceError) as raised:
        asyncio.run(token_store.async_save("synthetic-refresh-secret"))

    assert "synthetic-refresh-secret" not in str(raised.value)
    assert raised.value.__cause__ is None


def test_store_removes_credentials(storage_module: ModuleType) -> None:
    """Deleting a config entry also deletes its private token file."""
    token_store = storage_module.SmaSunnyPortalRefreshTokenStore(
        object(), "synthetic-entry"
    )
    store = FakeStore.instances[-1]

    asyncio.run(token_store.async_remove())

    assert store.removed
