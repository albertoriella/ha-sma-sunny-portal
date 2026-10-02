"""Tests for the Home Assistant data coordinator adapter."""

from __future__ import annotations

import asyncio
import importlib
import sys
from datetime import date
from types import ModuleType, SimpleNamespace

import pytest

from custom_components.sma_sunny_portal.errors import (
    SmaSunnyPortalAuthenticationError,
    SmaSunnyPortalConnectionError,
)
from custom_components.sma_sunny_portal.models import ConsumerBalance

MODULE_NAME = "custom_components.sma_sunny_portal.coordinator"


class FakeConfigEntryAuthFailed(Exception):
    """Stand-in for Home Assistant's terminal auth exception."""


class FakeUpdateFailed(Exception):
    """Stand-in for Home Assistant's retryable update exception."""


class FakeDataUpdateCoordinator[DataT]:
    """Capture coordinator construction without importing Home Assistant."""

    def __init__(self, hass: object, logger: object, **kwargs: object) -> None:
        """Record constructor values used by the integration."""
        self.hass = hass
        self.logger = logger
        self.name = kwargs["name"]
        self.config_entry = kwargs["config_entry"]
        self.update_interval = kwargs["update_interval"]
        self.always_update = kwargs["always_update"]


@pytest.fixture
def coordinator_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> SimpleNamespace:
    """Import coordinator.py against the documented Home Assistant surface."""
    homeassistant = ModuleType("homeassistant")
    homeassistant.__path__ = []  # type: ignore[attr-defined]
    config_entries = ModuleType("homeassistant.config_entries")
    config_entries.ConfigEntry = object  # type: ignore[attr-defined]
    core = ModuleType("homeassistant.core")
    core.HomeAssistant = object  # type: ignore[attr-defined]
    exceptions = ModuleType("homeassistant.exceptions")
    exceptions.ConfigEntryAuthFailed = FakeConfigEntryAuthFailed  # type: ignore[attr-defined]
    helpers = ModuleType("homeassistant.helpers")
    helpers.__path__ = []  # type: ignore[attr-defined]
    update_coordinator = ModuleType("homeassistant.helpers.update_coordinator")
    update_coordinator.DataUpdateCoordinator = FakeDataUpdateCoordinator  # type: ignore[attr-defined]
    update_coordinator.UpdateFailed = FakeUpdateFailed  # type: ignore[attr-defined]
    util = ModuleType("homeassistant.util")
    util.__path__ = []  # type: ignore[attr-defined]
    dt = ModuleType("homeassistant.util.dt")
    dt.now = lambda: None  # type: ignore[attr-defined]
    util.dt = dt  # type: ignore[attr-defined]

    modules = {
        "homeassistant": homeassistant,
        "homeassistant.config_entries": config_entries,
        "homeassistant.core": core,
        "homeassistant.exceptions": exceptions,
        "homeassistant.helpers": helpers,
        "homeassistant.helpers.update_coordinator": update_coordinator,
        "homeassistant.util": util,
        "homeassistant.util.dt": dt,
    }
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)

    sys.modules.pop(MODULE_NAME, None)
    module = importlib.import_module(MODULE_NAME)
    yield SimpleNamespace(
        module=module,
        auth_error=FakeConfigEntryAuthFailed,
        update_error=FakeUpdateFailed,
    )
    sys.modules.pop(MODULE_NAME, None)


class FakeApiClient:
    """Return a value or raise one configured integration error."""

    def __init__(
        self,
        result: ConsumerBalance | None = None,
        error: Exception | None = None,
    ) -> None:
        """Initialize the fake client."""
        self.result = result
        self.error = error
        self.calls: list[tuple[str, date]] = []

    async def async_get_consumer_balance(
        self,
        plant_id: str,
        date_local: date,
    ) -> ConsumerBalance:
        """Record the fetch and return or raise."""
        self.calls.append((plant_id, date_local))
        if self.error is not None:
            raise self.error
        assert self.result is not None
        return self.result


def _empty_balance() -> ConsumerBalance:
    """Return a valid empty normalized response."""
    return ConsumerBalance((), (), (), (), ())


def test_coordinator_fetches_one_local_day(
    coordinator_environment: SimpleNamespace,
) -> None:
    """The coordinator polls once with the configured plant and local date."""
    api_client = FakeApiClient(result=_empty_balance())
    local_date = date(2099, 6, 15)
    config_entry = object()
    coordinator = coordinator_environment.module.SmaSunnyPortalCoordinator(
        object(),
        config_entry,
        api_client,
        "90000000",
        local_date_provider=lambda: local_date,
    )

    result = asyncio.run(coordinator._async_update_data())

    assert result == _empty_balance()
    assert api_client.calls == [("90000000", local_date)]
    assert coordinator.config_entry is config_entry
    assert coordinator.update_interval.total_seconds() == 900
    assert coordinator.always_update is False


def test_coordinator_marks_authentication_as_terminal(
    coordinator_environment: SimpleNamespace,
) -> None:
    """Invalid credentials stop polling and request config-entry reauth."""
    error = SmaSunnyPortalAuthenticationError("safe synthetic auth failure")
    coordinator = coordinator_environment.module.SmaSunnyPortalCoordinator(
        object(),
        object(),
        FakeApiClient(error=error),
        "90000000",
        local_date_provider=lambda: date(2099, 6, 15),
    )

    with pytest.raises(coordinator_environment.auth_error) as raised:
        asyncio.run(coordinator._async_update_data())

    assert raised.value.__cause__ is error


def test_coordinator_marks_transport_failure_as_retryable(
    coordinator_environment: SimpleNamespace,
) -> None:
    """Transient service failures become DataUpdateCoordinator failures."""
    error = SmaSunnyPortalConnectionError("safe synthetic connection failure")
    coordinator = coordinator_environment.module.SmaSunnyPortalCoordinator(
        object(),
        object(),
        FakeApiClient(error=error),
        "90000000",
        local_date_provider=lambda: date(2099, 6, 15),
    )

    with pytest.raises(coordinator_environment.update_error) as raised:
        asyncio.run(coordinator._async_update_data())

    assert raised.value.__cause__ is error
    assert "safe synthetic connection failure" in str(raised.value)
