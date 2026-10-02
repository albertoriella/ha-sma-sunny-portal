"""Tests for safe rotating-token management."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from typing import Any

import pytest

from custom_components.sma_sunny_portal.auth import SmaSunnyPortalTokenManager
from custom_components.sma_sunny_portal.const import TOKEN_ENDPOINT
from custom_components.sma_sunny_portal.errors import (
    SmaSunnyPortalAuthenticationError,
    SmaSunnyPortalDataError,
    SmaSunnyPortalRateLimitError,
    SmaSunnyPortalTokenPersistenceError,
)


def _token_response(
    suffix: str,
    *,
    expires_in: int = 300,
    refresh_expires_in: int = 172800,
) -> dict[str, Any]:
    """Build an entirely synthetic Keycloak token response."""
    return {
        "access_token": f"synthetic-access-{suffix}",
        "expires_in": expires_in,
        "refresh_expires_in": refresh_expires_in,
        "refresh_token": f"synthetic-refresh-{suffix}",
        "token_type": "Bearer",
        "scope": "openid profile",
    }


class FakeResponse:
    """Asynchronous response context manager for token tests."""

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
        """Return or raise the configured response."""
        del content_type
        await asyncio.sleep(0)
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class FakeSession:
    """Return queued token responses and record all requests."""

    def __init__(self, *responses: FakeResponse | Exception) -> None:
        """Initialize a fake session."""
        self._responses = list(responses)
        self.requests: list[dict[str, Any]] = []

    def post(self, url: str, **kwargs: Any) -> FakeResponse:
        """Record one POST and return its queued result."""
        self.requests.append({"url": url, **kwargs})
        result = self._responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


class FakeClock:
    """Controllable monotonic clock."""

    def __init__(self, value: float = 100.0) -> None:
        """Initialize the clock."""
        self.value = value

    def __call__(self) -> float:
        """Return the current monotonic value."""
        return self.value

    def advance(self, seconds: float) -> None:
        """Advance the clock."""
        self.value += seconds


class TokenSaver:
    """Record tokens and optionally simulate transient persistence failures."""

    def __init__(self, failures: int = 0) -> None:
        """Initialize the saver."""
        self.failures = failures
        self.saved: list[str] = []

    async def __call__(self, refresh_token: str) -> None:
        """Persist a token or raise a synthetic failure."""
        await asyncio.sleep(0)
        if self.failures:
            self.failures -= 1
            raise RuntimeError("synthetic persistence failure")
        self.saved.append(refresh_token)


def _manager(
    session: FakeSession,
    saver: TokenSaver,
    *,
    clock: FakeClock | None = None,
    expiry_margin_seconds: float = 30.0,
) -> SmaSunnyPortalTokenManager:
    """Create a manager with synthetic inputs."""
    return SmaSunnyPortalTokenManager(
        session,  # type: ignore[arg-type]
        "synthetic-refresh-initial",
        saver,
        clock=clock or FakeClock(),
        expiry_margin_seconds=expiry_margin_seconds,
    )


def test_refresh_rotates_and_persists_before_returning_access() -> None:
    """A complete response rotates state and uses the minimal form request."""
    session = FakeSession(FakeResponse(200, _token_response("rotated")))
    saver = TokenSaver()
    manager = _manager(session, saver)

    access_token = asyncio.run(manager.async_get_access_token())

    assert access_token == "synthetic-access-rotated"
    assert saver.saved == ["synthetic-refresh-rotated"]
    assert manager.refresh_expires_in_seconds == 172800
    assert not manager.has_pending_refresh_token_persistence
    assert len(session.requests) == 1
    request = session.requests[0]
    assert request["url"] == TOKEN_ENDPOINT
    assert request["data"] == {
        "grant_type": "refresh_token",
        "scope": "openid profile",
        "refresh_token": "synthetic-refresh-initial",
        "client_id": "SPpbeOS",
    }
    assert request["headers"] == {
        "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    assert "Authorization" not in request["headers"]


def test_concurrent_callers_consume_only_one_rotation() -> None:
    """An account-wide lock prevents refresh-token reuse races."""
    session = FakeSession(FakeResponse(200, _token_response("one")))
    saver = TokenSaver()
    manager = _manager(session, saver)

    async def scenario() -> list[str]:
        return await asyncio.gather(
            *(manager.async_get_access_token() for _ in range(12))
        )

    results = asyncio.run(scenario())

    assert results == ["synthetic-access-one"] * 12
    assert len(session.requests) == 1
    assert saver.saved == ["synthetic-refresh-one"]


def test_cached_access_token_respects_expiry_margin() -> None:
    """A cached access token is reused only inside its safe lifetime."""
    session = FakeSession(
        FakeResponse(200, _token_response("one")),
        FakeResponse(200, _token_response("two")),
    )
    saver = TokenSaver()
    clock = FakeClock()
    manager = _manager(session, saver, clock=clock)

    async def scenario() -> tuple[str, str, str]:
        first = await manager.async_get_access_token()
        clock.advance(269)
        cached = await manager.async_get_access_token()
        clock.advance(2)
        refreshed = await manager.async_get_access_token()
        return first, cached, refreshed

    first, cached, refreshed = asyncio.run(scenario())

    assert first == cached == "synthetic-access-one"
    assert refreshed == "synthetic-access-two"
    assert len(session.requests) == 2
    assert saver.saved == ["synthetic-refresh-one", "synthetic-refresh-two"]


def test_persistence_failure_retries_without_another_rotation() -> None:
    """The newest token remains in memory until persistence succeeds."""
    session = FakeSession(FakeResponse(200, _token_response("recoverable")))
    saver = TokenSaver(failures=1)
    manager = _manager(session, saver)

    async def scenario() -> str:
        with pytest.raises(SmaSunnyPortalTokenPersistenceError) as raised:
            await manager.async_get_access_token()
        assert raised.value.__cause__ is None
        assert manager.has_pending_refresh_token_persistence
        assert len(session.requests) == 1
        return await manager.async_get_access_token()

    access_token = asyncio.run(scenario())

    assert access_token == "synthetic-access-recoverable"
    assert saver.saved == ["synthetic-refresh-recoverable"]
    assert len(session.requests) == 1
    assert not manager.has_pending_refresh_token_persistence


def test_expired_access_token_can_be_invalidated_early() -> None:
    """A portal 401 can force rotation before the local expiry time."""
    session = FakeSession(
        FakeResponse(200, _token_response("one")),
        FakeResponse(200, _token_response("two")),
    )
    saver = TokenSaver()
    manager = _manager(session, saver)

    async def scenario() -> str:
        await manager.async_get_access_token()
        manager.invalidate_access_token()
        return await manager.async_get_access_token()

    result = asyncio.run(scenario())

    assert result == "synthetic-access-two"
    assert len(session.requests) == 2


def test_invalid_grant_is_terminal_and_does_not_leak_token() -> None:
    """A rejected refresh token becomes a terminal authentication error."""
    session = FakeSession(FakeResponse(400, {"error": "invalid_grant"}))
    saver = TokenSaver()
    manager = _manager(session, saver)

    with pytest.raises(SmaSunnyPortalAuthenticationError) as raised:
        asyncio.run(manager.async_get_access_token())

    assert "synthetic-refresh-initial" not in str(raised.value)
    assert saver.saved == []


def test_rate_limit_has_distinct_error() -> None:
    """The coordinator can distinguish throttling from expired credentials."""
    session = FakeSession(FakeResponse(429, {}))
    manager = _manager(session, TokenSaver())

    with pytest.raises(SmaSunnyPortalRateLimitError):
        asyncio.run(manager.async_get_access_token())


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {**_token_response("missing"), "refresh_token": None},
        {**_token_response("wrong-type"), "token_type": "MAC"},
        {**_token_response("short"), "expires_in": 30},
    ],
)
def test_incomplete_token_response_never_advances_persisted_state(
    payload: Mapping[str, Any],
) -> None:
    """Every security-critical response field is validated before persistence."""
    session = FakeSession(FakeResponse(200, payload))
    saver = TokenSaver()
    manager = _manager(session, saver)

    with pytest.raises(SmaSunnyPortalDataError):
        asyncio.run(manager.async_get_access_token())

    assert saver.saved == []


def test_non_json_token_response_is_rejected_without_content() -> None:
    """Token endpoint response content is never copied into diagnostics."""
    invalid_json = json.JSONDecodeError("synthetic private content", "", 0)
    session = FakeSession(FakeResponse(200, invalid_json))
    manager = _manager(session, TokenSaver())

    with pytest.raises(SmaSunnyPortalDataError) as raised:
        asyncio.run(manager.async_get_access_token())

    assert "synthetic private content" not in str(raised.value)
    assert raised.value.__cause__ is None
