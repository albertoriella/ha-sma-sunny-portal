"""Normalized immutable models for SMA Sunny Portal data."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class ConsumerMeasurement:
    """Consumption attributed to one configured consumer."""

    component_id: str
    consumption_w: float | None


@dataclass(frozen=True, slots=True)
class Measurement:
    """One measured power sample."""

    time_utc: datetime
    total_generation_w: float
    pv_generation_w: float
    other_generation_w: float | None
    external_consumption_w: float
    total_consumption_w: float
    battery_charging_w: float
    battery_discharging_w: float
    baseload_w: float
    consumers: tuple[ConsumerMeasurement, ...]


@dataclass(frozen=True, slots=True)
class Prediction:
    """One predicted photovoltaic and consumption power sample."""

    time_utc: datetime
    pv_generation_w: float
    total_consumption_w: float

    @property
    def surplus_w(self) -> float:
        """Return predicted generation minus predicted consumption."""
        return self.pv_generation_w - self.total_consumption_w


@dataclass(frozen=True, slots=True)
class WeatherForecast:
    """One hourly Sunny Portal weather-symbol sample."""

    time_utc: datetime
    icon_id: int


@dataclass(frozen=True, slots=True)
class Recommendation:
    """One hourly SMA energy-surplus recommendation."""

    time_utc_start: datetime
    time_utc_end: datetime
    pv_generation_wh: float
    total_consumption_wh: float
    difference_wh: float
    excess_energy: str


@dataclass(frozen=True, slots=True)
class Consumer:
    """A configured consumer advertised by Sunny Portal."""

    component_id: str
    name: str


@dataclass(frozen=True, slots=True)
class ConsumerBalance:
    """Normalized consumer-balance response."""

    measurements: tuple[Measurement, ...]
    predictions: tuple[Prediction, ...]
    weather_forecasts: tuple[WeatherForecast, ...]
    recommendations: tuple[Recommendation, ...]
    consumers: tuple[Consumer, ...]
