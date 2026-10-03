"""Tests for Home Assistant Energy dashboard forecast support."""

from __future__ import annotations

import asyncio
import importlib
import sys
from datetime import UTC, datetime
from types import ModuleType, SimpleNamespace

import pytest

from custom_components.sma_sunny_portal.models import (
    ConsumerBalance,
    Recommendation,
)

MODULE_NAME = "custom_components.sma_sunny_portal.energy"


class FakeRuntimeData:
    """Runtime type used by the energy platform type guard."""

    def __init__(self, balance: ConsumerBalance) -> None:
        """Expose normalized coordinator data."""
        self.coordinator = SimpleNamespace(data=balance)


@pytest.fixture
def energy_environment(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    """Import energy.py against a minimal Home Assistant surface."""
    homeassistant = ModuleType("homeassistant")
    homeassistant.__path__ = []  # type: ignore[attr-defined]
    core = ModuleType("homeassistant.core")
    core.HomeAssistant = object  # type: ignore[attr-defined]
    runtime = ModuleType("custom_components.sma_sunny_portal.runtime")
    runtime.SmaSunnyPortalRuntimeData = FakeRuntimeData  # type: ignore[attr-defined]

    monkeypatch.setitem(sys.modules, "homeassistant", homeassistant)
    monkeypatch.setitem(sys.modules, "homeassistant.core", core)
    monkeypatch.setitem(
        sys.modules,
        "custom_components.sma_sunny_portal.runtime",
        runtime,
    )

    sys.modules.pop(MODULE_NAME, None)
    module = importlib.import_module(MODULE_NAME)
    yield module
    sys.modules.pop(MODULE_NAME, None)


def _recommendation(
    hour: int,
    pv_generation_wh: float,
) -> Recommendation:
    """Build one synthetic hourly recommendation."""
    return Recommendation(
        time_utc_start=datetime(2099, 6, 15, hour, tzinfo=UTC),
        time_utc_end=datetime(2099, 6, 15, hour + 1, tzinfo=UTC),
        pv_generation_wh=pv_generation_wh,
        total_consumption_wh=800,
        difference_wh=pv_generation_wh - 800,
        excess_energy="Mid",
    )


def _balance(*recommendations: Recommendation) -> ConsumerBalance:
    """Build a normalized response containing only recommendations."""
    return ConsumerBalance((), (), (), recommendations, ())


def _hass(entry: object | None) -> SimpleNamespace:
    """Build a Home Assistant stand-in with one config-entry lookup."""
    return SimpleNamespace(
        config_entries=SimpleNamespace(
            async_get_entry=lambda _entry_id: entry,
        )
    )


def test_energy_forecast_uses_hourly_sma_energy(
    energy_environment: ModuleType,
) -> None:
    """Recommendation totals are exposed without power integration drift."""
    entry = SimpleNamespace(
        runtime_data=FakeRuntimeData(
            _balance(
                _recommendation(7, 900),
                _recommendation(8, 1600),
            )
        )
    )

    result = asyncio.run(
        energy_environment.async_get_solar_forecast(
            _hass(entry),
            "entry-1",
        )
    )

    assert result == {
        "wh_hours": {
            "2099-06-15T07:00:00+00:00": 900,
            "2099-06-15T08:00:00+00:00": 1600,
        }
    }


@pytest.mark.parametrize(
    "entry",
    [
        None,
        SimpleNamespace(runtime_data=object()),
    ],
)
def test_energy_forecast_rejects_missing_or_foreign_runtime(
    energy_environment: ModuleType,
    entry: object | None,
) -> None:
    """Only a loaded SMA config entry can provide an Energy forecast."""
    result = asyncio.run(
        energy_environment.async_get_solar_forecast(
            _hass(entry),
            "entry-1",
        )
    )

    assert result is None


def test_energy_forecast_keeps_daytime_zero_and_skips_midnight_zero(
    energy_environment: ModuleType,
) -> None:
    """Mirror Home Assistant's Forecast.Solar midnight-zero convention."""
    midnight = Recommendation(
        time_utc_start=datetime(2099, 6, 15, 0, tzinfo=UTC),
        time_utc_end=datetime(2099, 6, 15, 1, tzinfo=UTC),
        pv_generation_wh=0,
        total_consumption_wh=800,
        difference_wh=-800,
        excess_energy="Low",
    )
    entry = SimpleNamespace(
        runtime_data=FakeRuntimeData(
            _balance(midnight, _recommendation(7, 0))
        )
    )

    result = asyncio.run(
        energy_environment.async_get_solar_forecast(
            _hass(entry),
            "entry-1",
        )
    )

    assert result == {
        "wh_hours": {
            "2099-06-15T07:00:00+00:00": 0,
        }
    }


def test_energy_forecast_can_be_temporarily_empty(
    energy_environment: ModuleType,
) -> None:
    """Portal ingestion delay remains a valid empty forecast response."""
    entry = SimpleNamespace(runtime_data=FakeRuntimeData(_balance()))

    result = asyncio.run(
        energy_environment.async_get_solar_forecast(
            _hass(entry),
            "entry-1",
        )
    )

    assert result == {"wh_hours": {}}
