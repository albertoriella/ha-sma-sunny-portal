"""Parse Sunny Portal UI API responses into normalized models."""

from __future__ import annotations

import math
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

from .errors import SmaSunnyPortalDataError
from .models import (
    Consumer,
    ConsumerBalance,
    ConsumerMeasurement,
    Measurement,
    Prediction,
    Recommendation,
    WeatherForecast,
)


def _mapping(value: object, path: str) -> Mapping[str, Any]:
    """Return a mapping or raise a path-only validation error."""
    if not isinstance(value, Mapping):
        raise SmaSunnyPortalDataError(f"{path} must be an object")
    return value


def _list(mapping: Mapping[str, Any], key: str, path: str) -> list[Any]:
    """Return a required list field."""
    value = mapping.get(key)
    if not isinstance(value, list):
        raise SmaSunnyPortalDataError(f"{path}.{key} must be an array")
    return value


def _string(mapping: Mapping[str, Any], key: str, path: str) -> str:
    """Return a required non-empty string field."""
    value = mapping.get(key)
    if not isinstance(value, str) or not value:
        raise SmaSunnyPortalDataError(f"{path}.{key} must be a non-empty string")
    return value


def _number(mapping: Mapping[str, Any], key: str, path: str) -> float:
    """Return a required finite numeric field as a float."""
    value = mapping.get(key)
    if (
        isinstance(value, bool)
        or not isinstance(value, int | float)
        or not math.isfinite(value)
    ):
        raise SmaSunnyPortalDataError(f"{path}.{key} must be a finite number")
    return float(value)


def _optional_number(mapping: Mapping[str, Any], key: str, path: str) -> float | None:
    """Return an optional finite numeric field as a float."""
    if mapping.get(key) is None:
        return None
    return _number(mapping, key, path)


def _integer(mapping: Mapping[str, Any], key: str, path: str) -> int:
    """Return a required integer field."""
    value = mapping.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise SmaSunnyPortalDataError(f"{path}.{key} must be an integer")
    return value


def _consumer_measurement(
    value: object, measurement_index: int, consumer_index: int
) -> ConsumerMeasurement:
    """Parse consumption attributed to one configured consumer."""
    path = f"values[{measurement_index}].consumers[{consumer_index}]"
    item = _mapping(value, path)
    return ConsumerMeasurement(
        component_id=_string(item, "componentId", path),
        consumption_w=_optional_number(item, "consumption", path),
    )


def _utc_datetime(mapping: Mapping[str, Any], key: str, path: str) -> datetime:
    """Return a required timezone-aware timestamp normalized to UTC."""
    raw_value = _string(mapping, key, path)
    try:
        parsed = datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
    except ValueError:
        raise SmaSunnyPortalDataError(
            f"{path}.{key} must be an ISO 8601 timestamp"
        ) from None

    if parsed.utcoffset() != timedelta(0):
        raise SmaSunnyPortalDataError(f"{path}.{key} must use UTC")
    return parsed.astimezone(UTC)


def _measurement(value: object, index: int) -> Measurement:
    """Parse one measured value."""
    path = f"values[{index}]"
    item = _mapping(value, path)
    consumer_values = _list(item, "consumers", path)
    consumers = tuple(
        _consumer_measurement(consumer_value, index, consumer_index)
        for consumer_index, consumer_value in enumerate(consumer_values)
    )

    return Measurement(
        time_utc=_utc_datetime(item, "timeUtc", path),
        total_generation_w=_number(item, "totalGeneration", path),
        pv_generation_w=_number(item, "pvGeneration", path),
        other_generation_w=_optional_number(item, "otherGeneration", path),
        external_consumption_w=_number(item, "externalConsumption", path),
        total_consumption_w=_number(item, "totalConsumption", path),
        battery_charging_w=_number(item, "batteryCharging", path),
        battery_discharging_w=_number(item, "batteryDischarging", path),
        baseload_w=_number(item, "baseload", path),
        consumers=consumers,
    )


def _prediction(value: object, index: int) -> Prediction:
    """Parse one predicted value."""
    path = f"predictionValues[{index}]"
    item = _mapping(value, path)
    return Prediction(
        time_utc=_utc_datetime(item, "timeUtc", path),
        pv_generation_w=_number(item, "pvGeneration", path),
        total_consumption_w=_number(item, "totalConsumption", path),
    )


def _weather_forecast(value: object, index: int) -> WeatherForecast:
    """Parse one weather forecast value."""
    path = f"weatherForecast[{index}]"
    item = _mapping(value, path)
    return WeatherForecast(
        time_utc=_utc_datetime(item, "timeUtc", path),
        icon_id=_integer(item, "iconId", path),
    )


def _recommendation(value: object, index: int) -> Recommendation:
    """Parse one hourly recommendation."""
    path = f"recommendations[{index}]"
    item = _mapping(value, path)
    start = _utc_datetime(item, "timeUtcStart", path)
    end = _utc_datetime(item, "timeUtcEnd", path)
    if end <= start:
        raise SmaSunnyPortalDataError(
            f"{path}.timeUtcEnd must be later than timeUtcStart"
        )
    return Recommendation(
        time_utc_start=start,
        time_utc_end=end,
        pv_generation_wh=_number(item, "totalPvGeneration", path),
        total_consumption_wh=_number(item, "totalConsumption", path),
        difference_wh=_number(item, "difference", path),
        excess_energy=_string(item, "excessEnergy", path),
    )


def _consumer(value: object, index: int) -> Consumer:
    """Parse one consumer legend entry."""
    path = f"consumerLegend[{index}]"
    item = _mapping(value, path)
    return Consumer(
        component_id=_string(item, "componentId", path),
        name=_string(item, "name", path),
    )


def parse_consumer_balance(payload: object) -> ConsumerBalance:
    """Parse one complete consumer-balance payload."""
    root = _mapping(payload, "response")

    measurements = tuple(
        sorted(
            (
                _measurement(item, index)
                for index, item in enumerate(_list(root, "values", "response"))
            ),
            key=lambda item: item.time_utc,
        )
    )
    predictions = tuple(
        sorted(
            (
                _prediction(item, index)
                for index, item in enumerate(
                    _list(root, "predictionValues", "response")
                )
            ),
            key=lambda item: item.time_utc,
        )
    )
    weather_forecasts = tuple(
        sorted(
            (
                _weather_forecast(item, index)
                for index, item in enumerate(_list(root, "weatherForecast", "response"))
            ),
            key=lambda item: item.time_utc,
        )
    )
    recommendations = tuple(
        sorted(
            (
                _recommendation(item, index)
                for index, item in enumerate(_list(root, "recommendations", "response"))
            ),
            key=lambda item: item.time_utc_start,
        )
    )
    consumers = tuple(
        _consumer(item, index)
        for index, item in enumerate(_list(root, "consumerLegend", "response"))
    )

    return ConsumerBalance(
        measurements=measurements,
        predictions=predictions,
        weather_forecasts=weather_forecasts,
        recommendations=recommendations,
        consumers=consumers,
    )
