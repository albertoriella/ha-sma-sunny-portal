"""Bounded private history for SMA forecasts and measured power."""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from .const import (
    FORECAST_ARCHIVE_INTERVAL_SECONDS,
    FORECAST_ARCHIVE_RETENTION_SECONDS,
    HISTORY_DATABASE_PREFIX,
    HISTORY_DATABASE_SCHEMA_VERSION,
    MEASUREMENT_ARCHIVE_RETENTION_SECONDS,
)
from .errors import SmaSunnyPortalHistoryError
from .models import ConsumerBalance

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

type UtcNowProvider = Callable[[], datetime]


def _utcnow() -> datetime:
    """Return the current aware UTC time."""
    return datetime.now(UTC)


def _utc_epoch(value: datetime) -> int:
    """Convert one aware datetime to a whole-second UTC epoch."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("history timestamps must be timezone-aware")
    return int(value.timestamp())


class SmaSunnyPortalHistoryStore:
    """Persist forecast vintages without duplicating curves in Recorder."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        plant_id: str,
        *,
        now_provider: UtcNowProvider = _utcnow,
    ) -> None:
        """Initialize one config-entry-scoped private SQLite archive."""
        self._hass = hass
        self._plant_id = plant_id
        self._now_provider = now_provider
        self._path = Path(
            hass.config.path(
                ".storage",
                f"{HISTORY_DATABASE_PREFIX}.{entry_id}.sqlite3",
            )
        )

    @property
    def path(self) -> Path:
        """Return the private database path for diagnostics and tests."""
        return self._path

    async def async_record(self, balance: ConsumerBalance) -> None:
        """Archive new measurements and, at most hourly, one forecast vintage."""
        issued_at = self._now_provider()
        try:
            await self._hass.async_add_executor_job(
                self._record,
                balance,
                issued_at,
            )
        except OSError, sqlite3.Error, ValueError:
            raise SmaSunnyPortalHistoryError(
                "Could not update the private SMA forecast history"
            ) from None

    async def async_remove(self) -> None:
        """Remove all history files when the config entry is deleted."""
        try:
            await self._hass.async_add_executor_job(self._remove)
        except OSError:
            raise SmaSunnyPortalHistoryError(
                "Could not remove the private SMA forecast history"
            ) from None

    def _record(self, balance: ConsumerBalance, issued_at: datetime) -> None:
        """Perform one short SQLite transaction in an executor thread."""
        issued_epoch = _utc_epoch(issued_at)
        self._prepare_private_file()

        with sqlite3.connect(self._path, timeout=30) as connection:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA busy_timeout = 30000")
            self._ensure_schema(connection)

            measurement_rows = tuple(
                (
                    self._plant_id,
                    _utc_epoch(item.time_utc),
                    item.pv_generation_w,
                    item.total_consumption_w,
                    issued_epoch,
                )
                for item in balance.measurements
            )
            connection.executemany(
                """
                INSERT INTO measurements (
                    plant_id,
                    valid_at_utc,
                    pv_generation_w,
                    total_consumption_w,
                    received_at_utc
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT (plant_id, valid_at_utc) DO UPDATE SET
                    pv_generation_w = excluded.pv_generation_w,
                    total_consumption_w = excluded.total_consumption_w,
                    received_at_utc = excluded.received_at_utc
                """,
                measurement_rows,
            )

            last_snapshot = connection.execute(
                """
                SELECT MAX(issued_at_utc)
                FROM forecast_snapshots
                WHERE plant_id = ?
                """,
                (self._plant_id,),
            ).fetchone()[0]
            snapshot_due = (
                last_snapshot is None
                or issued_epoch - int(last_snapshot)
                >= FORECAST_ARCHIVE_INTERVAL_SECONDS
            )

            if snapshot_due and balance.predictions:
                valid_epochs = tuple(
                    _utc_epoch(item.time_utc) for item in balance.predictions
                )
                cursor = connection.execute(
                    """
                    INSERT INTO forecast_snapshots (
                        plant_id,
                        issued_at_utc,
                        first_valid_at_utc,
                        last_valid_at_utc
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (
                        self._plant_id,
                        issued_epoch,
                        min(valid_epochs),
                        max(valid_epochs),
                    ),
                )
                snapshot_id = cursor.lastrowid
                if snapshot_id is None:
                    raise sqlite3.IntegrityError(
                        "forecast snapshot did not receive an identifier"
                    )
                connection.executemany(
                    """
                    INSERT INTO forecast_points (
                        snapshot_id,
                        valid_at_utc,
                        pv_generation_w,
                        total_consumption_w
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (
                        (
                            snapshot_id,
                            _utc_epoch(item.time_utc),
                            item.pv_generation_w,
                            item.total_consumption_w,
                        )
                        for item in balance.predictions
                    ),
                )

            connection.execute(
                """
                DELETE FROM forecast_snapshots
                WHERE plant_id = ? AND issued_at_utc < ?
                """,
                (
                    self._plant_id,
                    issued_epoch - FORECAST_ARCHIVE_RETENTION_SECONDS,
                ),
            )
            connection.execute(
                """
                DELETE FROM measurements
                WHERE plant_id = ? AND valid_at_utc < ?
                """,
                (
                    self._plant_id,
                    issued_epoch - MEASUREMENT_ARCHIVE_RETENTION_SECONDS,
                ),
            )

    def _prepare_private_file(self) -> None:
        """Create the database with restrictive permissions before SQLite opens it."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        flags = os.O_CREAT | os.O_RDWR
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(self._path, flags, 0o600)
        os.close(descriptor)
        self._path.chmod(0o600)

    @staticmethod
    def _ensure_schema(connection: sqlite3.Connection) -> None:
        """Create or validate the deliberately small version-one schema."""
        current_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        if current_version not in {0, HISTORY_DATABASE_SCHEMA_VERSION}:
            raise sqlite3.DatabaseError(
                "unsupported SMA forecast history schema version"
            )

        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS forecast_snapshots (
                snapshot_id INTEGER PRIMARY KEY,
                plant_id TEXT NOT NULL,
                issued_at_utc INTEGER NOT NULL,
                first_valid_at_utc INTEGER NOT NULL,
                last_valid_at_utc INTEGER NOT NULL,
                UNIQUE (plant_id, issued_at_utc)
            );

            CREATE TABLE IF NOT EXISTS forecast_points (
                snapshot_id INTEGER NOT NULL,
                valid_at_utc INTEGER NOT NULL,
                pv_generation_w REAL NOT NULL,
                total_consumption_w REAL NOT NULL,
                PRIMARY KEY (snapshot_id, valid_at_utc),
                FOREIGN KEY (snapshot_id)
                    REFERENCES forecast_snapshots (snapshot_id)
                    ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS forecast_points_valid_at
                ON forecast_points (valid_at_utc);

            CREATE TABLE IF NOT EXISTS measurements (
                plant_id TEXT NOT NULL,
                valid_at_utc INTEGER NOT NULL,
                pv_generation_w REAL NOT NULL,
                total_consumption_w REAL NOT NULL,
                received_at_utc INTEGER NOT NULL,
                PRIMARY KEY (plant_id, valid_at_utc)
            );

            CREATE INDEX IF NOT EXISTS measurements_valid_at
                ON measurements (valid_at_utc);
            """
        )
        connection.execute(f"PRAGMA user_version = {HISTORY_DATABASE_SCHEMA_VERSION}")

    def _remove(self) -> None:
        """Delete the database and any SQLite sidecar left after an interruption."""
        for suffix in ("", "-journal", "-shm", "-wal"):
            Path(f"{self._path}{suffix}").unlink(missing_ok=True)
