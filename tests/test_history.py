"""Tests for the bounded private forecast-history archive."""

from __future__ import annotations

import asyncio
import sqlite3
import stat
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from custom_components.sma_sunny_portal.errors import SmaSunnyPortalHistoryError
from custom_components.sma_sunny_portal.history import SmaSunnyPortalHistoryStore
from custom_components.sma_sunny_portal.models import (
    ConsumerBalance,
    Measurement,
    Prediction,
)


class FakeConfig:
    """Resolve Home Assistant storage paths below one temporary directory."""

    def __init__(self, root: Path) -> None:
        """Store the test root."""
        self._root = root

    def path(self, *parts: str) -> str:
        """Return a path using Home Assistant's config-path convention."""
        return str(self._root.joinpath(*parts))


class FakeHass:
    """Run executor jobs inline for deterministic archive tests."""

    def __init__(self, root: Path) -> None:
        """Initialize the path resolver."""
        self.config = FakeConfig(root)

    async def async_add_executor_job(
        self,
        target: Any,
        *args: object,
    ) -> Any:
        """Execute a synchronous storage operation."""
        return target(*args)


def _measurement(time_utc: datetime, pv_w: float, consumption_w: float) -> Measurement:
    """Build one compact synthetic measurement."""
    return Measurement(
        time_utc=time_utc,
        total_generation_w=pv_w,
        pv_generation_w=pv_w,
        other_generation_w=None,
        external_consumption_w=consumption_w,
        total_consumption_w=consumption_w,
        battery_charging_w=0,
        battery_discharging_w=0,
        baseload_w=consumption_w,
        consumers=(),
    )


def _balance(
    base: datetime,
    *,
    measurement_pv_w: float = 500,
) -> ConsumerBalance:
    """Build measurements and a two-point forecast without personal data."""
    return ConsumerBalance(
        measurements=(_measurement(base, measurement_pv_w, 700),),
        predictions=(
            Prediction(base + timedelta(minutes=15), 800, 650),
            Prediction(base + timedelta(minutes=30), 900, 675),
        ),
        weather_forecasts=(),
        recommendations=(),
        consumers=(),
    )


def _counts(path: Path) -> tuple[int, int, int]:
    """Return snapshot, forecast-point, and measurement row counts."""
    with sqlite3.connect(path) as connection:
        return (
            connection.execute("SELECT COUNT(*) FROM forecast_snapshots").fetchone()[0],
            connection.execute("SELECT COUNT(*) FROM forecast_points").fetchone()[0],
            connection.execute("SELECT COUNT(*) FROM measurements").fetchone()[0],
        )


def test_archive_is_private_and_throttles_forecast_vintages(tmp_path: Path) -> None:
    """Measurements update every cycle while full curves are stored hourly."""
    issued_times = iter(
        (
            datetime(2099, 6, 15, 8, 0, tzinfo=UTC),
            datetime(2099, 6, 15, 8, 15, tzinfo=UTC),
            datetime(2099, 6, 15, 9, 0, tzinfo=UTC),
        )
    )
    store = SmaSunnyPortalHistoryStore(
        FakeHass(tmp_path),
        "synthetic-entry",
        "90000000",
        now_provider=lambda: next(issued_times),
    )
    base = datetime(2099, 6, 15, 7, 55, tzinfo=UTC)

    asyncio.run(store.async_record(_balance(base)))
    assert _counts(store.path) == (1, 2, 1)
    assert stat.S_IMODE(store.path.stat().st_mode) == 0o600

    asyncio.run(store.async_record(_balance(base, measurement_pv_w=525)))
    assert _counts(store.path) == (1, 2, 1)

    asyncio.run(store.async_record(_balance(base + timedelta(hours=1))))
    assert _counts(store.path) == (2, 4, 2)

    with sqlite3.connect(store.path) as connection:
        actual_pv = connection.execute(
            """
            SELECT pv_generation_w
            FROM measurements
            WHERE valid_at_utc = ?
            """,
            (int(base.timestamp()),),
        ).fetchone()[0]
        assert actual_pv == 525
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1


def test_archive_prunes_old_vintages_and_measurements(tmp_path: Path) -> None:
    """Raw history remains useful but cannot grow without a bound."""
    current_time = datetime(2099, 1, 1, tzinfo=UTC)
    store = SmaSunnyPortalHistoryStore(
        FakeHass(tmp_path),
        "synthetic-entry",
        "90000000",
        now_provider=lambda: current_time,
    )
    asyncio.run(store.async_record(_balance(current_time)))

    current_time += timedelta(days=401)
    asyncio.run(store.async_record(_balance(current_time)))

    assert _counts(store.path) == (1, 2, 1)


def test_archive_remove_deletes_database(tmp_path: Path) -> None:
    """Removing a config entry removes its private telemetry archive."""
    now = datetime(2099, 6, 15, 8, tzinfo=UTC)
    store = SmaSunnyPortalHistoryStore(
        FakeHass(tmp_path),
        "synthetic-entry",
        "90000000",
        now_provider=lambda: now,
    )
    asyncio.run(store.async_record(_balance(now)))
    assert store.path.exists()

    asyncio.run(store.async_remove())

    assert not store.path.exists()


def test_archive_redacts_storage_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Filesystem details and telemetry never escape through archive errors."""
    store = SmaSunnyPortalHistoryStore(
        FakeHass(tmp_path),
        "synthetic-entry",
        "90000000",
        now_provider=lambda: datetime(2099, 6, 15, 8, tzinfo=UTC),
    )
    monkeypatch.setattr(
        store,
        "_prepare_private_file",
        lambda: (_ for _ in ()).throw(OSError("secret filesystem detail")),
    )

    with pytest.raises(SmaSunnyPortalHistoryError) as raised:
        asyncio.run(store.async_record(_balance(datetime(2099, 6, 15, 8, tzinfo=UTC))))

    assert "secret filesystem detail" not in str(raised.value)
    assert raised.value.__cause__ is None
