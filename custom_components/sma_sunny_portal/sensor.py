"""Forecast sensors for SMA Sunny Portal."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.const import UnitOfPower
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_PLANT_ID
from .coordinator import SmaSunnyPortalCoordinator
from .models import ConsumerBalance, Prediction

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from . import SmaSunnyPortalConfigEntry
type SensorValue = float | datetime
type UtcNowProvider = Callable[[], datetime]
type PredictionValue = Callable[[Prediction], SensorValue]


def _utcnow() -> datetime:
    """Return an aware UTC timestamp."""
    return datetime.now(UTC)


def _next_prediction(
    balance: ConsumerBalance,
    now_utc: datetime,
) -> Prediction | None:
    """Return the first forecast sample that has not started yet."""
    return next(
        (
            prediction
            for prediction in balance.predictions
            if prediction.time_utc >= now_utc
        ),
        None,
    )


@dataclass(frozen=True, kw_only=True)
class SmaSunnyPortalSensorEntityDescription(SensorEntityDescription):
    """Describe a value taken from the next forecast interval."""

    value_fn: PredictionValue


SENSOR_DESCRIPTIONS: tuple[SmaSunnyPortalSensorEntityDescription, ...] = (
    SmaSunnyPortalSensorEntityDescription(
        key="pv_power_forecast",
        translation_key="pv_power_forecast",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
        value_fn=lambda prediction: prediction.pv_generation_w,
    ),
    SmaSunnyPortalSensorEntityDescription(
        key="consumption_power_forecast",
        translation_key="consumption_power_forecast",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
        value_fn=lambda prediction: prediction.total_consumption_w,
    ),
    SmaSunnyPortalSensorEntityDescription(
        key="surplus_power_forecast",
        translation_key="surplus_power_forecast",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
        value_fn=lambda prediction: prediction.surplus_w,
    ),
    SmaSunnyPortalSensorEntityDescription(
        key="next_forecast_time",
        translation_key="next_forecast_time",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda prediction: prediction.time_utc,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SmaSunnyPortalConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up sensors backed by the account coordinator."""
    del hass
    plant_id = entry.data[CONF_PLANT_ID]
    async_add_entities(
        SmaSunnyPortalForecastSensor(
            entry.runtime_data.coordinator,
            plant_id,
            description,
        )
        for description in SENSOR_DESCRIPTIONS
    )


class SmaSunnyPortalForecastSensor(
    CoordinatorEntity[SmaSunnyPortalCoordinator],
    SensorEntity,
):
    """One value from SMA's next quarter-hour forecast interval."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SmaSunnyPortalCoordinator,
        plant_id: str,
        description: SmaSunnyPortalSensorEntityDescription,
        *,
        now_provider: UtcNowProvider = _utcnow,
    ) -> None:
        """Initialize a coordinator-backed forecast sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{plant_id}_{description.key}"
        self._now_provider = now_provider

    @property
    def _prediction(self) -> Prediction | None:
        """Return the next prediction available to this entity."""
        return _next_prediction(self.coordinator.data, self._now_provider())

    @property
    def available(self) -> bool:
        """Require both a successful update and a future forecast sample."""
        return super().available and self._prediction is not None

    @property
    def native_value(self) -> SensorValue | None:
        """Return this entity's value from the next forecast sample."""
        if (prediction := self._prediction) is None:
            return None
        return self.entity_description.value_fn(prediction)
