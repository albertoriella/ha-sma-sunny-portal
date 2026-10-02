"""Contract and privacy tests for the synthetic Sunny Portal fixture."""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "consumer_balance_day.json"

REQUIRED_TOP_LEVEL_KEYS = {
    "_links",
    "consumerLegend",
    "predictionValues",
    "recommendations",
    "total",
    "values",
    "weatherForecast",
}

FORBIDDEN_SECRET_KEYS = {
    "access_token",
    "authorization",
    "cookie",
    "email",
    "id_token",
    "preferred_username",
    "refresh_token",
    "session_state",
    "uid",
}


def _load_fixture() -> dict[str, Any]:
    """Load the synthetic consumer balance response."""
    with FIXTURE_PATH.open(encoding="utf-8") as fixture_file:
        return json.load(fixture_file)


def _parse_utc(value: str) -> datetime:
    """Parse an ISO 8601 UTC timestamp and require timezone awareness."""
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    assert parsed.tzinfo is UTC
    return parsed


def _assert_cadence(series: list[dict[str, Any]], cadence: timedelta) -> None:
    """Assert that a timeUtc series is ordered at a fixed cadence."""
    timestamps = [_parse_utc(item["timeUtc"]) for item in series]
    assert timestamps == sorted(timestamps)
    assert all(
        current - previous == cadence
        for previous, current in zip(timestamps, timestamps[1:], strict=False)
    )


def _walk_keys(value: Any) -> set[str]:
    """Return every dictionary key found recursively in a JSON value."""
    if isinstance(value, dict):
        return set(value) | {
            nested_key
            for nested_value in value.values()
            for nested_key in _walk_keys(nested_value)
        }
    if isinstance(value, list):
        return {
            nested_key
            for nested_value in value
            for nested_key in _walk_keys(nested_value)
        }
    return set()


def test_fixture_has_observed_response_shape() -> None:
    """The fixture preserves the endpoint sections needed by the parser."""
    payload = _load_fixture()

    assert set(payload) == REQUIRED_TOP_LEVEL_KEYS
    assert payload["values"]
    assert payload["consumerLegend"]
    assert payload["predictionValues"]
    assert payload["weatherForecast"]
    assert payload["recommendations"]
    assert payload["total"]["consumers"]

    assert {
        "baseload",
        "batteryCharging",
        "batteryDischarging",
        "consumers",
        "externalConsumption",
        "otherGeneration",
        "pvGeneration",
        "timeUtc",
        "totalConsumption",
        "totalGeneration",
    } <= set(payload["values"][0])

    assert {"pvGeneration", "timeUtc", "totalConsumption"} <= set(
        payload["predictionValues"][0]
    )


def test_fixture_preserves_observed_cadences() -> None:
    """Measured, forecast, and weather data use their observed intervals."""
    payload = _load_fixture()

    _assert_cadence(payload["values"], timedelta(minutes=5))
    _assert_cadence(payload["predictionValues"], timedelta(minutes=15))
    _assert_cadence(payload["weatherForecast"], timedelta(hours=1))


def test_recommendations_are_numerically_consistent() -> None:
    """Each recommendation difference is generation minus consumption."""
    payload = _load_fixture()

    for recommendation in payload["recommendations"]:
        start = _parse_utc(recommendation["timeUtcStart"])
        end = _parse_utc(recommendation["timeUtcEnd"])
        assert end - start == timedelta(hours=1)
        assert recommendation["excessEnergy"] in {"High", "Low", "Mid"}
        assert math.isclose(
            recommendation["difference"],
            recommendation["totalPvGeneration"] - recommendation["totalConsumption"],
        )


def test_fixture_contains_no_credentials_or_personal_fields() -> None:
    """The public fixture must remain free of credential and identity fields."""
    payload = _load_fixture()

    assert not (_walk_keys(payload) & FORBIDDEN_SECRET_KEYS)
    assert all(
        legend["name"].startswith("Synthetic ") for legend in payload["consumerLegend"]
    )
