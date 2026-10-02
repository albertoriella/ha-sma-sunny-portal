"""Network-free tests for the Home Assistant configuration flow."""

from __future__ import annotations

import asyncio
import importlib
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

from custom_components.sma_sunny_portal.bootstrap import BootstrapValidationResult
from custom_components.sma_sunny_portal.errors import (
    SmaSunnyPortalAuthenticationError,
    SmaSunnyPortalConnectionError,
    SmaSunnyPortalDataError,
    SmaSunnyPortalRateLimitError,
    SmaSunnyPortalTokenPersistenceError,
)
from custom_components.sma_sunny_portal.models import ConsumerBalance

MODULE_NAME = "custom_components.sma_sunny_portal.config_flow"


class FakeAbortFlow(Exception):
    """Represent a config-flow abort in the lightweight test harness."""

    def __init__(self, reason: str) -> None:
        """Store the translated reason key."""
        self.reason = reason
        super().__init__(reason)


class FakeConfigFlow:
    """Small subset of Home Assistant's ConfigFlow API."""

    configured_ids: set[str] = set()

    def __init_subclass__(cls, *, domain: str | None = None, **kwargs: Any) -> None:
        """Accept Home Assistant's domain class argument."""
        super().__init_subclass__(**kwargs)
        cls.domain = domain

    def __init__(self) -> None:
        """Initialize flow state."""
        self.hass = SimpleNamespace()
        self.unique_id: str | None = None
        self.reauth_entry: FakeEntry | None = None
        self.unique_configured_check = False

    async def async_set_unique_id(self, unique_id: str) -> None:
        """Record the stable account identity."""
        self.unique_id = unique_id

    def _abort_if_unique_id_configured(self) -> None:
        """Reject a duplicate account."""
        self.unique_configured_check = True
        if self.unique_id in self.configured_ids:
            raise FakeAbortFlow("already_configured")

    def _abort_if_unique_id_mismatch(self, *, reason: str) -> None:
        """Prevent switching accounts during reauthentication."""
        assert self.reauth_entry is not None
        if self.unique_id != self.reauth_entry.unique_id:
            raise FakeAbortFlow(reason)

    def _get_reauth_entry(self) -> FakeEntry:
        """Return the entry attached to a reauthentication flow."""
        assert self.reauth_entry is not None
        return self.reauth_entry

    def async_show_form(self, **kwargs: Any) -> dict[str, Any]:
        """Return a serializable form result."""
        return {"type": "form", **kwargs}

    def async_create_entry(self, **kwargs: Any) -> dict[str, Any]:
        """Return a serializable create-entry result."""
        return {"type": "create_entry", **kwargs}

    def async_update_reload_and_abort(
        self,
        entry: FakeEntry,
        *,
        data_updates: dict[str, Any],
    ) -> dict[str, Any]:
        """Apply reauth data and represent the reload abort."""
        entry.data = {**entry.data, **data_updates}
        return {
            "type": "abort",
            "reason": "reauth_successful",
            "data_updates": data_updates,
        }


class FakeTextSelectorType:
    """Selector type constants used by the form schema."""

    TEXT = "text"
    PASSWORD = "password"


@dataclass
class FakeTextSelectorConfig:
    """Capture text selector options."""

    type: str
    autocomplete: str


class FakeTextSelector:
    """Pass text values through probatio validation."""

    def __init__(self, config: FakeTextSelectorConfig) -> None:
        """Store selector configuration."""
        self.config = config

    def __call__(self, value: object) -> object:
        """Return the submitted value unchanged."""
        return value


class FakeTokenStore:
    """Persist reauthentication rotations in memory."""

    instances: list[FakeTokenStore] = []

    def __init__(self, hass: object, entry_id: str) -> None:
        """Record store scope."""
        self.hass = hass
        self.entry_id = entry_id
        self.saved: list[str] = []
        self.instances.append(self)

    async def async_save(self, token: str) -> None:
        """Record one rotated token."""
        self.saved.append(token)


@dataclass
class FakeEntry:
    """Config entry used by reauthentication tests."""

    data: dict[str, Any]
    unique_id: str = "synthetic-account-subject"
    entry_id: str = "synthetic-entry"


@pytest.fixture
def config_flow_module(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    """Import config_flow.py against the documented Home Assistant surface."""
    homeassistant = ModuleType("homeassistant")
    homeassistant.__path__ = []  # type: ignore[attr-defined]
    config_entries = ModuleType("homeassistant.config_entries")
    config_entries.ConfigFlow = FakeConfigFlow  # type: ignore[attr-defined]
    config_entries.ConfigFlowResult = dict  # type: ignore[attr-defined]
    helpers = ModuleType("homeassistant.helpers")
    helpers.__path__ = []  # type: ignore[attr-defined]
    aiohttp_client = ModuleType("homeassistant.helpers.aiohttp_client")
    aiohttp_client.async_get_clientsession = lambda hass: object()  # type: ignore[attr-defined]
    selector = ModuleType("homeassistant.helpers.selector")
    selector.TextSelector = FakeTextSelector  # type: ignore[attr-defined]
    selector.TextSelectorConfig = FakeTextSelectorConfig  # type: ignore[attr-defined]
    selector.TextSelectorType = FakeTextSelectorType  # type: ignore[attr-defined]
    util = ModuleType("homeassistant.util")
    util.__path__ = []  # type: ignore[attr-defined]
    dt = ModuleType("homeassistant.util.dt")
    dt.now = lambda: datetime(2099, 6, 15, 12, 0, tzinfo=UTC)  # type: ignore[attr-defined]
    util.dt = dt  # type: ignore[attr-defined]
    storage = ModuleType("custom_components.sma_sunny_portal.storage")
    storage.SmaSunnyPortalRefreshTokenStore = FakeTokenStore  # type: ignore[attr-defined]

    modules = {
        "homeassistant": homeassistant,
        "homeassistant.config_entries": config_entries,
        "homeassistant.helpers": helpers,
        "homeassistant.helpers.aiohttp_client": aiohttp_client,
        "homeassistant.helpers.selector": selector,
        "homeassistant.util": util,
        "homeassistant.util.dt": dt,
        "custom_components.sma_sunny_portal.storage": storage,
    }
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)

    sys.modules.pop(MODULE_NAME, None)
    FakeConfigFlow.configured_ids.clear()
    FakeTokenStore.instances.clear()
    module = importlib.import_module(MODULE_NAME)
    yield module
    sys.modules.pop(MODULE_NAME, None)


def _validation_result(
    *,
    account_id: str = "synthetic-account-subject",
    refresh_token: str = "synthetic-refresh-rotated",
) -> BootstrapValidationResult:
    """Return successful synthetic validation data."""
    return BootstrapValidationResult(
        account_id=account_id,
        refresh_token=refresh_token,
        consumer_balance=ConsumerBalance((), (), (), (), ()),
    )


def _valid_input() -> dict[str, str]:
    """Return safe manual-bootstrap fields."""
    return {
        "plant_id": "90000000",
        "refresh_token": "synthetic-refresh-bootstrap",
    }


def test_user_flow_creates_entry_with_rotated_token(
    config_flow_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The original token is replaced before the config entry is created."""
    observed_inputs: list[tuple[str, str]] = []

    async def validate(
        session: object,
        plant_id: str,
        refresh_token: str,
        date_local: object,
        *,
        async_observe_rotated_token: Any,
    ) -> BootstrapValidationResult:
        del session, date_local
        observed_inputs.append((plant_id, refresh_token))
        await async_observe_rotated_token("synthetic-refresh-rotated")
        return _validation_result()

    monkeypatch.setattr(config_flow_module, "async_validate_credentials", validate)
    flow = config_flow_module.SmaSunnyPortalConfigFlow()

    result = asyncio.run(flow.async_step_user(_valid_input()))

    assert result["type"] == "create_entry"
    assert result["title"] == "SMA Sunny Portal Forecast"
    assert result["data"] == {
        "plant_id": "90000000",
        "refresh_token": "synthetic-refresh-rotated",
    }
    assert flow.unique_id == "synthetic-account-subject"
    assert flow.unique_configured_check
    assert observed_inputs == [("90000000", "synthetic-refresh-bootstrap")]


def test_user_flow_retries_with_newest_rotated_token(
    config_flow_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A transient API error cannot strand the refresh-token chain."""
    attempted_tokens: list[str] = []

    async def validate(
        session: object,
        plant_id: str,
        refresh_token: str,
        date_local: object,
        *,
        async_observe_rotated_token: Any,
    ) -> BootstrapValidationResult:
        del session, plant_id, date_local
        attempted_tokens.append(refresh_token)
        if len(attempted_tokens) == 1:
            await async_observe_rotated_token("synthetic-refresh-after-failure")
            raise SmaSunnyPortalConnectionError("safe synthetic failure")
        await async_observe_rotated_token("synthetic-refresh-final")
        return _validation_result(refresh_token="synthetic-refresh-final")

    monkeypatch.setattr(config_flow_module, "async_validate_credentials", validate)
    flow = config_flow_module.SmaSunnyPortalConfigFlow()

    first = asyncio.run(flow.async_step_user(_valid_input()))
    second = asyncio.run(flow.async_step_user(_valid_input()))

    assert first["errors"] == {"base": "cannot_connect"}
    assert second["type"] == "create_entry"
    assert attempted_tokens == [
        "synthetic-refresh-bootstrap",
        "synthetic-refresh-after-failure",
    ]


@pytest.mark.parametrize(
    ("error", "expected_key"),
    [
        (SmaSunnyPortalAuthenticationError("safe"), "invalid_auth"),
        (SmaSunnyPortalConnectionError("safe"), "cannot_connect"),
        (SmaSunnyPortalDataError("safe"), "invalid_response"),
        (SmaSunnyPortalRateLimitError("safe"), "rate_limited"),
        (SmaSunnyPortalTokenPersistenceError("safe"), "storage_error"),
    ],
)
def test_user_flow_translates_client_errors(
    config_flow_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    expected_key: str,
) -> None:
    """The UI receives only fixed translation keys, never exception text."""

    async def validate(*args: object, **kwargs: object) -> BootstrapValidationResult:
        del args, kwargs
        raise error

    monkeypatch.setattr(config_flow_module, "async_validate_credentials", validate)
    flow = config_flow_module.SmaSunnyPortalConfigFlow()

    result = asyncio.run(flow.async_step_user(_valid_input()))

    assert result["type"] == "form"
    assert result["errors"] == {"base": expected_key}
    assert "safe" not in str(result)


def test_user_flow_rejects_fields_before_rotation(
    config_flow_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Malformed local fields never reach the token endpoint."""
    called = False

    async def validate(*args: object, **kwargs: object) -> BootstrapValidationResult:
        nonlocal called
        del args, kwargs
        called = True
        return _validation_result()

    monkeypatch.setattr(config_flow_module, "async_validate_credentials", validate)
    flow = config_flow_module.SmaSunnyPortalConfigFlow()

    result = asyncio.run(
        flow.async_step_user(
            {"plant_id": "not-numeric", "refresh_token": "contains whitespace"}
        )
    )

    assert result["errors"] == {"plant_id": "invalid_plant_id"}
    assert not called


def test_user_flow_prevents_duplicate_accounts(
    config_flow_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A stable validated account subject prevents duplicate entries."""

    async def validate(*args: object, **kwargs: object) -> BootstrapValidationResult:
        del args, kwargs
        return _validation_result()

    monkeypatch.setattr(config_flow_module, "async_validate_credentials", validate)
    FakeConfigFlow.configured_ids.add("synthetic-account-subject")
    flow = config_flow_module.SmaSunnyPortalConfigFlow()

    with pytest.raises(FakeAbortFlow, match="already_configured"):
        asyncio.run(flow.async_step_user(_valid_input()))


def test_reauth_persists_rotation_then_reloads_entry(
    config_flow_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reauthentication writes the newest token before entry reload."""

    async def validate(
        session: object,
        plant_id: str,
        refresh_token: str,
        date_local: object,
        *,
        async_observe_rotated_token: Any,
    ) -> BootstrapValidationResult:
        del session, plant_id, refresh_token, date_local
        await async_observe_rotated_token("synthetic-refresh-reauth")
        return _validation_result(refresh_token="synthetic-refresh-reauth")

    monkeypatch.setattr(config_flow_module, "async_validate_credentials", validate)
    flow = config_flow_module.SmaSunnyPortalConfigFlow()
    flow.reauth_entry = FakeEntry({"plant_id": "90000000"})

    result = asyncio.run(
        flow.async_step_reauth_confirm(
            {"refresh_token": "synthetic-refresh-from-browser"}
        )
    )

    assert FakeTokenStore.instances[-1].saved == ["synthetic-refresh-reauth"]
    assert result == {
        "type": "abort",
        "reason": "reauth_successful",
        "data_updates": {"refresh_token": "synthetic-refresh-reauth"},
    }
    assert flow.reauth_entry.data["refresh_token"] == "synthetic-refresh-reauth"


def test_reauth_refuses_different_account(
    config_flow_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A replacement token cannot silently switch the configured account."""

    async def validate(
        session: object,
        plant_id: str,
        refresh_token: str,
        date_local: object,
        *,
        async_observe_rotated_token: Any,
    ) -> BootstrapValidationResult:
        del session, plant_id, refresh_token, date_local
        await async_observe_rotated_token("synthetic-refresh-other-account")
        return _validation_result(account_id="different-synthetic-account")

    monkeypatch.setattr(config_flow_module, "async_validate_credentials", validate)
    flow = config_flow_module.SmaSunnyPortalConfigFlow()
    flow.reauth_entry = FakeEntry({"plant_id": "90000000"})

    with pytest.raises(FakeAbortFlow, match="wrong_account"):
        asyncio.run(
            flow.async_step_reauth_confirm(
                {"refresh_token": "synthetic-refresh-from-browser"}
            )
        )
