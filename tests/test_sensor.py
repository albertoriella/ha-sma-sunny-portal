"""Tests for coordinator-backed forecast sensors."""

from __future__ import annotations

import asyncio
import importlib
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

from custom_components.sma_sunny_portal.models import ConsumerBalance, Prediction

MODULE_NAME = "custom_components.sma_sunny_portal.sensor"


@dataclass(frozen=True, kw_only=True)
class FakeSensorEntityDescription:
    """Minimal Home Assistant sensor description."""

    key: str
    translation_key: str | None = None
    device_class: str | None = None
    native_unit_of_measurement: str | None = None
    suggested_display_precision: int | None = None


class FakeSensorEntity:
    """Stand-in for Home Assistant's SensorEntity."""


class FakeCoordinatorEntity[DataT]:
    """Expose coordinator state like Home Assistant's base entity."""

    def __init__(self, coordinator: Any) -> None:
        """Store the coordinator."""
        self.coordinator = coordinator

    @property
    def available(self) -> bool:
        """Mirror the coordinator update status."""
        return self.coordinator.last_update_success


@pytest.fixture
def sensor_environment(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    """Import sensor.py against the documented Home Assistant surface."""
    homeassistant = ModuleType("homeassistant")
    homeassistant.__path__ = []  # type: ignore[attr-defined]
    components = ModuleType("homeassistant.components")
    components.__path__ = []  # type: ignore[attr-defined]
    sensor = ModuleType("homeassistant.components.sensor")
    sensor.SensorDeviceClass = SimpleNamespace(  # type: ignore[attr-defined]
        POWER="power",
        TIMESTAMP="timestamp",
    )
    sensor.SensorEntity = FakeSensorEntity  # type: ignore[attr-defined]
    sensor.SensorEntityDescription = FakeSensorEntityDescription  # type: ignore[attr-defined]
    const = ModuleType("homeassistant.const")
    const.UnitOfPower = SimpleNamespace(WATT="W")  # type: ignore[attr-defined]
    helpers = ModuleType("homeassistant.helpers")
    helpers.__path__ = []  # type: ignore[attr-defined]
    update_coordinator = ModuleType("homeassistant.helpers.update_coordinator")
    update_coordinator.CoordinatorEntity = FakeCoordinatorEntity  # type: ignore[attr-defined]
    integration_coordinator = ModuleType(
        "custom_components.sma_sunny_portal.coordinator"
    )
    integration_coordinator.SmaSunnyPortalCoordinator = object  # type: ignore[attr-defined]

    modules = {
        "homeassistant": homeassistant,
        "homeassistant.components": components,
        "homeassistant.components.sensor": sensor,
        "homeassistant.const": const,
        "homeassistant.helpers": helpers,
        "homeassistant.helpers.update_coordinator": update_coordinator,
        "custom_components.sma_sunny_portal.coordinator": integration_coordinator,
    }
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)

    sys.modules.pop(MODULE_NAME, None)
    module = importlib.import_module(MODULE_NAME)
    yield module
    sys.modules.pop(MODULE_NAME, None)


def _prediction(
    hour: int,
    minute: int,
    pv_generation_w: float,
    total_consumption_w: float,
) -> Prediction:
    """Build one synthetic UTC prediction."""
    return Prediction(
        time_utc=datetime(2099, 6, 15, hour, minute, tzinfo=UTC),
        pv_generation_w=pv_generation_w,
        total_consumption_w=total_consumption_w,
    )


def _balance(*predictions: Prediction) -> ConsumerBalance:
    """Build a normalized response containing only predictions."""
    return ConsumerBalance((), predictions, (), (), ())


def test_setup_adds_four_stable_translated_entities(
    sensor_environment: ModuleType,
) -> None:
    """The sensor platform exposes one entity per lightweight forecast value."""
    coordinator = SimpleNamespace(
        data=_balance(_prediction(8, 0, 1500, 850)),
        last_update_success=True,
    )
    entry = SimpleNamespace(
        data={"plant_id": "90000000"},
        runtime_data=SimpleNamespace(coordinator=coordinator),
    )
    added: list[Any] = []

    asyncio.run(
        sensor_environment.async_setup_entry(
            object(),
            entry,
            lambda entities: added.extend(entities),
        )
    )

    assert [entity.entity_description.key for entity in added] == [
        "pv_power_forecast",
        "consumption_power_forecast",
        "surplus_power_forecast",
        "next_forecast_time",
    ]
    assert [entity._attr_unique_id for entity in added] == [
        "90000000_pv_power_forecast",
        "90000000_consumption_power_forecast",
        "90000000_surplus_power_forecast",
        "90000000_next_forecast_time",
    ]
    assert all(entity._attr_has_entity_name for entity in added)


def test_sensors_select_first_non_past_interval(
    sensor_environment: ModuleType,
) -> None:
    """All entity values come from the same earliest future sample."""
    now = datetime(2099, 6, 15, 7, 40, tzinfo=UTC)
    coordinator = SimpleNamespace(
        data=_balance(
            _prediction(7, 30, 900, 800),
            _prediction(7, 45, 1300, 820),
            _prediction(8, 0, 1500, 850),
        ),
        last_update_success=True,
    )
    entities = {
        description.key: sensor_environment.SmaSunnyPortalForecastSensor(
            coordinator,
            "90000000",
            description,
            now_provider=lambda: now,
        )
        for description in sensor_environment.SENSOR_DESCRIPTIONS
    }

    assert entities["pv_power_forecast"].native_value == 1300
    assert entities["consumption_power_forecast"].native_value == 820
    assert entities["surplus_power_forecast"].native_value == 480
    assert entities["next_forecast_time"].native_value == datetime(
        2099, 6, 15, 7, 45, tzinfo=UTC
    )
    assert all(entity.available for entity in entities.values())


def test_negative_surplus_is_not_clamped(sensor_environment: ModuleType) -> None:
    """Predicted grid demand remains visible as a negative surplus."""
    description = next(
        item
        for item in sensor_environment.SENSOR_DESCRIPTIONS
        if item.key == "surplus_power_forecast"
    )
    entity = sensor_environment.SmaSunnyPortalForecastSensor(
        SimpleNamespace(
            data=_balance(_prediction(8, 0, 500, 800)),
            last_update_success=True,
        ),
        "90000000",
        description,
        now_provider=lambda: datetime(2099, 6, 15, 7, 45, tzinfo=UTC),
    )

    assert entity.native_value == -300


def test_no_future_prediction_makes_entities_unavailable(
    sensor_environment: ModuleType,
) -> None:
    """A healthy empty forecast never masquerades as a zero prediction."""
    description = sensor_environment.SENSOR_DESCRIPTIONS[0]
    entity = sensor_environment.SmaSunnyPortalForecastSensor(
        SimpleNamespace(
            data=_balance(_prediction(7, 30, 900, 800)),
            last_update_success=True,
        ),
        "90000000",
        description,
        now_provider=lambda: datetime(2099, 6, 15, 8, 0, tzinfo=UTC),
    )

    assert entity.native_value is None
    assert entity.available is False


def test_coordinator_failure_keeps_sensor_unavailable(
    sensor_environment: ModuleType,
) -> None:
    """Future data does not override a failed coordinator update."""
    description = sensor_environment.SENSOR_DESCRIPTIONS[0]
    entity = sensor_environment.SmaSunnyPortalForecastSensor(
        SimpleNamespace(
            data=_balance(_prediction(8, 0, 1500, 850)),
            last_update_success=False,
        ),
        "90000000",
        description,
        now_provider=lambda: datetime(2099, 6, 15, 7, 45, tzinfo=UTC),
    )

    assert entity.native_value == 1500
    assert entity.available is False
