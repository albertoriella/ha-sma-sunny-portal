"""Bounded private history for SMA forecasts and measured power."""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Literal

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
type ForecastHistoryMode = Literal["latest", "day_ahead", "rolling"]

FORECAST_HISTORY_MODES = frozenset({"latest", "day_ahead", "rolling"})


@dataclass(frozen=True, slots=True)
class ArchivedMeasurement:
    """One measured point read from the private history database."""

    time_utc: datetime
    pv_generation_w: float
    total_consumption_w: float


@dataclass(frozen=True, slots=True)
class ArchivedPrediction:
    """One forecast point with both issue and target timestamps."""

    time_utc: datetime
    issued_at_utc: datetime
    pv_generation_w: float
    total_consumption_w: float


@dataclass(frozen=True, slots=True)
class ArchivedDay:
    """Measured and predicted power for one requested local-day interval."""

    measurements: tuple[ArchivedMeasurement, ...]
    predictions: tuple[ArchivedPrediction, ...]
    first_available_utc: datetime | None
    last_available_utc: datetime | None


def _utcnow() -> datetime:
    """Return the current aware UTC time."""
    return datetime.now(UTC)


def _utc_epoch(value: datetime) -> int:
    """Convert one aware datetime to a whole-second UTC epoch."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("history timestamps must be timezone-aware")
    return int(value.timestamp())


def _utc_datetime(value: int) -> datetime:
    """Convert one whole-second epoch to an aware UTC datetime."""
    return datetime.fromtimestamp(value, UTC)


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

    async def async_get_day(
        self,
        start_utc: datetime,
        end_utc: datetime,
        mode: ForecastHistoryMode,
    ) -> ArchivedDay:
        """Read one local-day UTC interval using the requested forecast vintage."""
        try:
            start_epoch = _utc_epoch(start_utc)
            end_epoch = _utc_epoch(end_utc)
            if end_epoch <= start_epoch or end_epoch - start_epoch > 26 * 60 * 60:
                raise ValueError("history interval must represent one local day")
            if mode not in FORECAST_HISTORY_MODES:
                raise ValueError("unsupported forecast history mode")
            return await self._hass.async_add_executor_job(
                self._get_day,
                start_epoch,
                end_epoch,
                mode,
            )
        except OSError, sqlite3.Error, ValueError:
            raise SmaSunnyPortalHistoryError(
                "Could not read the private SMA forecast history"
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

    def _get_day(
        self,
        start_epoch: int,
        end_epoch: int,
        mode: ForecastHistoryMode,
    ) -> ArchivedDay:
        """Read one bounded interval without modifying the SQLite database."""
        if not self._path.exists():
            return ArchivedDay((), (), None, None)

        with sqlite3.connect(
            f"file:{self._path}?mode=ro",
            uri=True,
            timeout=30,
        ) as connection:
            connection.execute("PRAGMA query_only = ON")
            connection.execute("PRAGMA busy_timeout = 30000")
            schema_version = int(
                connection.execute("PRAGMA user_version").fetchone()[0]
            )
            if schema_version != HISTORY_DATABASE_SCHEMA_VERSION:
                raise sqlite3.DatabaseError(
                    "unsupported SMA forecast history schema version"
                )

            measurement_rows = connection.execute(
                """
                SELECT
                    valid_at_utc,
                    pv_generation_w,
                    total_consumption_w
                FROM measurements
                WHERE plant_id = ?
                    AND valid_at_utc >= ?
                    AND valid_at_utc < ?
                ORDER BY valid_at_utc
                """,
                (self._plant_id, start_epoch, end_epoch),
            ).fetchall()

            if mode == "rolling":
                prediction_rows = self._rolling_prediction_rows(
                    connection,
                    start_epoch,
                    end_epoch,
                )
            else:
                prediction_rows = self._snapshot_prediction_rows(
                    connection,
                    start_epoch,
                    end_epoch,
                    mode,
                )

            bounds = connection.execute(
                """
                SELECT MIN(valid_at_utc), MAX(valid_at_utc)
                FROM (
                    SELECT valid_at_utc
                    FROM measurements
                    WHERE plant_id = ?

                    UNION ALL

                    SELECT forecast_points.valid_at_utc
                    FROM forecast_points
                    JOIN forecast_snapshots USING (snapshot_id)
                    WHERE forecast_snapshots.plant_id = ?
                )
                """,
                (self._plant_id, self._plant_id),
            ).fetchone()

        return ArchivedDay(
            measurements=tuple(
                ArchivedMeasurement(
                    time_utc=_utc_datetime(row[0]),
                    pv_generation_w=float(row[1]),
                    total_consumption_w=float(row[2]),
                )
                for row in measurement_rows
            ),
            predictions=tuple(
                ArchivedPrediction(
                    time_utc=_utc_datetime(row[0]),
                    issued_at_utc=_utc_datetime(row[3]),
                    pv_generation_w=float(row[1]),
                    total_consumption_w=float(row[2]),
                )
                for row in prediction_rows
            ),
            first_available_utc=(
                _utc_datetime(bounds[0]) if bounds[0] is not None else None
            ),
            last_available_utc=(
                _utc_datetime(bounds[1]) if bounds[1] is not None else None
            ),
        )

    def _snapshot_prediction_rows(
        self,
        connection: sqlite3.Connection,
        start_epoch: int,
        end_epoch: int,
        mode: ForecastHistoryMode,
    ) -> list[tuple[int, float, float, int]]:
        """Read a single latest or day-ahead forecast vintage."""
        snapshot = connection.execute(
            """
            SELECT snapshot_id, issued_at_utc
            FROM forecast_snapshots
            WHERE plant_id = ?
                AND first_valid_at_utc < ?
                AND last_valid_at_utc >= ?
                AND (? != 'day_ahead' OR issued_at_utc <= ?)
            ORDER BY issued_at_utc DESC
            LIMIT 1
            """,
            (self._plant_id, end_epoch, start_epoch, mode, start_epoch),
        ).fetchone()
        if snapshot is None:
            return []

        return connection.execute(
            """
            SELECT
                valid_at_utc,
                pv_generation_w,
                total_consumption_w,
                ?
            FROM forecast_points
            WHERE snapshot_id = ?
                AND valid_at_utc >= ?
                AND valid_at_utc < ?
            ORDER BY valid_at_utc
            """,
            (snapshot[1], snapshot[0], start_epoch, end_epoch),
        ).fetchall()

    def _rolling_prediction_rows(
        self,
        connection: sqlite3.Connection,
        start_epoch: int,
        end_epoch: int,
    ) -> list[tuple[int, float, float, int]]:
        """Use the newest archived vintage issued before every target interval."""
        candidate_rows = connection.execute(
            """
            SELECT
                forecast_points.valid_at_utc,
                forecast_points.pv_generation_w,
                forecast_points.total_consumption_w,
                forecast_snapshots.issued_at_utc
            FROM forecast_points
            JOIN forecast_snapshots USING (snapshot_id)
            WHERE forecast_snapshots.plant_id = ?
                AND forecast_points.valid_at_utc >= ?
                AND forecast_points.valid_at_utc < ?
                AND forecast_snapshots.issued_at_utc
                    <= forecast_points.valid_at_utc
            ORDER BY
                forecast_points.valid_at_utc,
                forecast_snapshots.issued_at_utc DESC
            """,
            (self._plant_id, start_epoch, end_epoch),
        ).fetchall()

        newest_by_target: dict[int, tuple[int, float, float, int]] = {}
        for row in candidate_rows:
            newest_by_target.setdefault(row[0], row)
        return list(newest_by_target.values())

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
