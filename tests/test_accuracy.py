"""Tests for provider-neutral forecast-accuracy metrics."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from custom_components.sma_sunny_portal.accuracy import (
    ACCURACY_INTERVAL_SECONDS,
    calculate_forecast_accuracy,
)
from custom_components.sma_sunny_portal.history import (
    ArchivedDay,
    ArchivedMeasurement,
    ArchivedPrediction,
)


def _day(
    measurements: tuple[ArchivedMeasurement, ...],
    predictions: tuple[ArchivedPrediction, ...],
) -> ArchivedDay:
    """Build an archive response without availability metadata."""
    return ArchivedDay(measurements, predictions, None, None)


def test_accuracy_calculates_power_energy_and_coverage() -> None:
    """Matched points produce signed bias and zero-safe aggregate errors."""
    start = datetime(2099, 6, 15, 10, tzinfo=UTC)
    issued = start - timedelta(hours=12)
    measurements = (
        ArchivedMeasurement(start, 100, 60),
        ArchivedMeasurement(start + timedelta(minutes=15), 140, 90),
        ArchivedMeasurement(start + timedelta(minutes=30), 160, 100),
    )
    predictions = (
        ArchivedPrediction(start, issued, 120, 70),
        ArchivedPrediction(start + timedelta(minutes=15), issued, 180, 110),
        ArchivedPrediction(start + timedelta(minutes=30), issued, 170, 105),
        ArchivedPrediction(start + timedelta(minutes=45), issued, 200, 120),
    )

    result = calculate_forecast_accuracy(_day(measurements, predictions))

    assert result.interval_seconds == ACCURACY_INTERVAL_SECONDS
    assert result.measurement_points == 3
    assert result.forecast_points == 4
    assert result.eligible_points == 3
    assert result.matched_points == 3
    assert result.coverage_percent == 100
    assert result.first_matched_utc == start
    assert result.last_matched_utc == start + timedelta(minutes=30)

    assert result.pv_generation is not None
    assert result.pv_generation.actual_energy_wh == 100
    assert result.pv_generation.forecast_energy_wh == 117.5
    assert result.pv_generation.energy_error_wh == 17.5
    assert result.pv_generation.energy_error_percent == 17.5
    assert result.pv_generation.mae_w == pytest.approx(70 / 3)
    assert result.pv_generation.rmse_w == pytest.approx((2100 / 3) ** 0.5)
    assert result.pv_generation.bias_w == pytest.approx(70 / 3)
    assert result.pv_generation.wape_percent == 17.5

    assert result.total_consumption is not None
    assert result.total_consumption.actual_energy_wh == 62.5
    assert result.total_consumption.forecast_energy_wh == 71.25
    assert result.total_consumption.energy_error_wh == 8.75
    assert result.total_consumption.energy_error_percent == pytest.approx(14)
    assert result.total_consumption.mae_w == pytest.approx(35 / 3)
    assert result.total_consumption.rmse_w == pytest.approx((525 / 3) ** 0.5)
    assert result.total_consumption.bias_w == pytest.approx(35 / 3)
    assert result.total_consumption.wape_percent == pytest.approx(14)


def test_accuracy_reports_missing_timestamp_as_coverage_gap() -> None:
    """An eligible prediction without an exact measured point is not invented."""
    start = datetime(2099, 6, 15, 10, tzinfo=UTC)
    issued = start - timedelta(hours=1)
    result = calculate_forecast_accuracy(
        _day(
            (
                ArchivedMeasurement(start, 100, 60),
                ArchivedMeasurement(start + timedelta(minutes=30), 150, 80),
            ),
            (
                ArchivedPrediction(start, issued, 110, 65),
                ArchivedPrediction(start + timedelta(minutes=15), issued, 130, 70),
                ArchivedPrediction(start + timedelta(minutes=30), issued, 160, 85),
            ),
        )
    )

    assert result.eligible_points == 3
    assert result.matched_points == 2
    assert result.coverage_percent == pytest.approx(200 / 3)


def test_accuracy_does_not_count_future_forecasts_as_missing() -> None:
    """A current-day future curve has no eligible points or false failures."""
    now = datetime(2099, 6, 15, 10, tzinfo=UTC)
    result = calculate_forecast_accuracy(
        _day(
            (ArchivedMeasurement(now, 100, 60),),
            (
                ArchivedPrediction(
                    now + timedelta(minutes=15),
                    now,
                    120,
                    70,
                ),
            ),
        )
    )

    assert result.eligible_points == 0
    assert result.matched_points == 0
    assert result.coverage_percent is None
    assert result.first_matched_utc is None
    assert result.last_matched_utc is None
    assert result.pv_generation is None
    assert result.total_consumption is None


def test_accuracy_avoids_percentage_division_by_zero() -> None:
    """Night-time PV retains absolute metrics without meaningless percentages."""
    target = datetime(2099, 6, 15, 1, tzinfo=UTC)
    result = calculate_forecast_accuracy(
        _day(
            (ArchivedMeasurement(target, 0, 100),),
            (ArchivedPrediction(target, target - timedelta(hours=1), 50, 100),),
        )
    )

    assert result.pv_generation is not None
    assert result.pv_generation.actual_energy_wh == 0
    assert result.pv_generation.forecast_energy_wh == 12.5
    assert result.pv_generation.energy_error_percent is None
    assert result.pv_generation.wape_percent is None
    assert result.pv_generation.mae_w == 50
