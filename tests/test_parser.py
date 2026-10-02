"""Tests for normalized Sunny Portal response parsing."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from custom_components.sma_sunny_portal.errors import SmaSunnyPortalDataError
from custom_components.sma_sunny_portal.parser import parse_consumer_balance

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "consumer_balance_day.json"


def _load_fixture() -> dict[str, Any]:
    """Load a mutable copy of the synthetic API response."""
    with FIXTURE_PATH.open(encoding="utf-8") as fixture_file:
        return json.load(fixture_file)


def test_parser_normalizes_complete_response() -> None:
    """The observed response sections become immutable domain models."""
    result = parse_consumer_balance(_load_fixture())

    assert len(result.measurements) == 4
    assert len(result.predictions) == 5
    assert len(result.weather_forecasts) == 2
    assert len(result.recommendations) == 2
    assert len(result.consumers) == 1

    assert result.measurements[0].time_utc == datetime(2099, 6, 15, 7, 0, tzinfo=UTC)
    assert result.measurements[1].consumers[0].consumption_w == 120
    assert result.predictions[0].surplus_w == 300
    assert result.recommendations[1].difference_wh == 750
    assert result.consumers[0].name == "Synthetic EV Charger"


def test_parser_sorts_time_series() -> None:
    """Endpoint ordering does not leak into coordinator behavior."""
    payload = _load_fixture()
    payload["predictionValues"].reverse()

    result = parse_consumer_balance(payload)

    assert list(result.predictions) == sorted(
        result.predictions, key=lambda prediction: prediction.time_utc
    )


def test_parser_accepts_temporarily_empty_forecast_sections() -> None:
    """A portal ingestion delay is valid data rather than malformed data."""
    payload = _load_fixture()
    payload["predictionValues"] = []
    payload["weatherForecast"] = []
    payload["recommendations"] = []

    result = parse_consumer_balance(payload)

    assert result.predictions == ()
    assert result.weather_forecasts == ()
    assert result.recommendations == ()


def test_parser_rejects_non_utc_timestamp_without_echoing_value() -> None:
    """Malformed values identify only their safe JSON path."""
    payload = deepcopy(_load_fixture())
    private_value = "2099-06-15T09:30:00+02:00"
    payload["predictionValues"][0]["timeUtc"] = private_value

    with pytest.raises(SmaSunnyPortalDataError) as raised:
        parse_consumer_balance(payload)

    assert "predictionValues[0].timeUtc" in str(raised.value)
    assert private_value not in str(raised.value)
    assert raised.value.__cause__ is None


def test_parser_rejects_non_finite_number() -> None:
    """NaN and infinity cannot become Home Assistant sensor states."""
    payload = _load_fixture()
    payload["predictionValues"][0]["pvGeneration"] = float("nan")

    with pytest.raises(SmaSunnyPortalDataError, match="finite number"):
        parse_consumer_balance(payload)
