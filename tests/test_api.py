"""Tests for the asynchronous Sunny Portal API client."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from datetime import date
from pathlib import Path
from typing import Any

import aiohttp
import pytest

from custom_components.sma_sunny_portal.api import SmaSunnyPortalApiClient
from custom_components.sma_sunny_portal.errors import (
    SmaSunnyPortalAuthenticationError,
    SmaSunnyPortalConnectionError,
    SmaSunnyPortalDataError,
    SmaSunnyPortalRateLimitError,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "consumer_balance_day.json"


class FakeResponse:
    """Small asynchronous response context manager for network-free tests."""

    def __init__(self, status: int, payload: object) -> None:
        """Initialize a fake response."""
        self.status = status
        self._payload = payload

    async def __aenter__(self) -> FakeResponse:
        """Enter the response context."""
        return self

    async def __aexit__(self, *args: object) -> None:
        """Exit the response context."""

    async def json(self, *, content_type: None = None) -> object:
        """Return or raise the configured payload."""
        del content_type
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class FakeSession:
    """Record one request and return a preconfigured response."""

    def __init__(
        self,
        response: FakeResponse | None = None,
        request_error: Exception | None = None,
    ) -> None:
        """Initialize a fake session."""
        self._response = response
        self._request_error = request_error
        self.request: dict[str, Any] | None = None

    def get(self, url: str, **kwargs: Any) -> FakeResponse:
        """Record the request and return the fake response."""
        self.request = {"url": url, **kwargs}
        if self._request_error is not None:
            raise self._request_error
        assert self._response is not None
        return self._response


def _load_fixture() -> Mapping[str, Any]:
    """Load the synthetic API response."""
    with FIXTURE_PATH.open(encoding="utf-8") as fixture_file:
        payload = json.load(fixture_file)
    assert isinstance(payload, Mapping)
    return payload


async def _access_token() -> str:
    """Return an obviously synthetic access token."""
    return "synthetic-access-token"


def test_client_builds_minimal_request_and_parses_response() -> None:
    """The client sends only required headers and returns normalized data."""
    session = FakeSession(FakeResponse(200, _load_fixture()))
    client = SmaSunnyPortalApiClient(session, _access_token)  # type: ignore[arg-type]

    result = asyncio.run(
        client.async_get_consumer_balance("90000000", date(2099, 6, 15))
    )

    assert len(result.measurements) == 4
    assert len(result.predictions) == 5
    assert result.predictions[0].surplus_w == 300
    assert session.request is not None
    assert session.request["url"].endswith(
        "/measurements/90000000/consumerbalance/consumption"
    )
    assert session.request["params"] == {
        "dateBeginLocal": "2099-06-15",
        "interval": "Day",
        "loadTimeframes": "false",
    }
    assert session.request["headers"] == {
        "Accept": "application/json",
        "Authorization": "Bearer synthetic-access-token",
    }
    assert session.request["timeout"].total == 30.0


@pytest.mark.parametrize("status", [401, 403])
def test_client_classifies_authentication_failures_without_leaking_token(
    status: int,
) -> None:
    """Authentication failures are terminal and never expose credentials."""
    session = FakeSession(FakeResponse(status, {}))
    client = SmaSunnyPortalApiClient(session, _access_token)  # type: ignore[arg-type]

    with pytest.raises(SmaSunnyPortalAuthenticationError) as raised:
        asyncio.run(client.async_get_consumer_balance("90000000", date(2099, 6, 15)))

    assert "synthetic-access-token" not in str(raised.value)
    assert str(status) in str(raised.value)


def test_client_classifies_rate_limit() -> None:
    """HTTP 429 has a distinct retryable error type."""
    session = FakeSession(FakeResponse(429, {}))
    client = SmaSunnyPortalApiClient(session, _access_token)  # type: ignore[arg-type]

    with pytest.raises(SmaSunnyPortalRateLimitError):
        asyncio.run(client.async_get_consumer_balance("90000000", date(2099, 6, 15)))


def test_client_classifies_connection_failure() -> None:
    """aiohttp failures become integration-specific connection errors."""
    session = FakeSession(request_error=aiohttp.ClientConnectionError("synthetic"))
    client = SmaSunnyPortalApiClient(session, _access_token)  # type: ignore[arg-type]

    with pytest.raises(SmaSunnyPortalConnectionError):
        asyncio.run(client.async_get_consumer_balance("90000000", date(2099, 6, 15)))


def test_client_rejects_non_json_response() -> None:
    """Invalid JSON becomes a data error without including response content."""
    invalid_json = json.JSONDecodeError("synthetic", "", 0)
    session = FakeSession(FakeResponse(200, invalid_json))
    client = SmaSunnyPortalApiClient(session, _access_token)  # type: ignore[arg-type]

    with pytest.raises(SmaSunnyPortalDataError, match="non-JSON") as raised:
        asyncio.run(client.async_get_consumer_balance("90000000", date(2099, 6, 15)))

    assert raised.value.__cause__ is None
