"""Forecast-accuracy metrics for archived SMA power curves."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import fsum, sqrt

from .history import ArchivedDay

ACCURACY_INTERVAL_SECONDS = 15 * 60
_SECONDS_PER_HOUR = 60 * 60
_ZERO_TOLERANCE = 1e-9


@dataclass(frozen=True, slots=True)
class AccuracySeries:
    """Accuracy metrics for one forecasted physical quantity."""

    actual_energy_wh: float
    forecast_energy_wh: float
    energy_error_wh: float
    energy_error_percent: float | None
    mae_w: float
    rmse_w: float
    bias_w: float
    wape_percent: float | None


@dataclass(frozen=True, slots=True)
class ForecastAccuracy:
    """Accuracy summary for the selected day and forecast provenance mode."""

    interval_seconds: int
    measurement_points: int
    forecast_points: int
    eligible_points: int
    matched_points: int
    coverage_percent: float | None
    first_matched_utc: datetime | None
    last_matched_utc: datetime | None
    pv_generation: AccuracySeries | None
    total_consumption: AccuracySeries | None


def _series_accuracy(
    values: tuple[tuple[float, float], ...],
) -> AccuracySeries | None:
    """Calculate metrics from ``(actual, forecast)`` power pairs."""
    if not values:
        return None

    actual_values = tuple(actual for actual, _forecast in values)
    forecast_values = tuple(forecast for _actual, forecast in values)
    errors = tuple(
        forecast - actual
        for actual, forecast in zip(actual_values, forecast_values, strict=True)
    )
    interval_hours = ACCURACY_INTERVAL_SECONDS / _SECONDS_PER_HOUR
    actual_energy_wh = fsum(actual_values) * interval_hours
    forecast_energy_wh = fsum(forecast_values) * interval_hours
    energy_error_wh = forecast_energy_wh - actual_energy_wh
    absolute_actual_sum = fsum(abs(value) for value in actual_values)

    return AccuracySeries(
        actual_energy_wh=actual_energy_wh,
        forecast_energy_wh=forecast_energy_wh,
        energy_error_wh=energy_error_wh,
        energy_error_percent=(
            energy_error_wh / actual_energy_wh * 100
            if abs(actual_energy_wh) > _ZERO_TOLERANCE
            else None
        ),
        mae_w=fsum(abs(error) for error in errors) / len(errors),
        rmse_w=sqrt(fsum(error * error for error in errors) / len(errors)),
        bias_w=fsum(errors) / len(errors),
        wape_percent=(
            fsum(abs(error) for error in errors) / absolute_actual_sum * 100
            if absolute_actual_sum > _ZERO_TOLERANCE
            else None
        ),
    )


def calculate_forecast_accuracy(day: ArchivedDay) -> ForecastAccuracy:
    """Compare forecasts with measurements sharing the exact target timestamp.

    SMA measurements are sampled every five minutes while predictions use
    quarter-hour target timestamps. Exact matching preserves the provider's
    timestamp semantics without interpolation. Predictions later than the most
    recent measurement are not yet eligible and therefore do not reduce the
    reported coverage.
    """
    measurements_by_time = {item.time_utc: item for item in day.measurements}
    latest_measurement = max(measurements_by_time, default=None)
    eligible_predictions = tuple(
        item
        for item in day.predictions
        if latest_measurement is not None and item.time_utc <= latest_measurement
    )
    matched = tuple(
        (measurement, prediction)
        for prediction in eligible_predictions
        if (measurement := measurements_by_time.get(prediction.time_utc)) is not None
    )

    eligible_count = len(eligible_predictions)
    matched_count = len(matched)
    matched_times = tuple(prediction.time_utc for _measurement, prediction in matched)

    return ForecastAccuracy(
        interval_seconds=ACCURACY_INTERVAL_SECONDS,
        measurement_points=len(day.measurements),
        forecast_points=len(day.predictions),
        eligible_points=eligible_count,
        matched_points=matched_count,
        coverage_percent=(
            matched_count / eligible_count * 100 if eligible_count else None
        ),
        first_matched_utc=min(matched_times, default=None),
        last_matched_utc=max(matched_times, default=None),
        pv_generation=_series_accuracy(
            tuple(
                (measurement.pv_generation_w, prediction.pv_generation_w)
                for measurement, prediction in matched
            )
        ),
        total_consumption=_series_accuracy(
            tuple(
                (
                    measurement.total_consumption_w,
                    prediction.total_consumption_w,
                )
                for measurement, prediction in matched
            )
        ),
    )
