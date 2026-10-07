"""Tests for the authenticated forecast-history WebSocket command."""

from __future__ import annotations

import asyncio
import importlib
import sys
from datetime import UTC, datetime
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

from custom_components.sma_sunny_portal.errors import SmaSunnyPortalHistoryError
from custom_components.sma_sunny_portal.history import (
    ArchivedDay,
    ArchivedMeasurement,
    ArchivedPrediction,
)

MODULE_NAME = "custom_components.sma_sunny_portal.websocket"


class FakeConnection:
    """Capture Home Assistant WebSocket replies."""

    def __init__(self) -> None:
        """Initialize result and error collections."""
        self.results: list[tuple[int, dict[str, Any]]] = []
        self.errors: list[tuple[int, str, str]] = []

    def send_result(self, message_id: int, result: dict[str, Any]) -> None:
        """Record one successful response."""
        self.results.append((message_id, result))

    def send_error(self, message_id: int, code: str, message: str) -> None:
        """Record one fixed public error."""
        self.errors.append((message_id, code, message))


class FakeHistoryStore:
    """Return one configured archive response and record requested bounds."""

    def __init__(self, result: ArchivedDay) -> None:
        """Store the synthetic archive response."""
        self.result = result
        self.calls: list[tuple[datetime, datetime, str]] = []
        self.error: Exception | None = None

    async def async_get_day(
        self,
        start_utc: datetime,
        end_utc: datetime,
        mode: str,
    ) -> ArchivedDay:
        """Return or fail after recording the request."""
        self.calls.append((start_utc, end_utc, mode))
        if self.error is not None:
            raise self.error
        return self.result


class FakeConfigEntries:
    """Look up one optional synthetic config entry."""

    def __init__(self, entry: SimpleNamespace | None) -> None:
        """Store the entry."""
        self.entry = entry

    def async_get_entry(self, entry_id: str) -> SimpleNamespace | None:
        """Return the entry only for its exact ID."""
        if self.entry is None or self.entry.entry_id != entry_id:
            return None
        return self.entry

    def async_entries(self, domain: str) -> list[SimpleNamespace]:
        """Return the synthetic entry only for its integration domain."""
        if self.entry is None or self.entry.domain != domain:
            return []
        return [self.entry]


class FakeHass:
    """Minimal Home Assistant instance for a history query."""

    def __init__(
        self,
        store: FakeHistoryStore,
        *,
        domain: str = "sma_sunny_portal",
        loaded: bool = True,
        time_zone: str = "Europe/Rome",
    ) -> None:
        """Build one config entry and time-zone configuration."""
        runtime_data = SimpleNamespace(history_store=store) if loaded else None
        entry = SimpleNamespace(
            entry_id="synthetic-entry",
            domain=domain,
            title="Synthetic SMA plant",
            runtime_data=runtime_data,
        )
        self.config_entries = FakeConfigEntries(entry)
        self.config = SimpleNamespace(time_zone=time_zone)
        self.registered_commands: list[Any] = []


@pytest.fixture
def websocket_module(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    """Import websocket.py against the documented Home Assistant surface."""
    homeassistant = ModuleType("homeassistant")
    homeassistant.__path__ = []  # type: ignore[attr-defined]
    components = ModuleType("homeassistant.components")
    components.__path__ = []  # type: ignore[attr-defined]
    websocket_api = ModuleType("homeassistant.components.websocket_api")

    def websocket_command(schema: object) -> Any:
        """Attach the schema while leaving the test handler callable."""

        def decorator(target: Any) -> Any:
            target.websocket_schema = schema
            return target

        return decorator

    def async_response(target: Any) -> Any:
        """Keep asynchronous handlers unchanged."""
        return target

    def async_register_command(hass: FakeHass, command: Any) -> None:
        """Record registration on the synthetic Home Assistant instance."""
        hass.registered_commands.append(command)

    websocket_api.websocket_command = websocket_command  # type: ignore[attr-defined]
    websocket_api.async_response = async_response  # type: ignore[attr-defined]
    websocket_api.async_register_command = async_register_command  # type: ignore[attr-defined]
    websocket_api.ActiveConnection = FakeConnection  # type: ignore[attr-defined]
    components.websocket_api = websocket_api  # type: ignore[attr-defined]
    core = ModuleType("homeassistant.core")
    core.HomeAssistant = FakeHass  # type: ignore[attr-defined]

    modules = {
        "homeassistant": homeassistant,
        "homeassistant.components": components,
        "homeassistant.components.websocket_api": websocket_api,
        "homeassistant.core": core,
    }
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)

    sys.modules.pop(MODULE_NAME, None)
    module = importlib.import_module(MODULE_NAME)
    yield module
    sys.modules.pop(MODULE_NAME, None)


def _archived_day() -> ArchivedDay:
    """Return actual and predicted points with deliberately distinct values."""
    actual_time = datetime(2026, 10, 25, 10, tzinfo=UTC)
    predicted_time = datetime(2026, 10, 25, 10, 15, tzinfo=UTC)
    issued_time = datetime(2026, 10, 24, 21, tzinfo=UTC)
    return ArchivedDay(
        measurements=(ArchivedMeasurement(actual_time, 900, 650),),
        predictions=(ArchivedPrediction(predicted_time, issued_time, 1200, 700),),
        first_available_utc=actual_time,
        last_available_utc=predicted_time,
    )


def test_history_command_serializes_curves_and_dst_day(
    websocket_module: ModuleType,
) -> None:
    """The response uses the configured local day, including a 25-hour DST day."""
    store = FakeHistoryStore(_archived_day())
    hass = FakeHass(store)
    connection = FakeConnection()

    asyncio.run(
        websocket_module.websocket_get_history(
            hass,
            connection,
            {
                "id": 7,
                "type": "sma_sunny_portal/history",
                "config_entry_id": "synthetic-entry",
                "date": "2026-10-25",
                "mode": "day_ahead",
            },
        )
    )

    assert connection.errors == []
    assert store.calls == [
        (
            datetime(2026, 10, 24, 22, tzinfo=UTC),
            datetime(2026, 10, 25, 23, tzinfo=UTC),
            "day_ahead",
        )
    ]
    message_id, result = connection.results[0]
    assert message_id == 7
    assert result["timezone"] == "Europe/Rome"
    assert result["day_start_utc"] == "2026-10-24T22:00:00+00:00"
    assert result["day_end_utc"] == "2026-10-25T23:00:00+00:00"
    assert result["archive"] == {
        "first_available_utc": "2026-10-25T10:00:00+00:00",
        "last_available_utc": "2026-10-25T10:15:00+00:00",
    }
    assert result["measurements"] == [
        {
            "time_utc": "2026-10-25T10:00:00+00:00",
            "pv_generation_w": 900,
            "total_consumption_w": 650,
            "surplus_w": 250,
        }
    ]
    assert result["predictions"] == [
        {
            "time_utc": "2026-10-25T10:15:00+00:00",
            "issued_at_utc": "2026-10-24T21:00:00+00:00",
            "pv_generation_w": 1200,
            "total_consumption_w": 700,
            "surplus_w": 500,
        }
    ]
    assert result["accuracy"] == {
        "interval_seconds": 900,
        "measurement_points": 1,
        "forecast_points": 1,
        "eligible_points": 0,
        "matched_points": 0,
        "coverage_percent": None,
        "first_matched_utc": None,
        "last_matched_utc": None,
        "pv_generation": None,
        "total_consumption": None,
    }


def test_history_command_serializes_accuracy_metrics(
    websocket_module: ModuleType,
) -> None:
    """Matched actual and forecast points include compact quality metrics."""
    target = datetime(2026, 10, 25, 10, tzinfo=UTC)
    store = FakeHistoryStore(
        ArchivedDay(
            measurements=(ArchivedMeasurement(target, 900, 650),),
            predictions=(
                ArchivedPrediction(
                    target,
                    datetime(2026, 10, 24, 21, tzinfo=UTC),
                    1200,
                    700,
                ),
            ),
            first_available_utc=target,
            last_available_utc=target,
        )
    )
    connection = FakeConnection()

    asyncio.run(
        websocket_module.websocket_get_history(
            FakeHass(store),
            connection,
            {
                "id": 13,
                "config_entry_id": "synthetic-entry",
                "date": "2026-10-25",
                "mode": "day_ahead",
            },
        )
    )

    accuracy = connection.results[0][1]["accuracy"]
    assert accuracy["eligible_points"] == 1
    assert accuracy["matched_points"] == 1
    assert accuracy["coverage_percent"] == 100
    assert accuracy["first_matched_utc"] == "2026-10-25T10:00:00+00:00"
    assert accuracy["last_matched_utc"] == "2026-10-25T10:00:00+00:00"
    assert accuracy["pv_generation"] == {
        "actual_energy_wh": 225,
        "forecast_energy_wh": 300,
        "energy_error_wh": 75,
        "energy_error_percent": pytest.approx(100 / 3),
        "mae_w": 300,
        "rmse_w": 300,
        "bias_w": 300,
        "wape_percent": pytest.approx(100 / 3),
    }
    assert accuracy["total_consumption"] == {
        "actual_energy_wh": 162.5,
        "forecast_energy_wh": 175,
        "energy_error_wh": 12.5,
        "energy_error_percent": pytest.approx(100 / 13),
        "mae_w": 50,
        "rmse_w": 50,
        "bias_w": 50,
        "wape_percent": pytest.approx(100 / 13),
    }


def test_history_command_defaults_to_latest(websocket_module: ModuleType) -> None:
    """The callable remains safe when a lightweight test bypasses schema defaults."""
    store = FakeHistoryStore(ArchivedDay((), (), None, None))
    hass = FakeHass(store)
    connection = FakeConnection()

    asyncio.run(
        websocket_module.websocket_get_history(
            hass,
            connection,
            {
                "id": 8,
                "type": "sma_sunny_portal/history",
                "config_entry_id": "synthetic-entry",
                "date": "2026-10-26",
            },
        )
    )

    assert store.calls[0][2] == "latest"
    assert connection.results[0][1]["measurements"] == []
    assert connection.results[0][1]["predictions"] == []


@pytest.mark.parametrize("value", ["2026-02-30", "20261025", "not-a-date"])
def test_history_command_rejects_noncanonical_dates(
    websocket_module: ModuleType,
    value: str,
) -> None:
    """Malformed dates return a stable public error without querying storage."""
    store = FakeHistoryStore(ArchivedDay((), (), None, None))
    connection = FakeConnection()

    asyncio.run(
        websocket_module.websocket_get_history(
            FakeHass(store),
            connection,
            {
                "id": 9,
                "config_entry_id": "synthetic-entry",
                "date": value,
            },
        )
    )

    assert store.calls == []
    assert connection.errors[0][1] == "invalid_date"


@pytest.mark.parametrize(
    ("domain", "loaded", "expected_code"),
    [
        ("different_domain", True, "entry_not_found"),
        ("sma_sunny_portal", False, "entry_not_loaded"),
    ],
)
def test_history_command_validates_entry_scope_and_runtime(
    websocket_module: ModuleType,
    domain: str,
    loaded: bool,
    expected_code: str,
) -> None:
    """Another integration or an unloaded entry cannot expose this archive."""
    store = FakeHistoryStore(ArchivedDay((), (), None, None))
    connection = FakeConnection()

    asyncio.run(
        websocket_module.websocket_get_history(
            FakeHass(store, domain=domain, loaded=loaded),
            connection,
            {
                "id": 10,
                "config_entry_id": "synthetic-entry",
                "date": "2026-10-25",
            },
        )
    )

    assert store.calls == []
    assert connection.errors[0][1] == expected_code


def test_history_command_redacts_archive_failures(
    websocket_module: ModuleType,
) -> None:
    """Storage failures become one fixed WebSocket error without private details."""
    store = FakeHistoryStore(ArchivedDay((), (), None, None))
    store.error = SmaSunnyPortalHistoryError("secret database path")
    connection = FakeConnection()

    asyncio.run(
        websocket_module.websocket_get_history(
            FakeHass(store),
            connection,
            {
                "id": 11,
                "config_entry_id": "synthetic-entry",
                "date": "2026-10-25",
                "mode": "rolling",
            },
        )
    )

    assert connection.results == []
    assert connection.errors[0][1] == "history_unavailable"
    assert "secret database path" not in str(connection.errors)


def test_registers_history_command(websocket_module: ModuleType) -> None:
    """Component setup registers both authenticated frontend commands."""
    hass = FakeHass(FakeHistoryStore(ArchivedDay((), (), None, None)))

    websocket_module.async_register_websocket_commands(hass)

    assert hass.registered_commands == [
        websocket_module.websocket_get_history,
        websocket_module.websocket_get_entries,
    ]


def test_entries_command_returns_only_safe_card_metadata(
    websocket_module: ModuleType,
) -> None:
    """The card can discover one entry without receiving plant data or tokens."""
    store = FakeHistoryStore(ArchivedDay((), (), None, None))
    hass = FakeHass(store)
    connection = FakeConnection()

    asyncio.run(
        websocket_module.websocket_get_entries(
            hass,
            connection,
            {
                "id": 12,
                "type": "sma_sunny_portal/entries",
            },
        )
    )

    assert connection.errors == []
    assert connection.results == [
        (
            12,
            {
                "entries": [
                    {
                        "entry_id": "synthetic-entry",
                        "title": "Synthetic SMA plant",
                        "loaded": True,
                    }
                ]
            },
        )
    ]
    assert "plant_id" not in str(connection.results)
    assert "refresh_token" not in str(connection.results)
