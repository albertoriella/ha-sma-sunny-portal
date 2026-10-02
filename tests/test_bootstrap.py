"""Tests for manual-bootstrap credential validation."""

from __future__ import annotations

import asyncio
import base64
import json
from collections.abc import Mapping
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from custom_components.sma_sunny_portal.bootstrap import async_validate_credentials
from custom_components.sma_sunny_portal.const import OAUTH_ISSUER
from custom_components.sma_sunny_portal.errors import (
    SmaSunnyPortalDataError,
    SmaSunnyPortalResponseError,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "consumer_balance_day.json"


def _load_fixture() -> Mapping[str, Any]:
    """Load the synthetic Sunny Portal response."""
    with FIXTURE_PATH.open(encoding="utf-8") as fixture_file:
        payload = json.load(fixture_file)
    assert isinstance(payload, Mapping)
    return payload


def _encode_segment(value: object) -> str:
    """Encode one unsigned synthetic JWT segment."""
    encoded = base64.urlsafe_b64encode(
        json.dumps(value, separators=(",", ":")).encode()
    ).decode()
    return encoded.rstrip("=")


def _access_token(*, issuer: str = OAUTH_ISSUER) -> str:
    """Return a synthetic unsigned token containing only safe claims."""
    return ".".join(
        (
            _encode_segment({"alg": "none", "typ": "JWT"}),
            _encode_segment(
                {
                    "iss": issuer,
                    "sub": "synthetic-account-subject",
                }
            ),
            "synthetic-signature",
        )
    )


def _token_response(*, access_token: str | None = None) -> dict[str, Any]:
    """Build a complete synthetic refresh response."""
    return {
        "access_token": access_token or _access_token(),
        "expires_in": 300,
        "refresh_expires_in": 172800,
        "refresh_token": "synthetic-refresh-rotated",
        "token_type": "Bearer",
        "scope": "openid profile",
    }


class FakeResponse:
    """Asynchronous HTTP response used for both token and data calls."""

    def __init__(self, status: int, payload: object) -> None:
        """Initialize response data."""
        self.status = status
        self.payload = payload

    async def __aenter__(self) -> FakeResponse:
        """Enter the response context."""
        return self

    async def __aexit__(self, *args: object) -> None:
        """Exit the response context."""

    async def json(self, *, content_type: None = None) -> object:
        """Return the configured JSON value."""
        del content_type
        return self.payload


class FakeSession:
    """Serve one refresh response and one portal response."""

    def __init__(
        self,
        token_response: FakeResponse,
        api_response: FakeResponse,
    ) -> None:
        """Initialize responses and request history."""
        self.token_response = token_response
        self.api_response = api_response
        self.posts: list[dict[str, Any]] = []
        self.gets: list[dict[str, Any]] = []

    def post(self, url: str, **kwargs: Any) -> FakeResponse:
        """Record token rotation."""
        self.posts.append({"url": url, **kwargs})
        return self.token_response

    def get(self, url: str, **kwargs: Any) -> FakeResponse:
        """Record portal validation."""
        self.gets.append({"url": url, **kwargs})
        return self.api_response


def test_bootstrap_rotates_token_and_validates_plant() -> None:
    """A successful bootstrap returns identity, newest token, and parsed data."""
    session = FakeSession(
        FakeResponse(200, _token_response()),
        FakeResponse(200, _load_fixture()),
    )
    observed: list[str] = []

    async def observe(token: str) -> None:
        observed.append(token)

    result = asyncio.run(
        async_validate_credentials(
            session,  # type: ignore[arg-type]
            "90000000",
            "synthetic-refresh-bootstrap",
            date(2099, 6, 15),
            async_observe_rotated_token=observe,
        )
    )

    assert result.account_id == "synthetic-account-subject"
    assert result.refresh_token == "synthetic-refresh-rotated"
    assert len(result.consumer_balance.predictions) == 5
    assert observed == ["synthetic-refresh-rotated"]
    assert len(session.posts) == 1
    assert len(session.gets) == 1
    assert session.gets[0]["headers"]["Authorization"].startswith("Bearer ")


def test_bootstrap_rejects_unexpected_identity_without_leaking_token() -> None:
    """Only identity claims issued by the observed SMA realm are accepted."""
    private_access_token = _access_token(issuer="https://synthetic.invalid")
    session = FakeSession(
        FakeResponse(200, _token_response(access_token=private_access_token)),
        FakeResponse(200, _load_fixture()),
    )

    with pytest.raises(SmaSunnyPortalDataError) as raised:
        asyncio.run(
            async_validate_credentials(
                session,  # type: ignore[arg-type]
                "90000000",
                "synthetic-refresh-bootstrap",
                date(2099, 6, 15),
            )
        )

    assert private_access_token not in str(raised.value)
    assert session.gets == []


def test_bootstrap_observes_rotation_before_portal_failure() -> None:
    """A retry can continue with the newest token after a data API failure."""
    session = FakeSession(
        FakeResponse(200, _token_response()),
        FakeResponse(503, {}),
    )
    observed: list[str] = []

    async def observe(token: str) -> None:
        observed.append(token)

    with pytest.raises(SmaSunnyPortalResponseError):
        asyncio.run(
            async_validate_credentials(
                session,  # type: ignore[arg-type]
                "90000000",
                "synthetic-refresh-bootstrap",
                date(2099, 6, 15),
                async_observe_rotated_token=observe,
            )
        )

    assert observed == ["synthetic-refresh-rotated"]
