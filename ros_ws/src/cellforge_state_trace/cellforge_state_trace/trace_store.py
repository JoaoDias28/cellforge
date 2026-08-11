"""Durable trace event storage with monotonic sequence numbering and query support."""

from __future__ import annotations

import json
import sqlite3
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class TraceEvent:
    """A single durable, ordered trace event for correlation and audit."""

    trace_id: str
    job_id: str
    cell_id: str
    component_instance_id: str
    command_id: str
    sequence: int
    event_type: str
    severity: str
    bundle_id: str = ""
    source_revision: str = ""
    recipe_id: str = ""
    recipe_version: int = 0
    recipe_sha256: str = ""
    task_id: str = ""
    task_sha256: str = ""
    execution_mode: str = ""
    calibration_ids: tuple[str, ...] = ()
    calibration_sha256s: tuple[str, ...] = ()
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_row(self) -> tuple[Any, ...]:
        return (
            self.trace_id,
            self.job_id,
            self.cell_id,
            self.bundle_id,
            self.source_revision,
            self.recipe_id,
            self.recipe_version,
            self.recipe_sha256,
            self.task_id,
            self.task_sha256,
            self.execution_mode,
            json.dumps(self.calibration_ids),
            json.dumps(self.calibration_sha256s),
            self.component_instance_id,
            self.command_id,
            self.sequence,
            self.event_type,
            self.severity,
            json.dumps(self.payload, sort_keys=True),
            self.timestamp.isoformat(),
        )

    @classmethod
    def from_row(cls, row: tuple[Any, ...]) -> TraceEvent:
        return cls(
            trace_id=row[0],
            job_id=row[1],
            cell_id=row[2],
            bundle_id=row[3],
            source_revision=row[4],
            recipe_id=row[5],
            recipe_version=row[6],
            recipe_sha256=row[7],
            task_id=row[8],
            task_sha256=row[9],
            execution_mode=row[10],
            calibration_ids=tuple(json.loads(row[11])),
            calibration_sha256s=tuple(json.loads(row[12])),
            component_instance_id=row[13],
            command_id=row[14],
            sequence=row[15],
            event_type=row[16],
            severity=row[17],
            payload=json.loads(row[18]) if row[18] else {},
            timestamp=datetime.fromisoformat(row[19]),
        )


class TraceEventStore(ABC):
    """Append-only durable store for structured trace events."""

    @abstractmethod
    def record(self, event: TraceEvent) -> int:
        """Persist *event* and return its assigned sequence number."""

    @abstractmethod
    def query(
        self,
        *,
        trace_id: str | None = None,
        job_id: str | None = None,
        event_type: str | None = None,
        severity: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 1000,
    ) -> list[TraceEvent]:
        """Return events matching optional filters in insertion order."""

    @abstractmethod
    def close(self) -> None:
        """Flush and release resources."""


_DDL = """\
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trace_id TEXT NOT NULL,
    job_id TEXT NOT NULL,
    cell_id TEXT NOT NULL,
    bundle_id TEXT NOT NULL DEFAULT '',
    source_revision TEXT NOT NULL DEFAULT '',
    recipe_id TEXT NOT NULL DEFAULT '',
    recipe_version INTEGER NOT NULL DEFAULT 0,
    recipe_sha256 TEXT NOT NULL DEFAULT '',
    task_id TEXT NOT NULL DEFAULT '',
    task_sha256 TEXT NOT NULL DEFAULT '',
    execution_mode TEXT NOT NULL DEFAULT '',
    calibration_ids_json TEXT NOT NULL DEFAULT '[]',
    calibration_sha256s_json TEXT NOT NULL DEFAULT '[]',
    component_instance_id TEXT NOT NULL DEFAULT '',
    command_id TEXT NOT NULL DEFAULT '',
    sequence INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'INFO',
    payload_json TEXT NOT NULL DEFAULT '{}',
    recorded_at TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_events_sequence ON events(sequence);
CREATE INDEX IF NOT EXISTS idx_events_trace_id ON events(trace_id);
CREATE INDEX IF NOT EXISTS idx_events_job_id ON events(job_id);
CREATE INDEX IF NOT EXISTS idx_events_event_type ON events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_severity ON events(severity);
CREATE INDEX IF NOT EXISTS idx_events_recorded_at ON events(recorded_at);
"""


class SqliteTraceEventStore(TraceEventStore):
    """SQLite-backed append-only trace event store with restart-safe sequencing.

    Sequence allocation is protected by a threading lock.  A ``UNIQUE`` index on
    ``sequence`` provides a second line of defense against duplicates.
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(_DDL)
        columns = {
            str(row[1]) for row in self._conn.execute("PRAGMA table_info(events)").fetchall()
        }
        migrations = {
            "bundle_id": "TEXT NOT NULL DEFAULT ''",
            "source_revision": "TEXT NOT NULL DEFAULT ''",
            "recipe_id": "TEXT NOT NULL DEFAULT ''",
            "recipe_version": "INTEGER NOT NULL DEFAULT 0",
            "recipe_sha256": "TEXT NOT NULL DEFAULT ''",
            "task_id": "TEXT NOT NULL DEFAULT ''",
            "task_sha256": "TEXT NOT NULL DEFAULT ''",
            "execution_mode": "TEXT NOT NULL DEFAULT ''",
            "calibration_ids_json": "TEXT NOT NULL DEFAULT '[]'",
            "calibration_sha256s_json": "TEXT NOT NULL DEFAULT '[]'",
        }
        for column, definition in migrations.items():
            if column not in columns:
                self._conn.execute(f"ALTER TABLE events ADD COLUMN {column} {definition}")
        self._conn.commit()
        self._sequence = self._load_max_sequence()
        self._lock = threading.Lock()

    def _load_max_sequence(self) -> int:
        row = self._conn.execute("SELECT COALESCE(MAX(sequence), 0) FROM events").fetchone()
        return int(row[0]) if row else 0

    def record(self, event: TraceEvent) -> int:
        """Atomically allocate next sequence, insert, and commit under lock."""
        with self._lock:
            next_seq = self._sequence + 1
            self._conn.execute(
                "INSERT INTO events (trace_id, job_id, cell_id, bundle_id, source_revision, "
                "recipe_id, recipe_version, recipe_sha256, task_id, task_sha256, execution_mode, "
                "calibration_ids_json, calibration_sha256s_json, component_instance_id, "
                "command_id, sequence, event_type, severity, payload_json, recorded_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    event.trace_id,
                    event.job_id,
                    event.cell_id,
                    event.bundle_id,
                    event.source_revision,
                    event.recipe_id,
                    event.recipe_version,
                    event.recipe_sha256,
                    event.task_id,
                    event.task_sha256,
                    event.execution_mode,
                    json.dumps(event.calibration_ids),
                    json.dumps(event.calibration_sha256s),
                    event.component_instance_id,
                    event.command_id,
                    next_seq,
                    event.event_type,
                    event.severity,
                    json.dumps(event.payload, sort_keys=True),
                    event.timestamp.isoformat(),
                ),
            )
            self._conn.commit()
            self._sequence = next_seq
            return next_seq

    def query(
        self,
        *,
        trace_id: str | None = None,
        job_id: str | None = None,
        event_type: str | None = None,
        severity: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 1000,
    ) -> list[TraceEvent]:
        clauses: list[str] = []
        params: list[Any] = []

        if trace_id is not None:
            clauses.append("trace_id = ?")
            params.append(trace_id)
        if job_id is not None:
            clauses.append("job_id = ?")
            params.append(job_id)
        if event_type is not None:
            clauses.append("event_type = ?")
            params.append(event_type)
        if severity is not None:
            clauses.append("severity = ?")
            params.append(severity)
        if start is not None:
            clauses.append("recorded_at >= ?")
            params.append(start.isoformat())
        if end is not None:
            clauses.append("recorded_at <= ?")
            params.append(end.isoformat())

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        columns = (
            "trace_id, job_id, cell_id, bundle_id, source_revision, recipe_id, recipe_version, "
            "recipe_sha256, task_id, task_sha256, execution_mode, calibration_ids_json, "
            "calibration_sha256s_json, component_instance_id, command_id, sequence, event_type, "
            "severity, payload_json, recorded_at"
        )
        query_sql = f"SELECT {columns} FROM events {where} ORDER BY sequence ASC LIMIT ?"
        params.append(limit)
        rows = self._conn.execute(query_sql, tuple(params)).fetchall()
        return [TraceEvent.from_row(row) for row in rows]

    def close(self) -> None:
        self._conn.close()


def query_events_in_range(
    store: TraceEventStore,
    start: datetime,
    end: datetime,
    *,
    trace_id: str | None = None,
    limit: int = 1000,
) -> list[TraceEvent]:
    """Convenience helper to query events in a time window."""
    return store.query(trace_id=trace_id, start=start, end=end, limit=limit)


def query_job_trace(store: TraceEventStore, trace_id: str) -> list[TraceEvent]:
    """Return all events for a single trace in chronological order."""
    return store.query(trace_id=trace_id, limit=10000)


def query_events_by_type(
    store: TraceEventStore, event_type: str, *, limit: int = 1000
) -> list[TraceEvent]:
    """Return events of a given type in chronological order (oldest first)."""
    return store.query(event_type=event_type, limit=limit)


def convert_job_event_to_trace_event(message: Any) -> TraceEvent:
    """Convert a ROS ``JobEvent``-shaped object to a durable ``TraceEvent``.

    The *message* argument may be a generated ROS message or any object with the same
    shape (``header.stamp.sec/nanosec``, ``trace_id``, ``job_id``, ``cell_id``,
    ``bundle_id``, ``component_instance_id``, ``command_id``, ``event_type``, ``severity``,
    ``payload_json``).  This function is intentionally ROS-free so it can be tested
    without a runtime.
    """
    try:
        payload = json.loads(message.payload_json) if message.payload_json.strip() else {}
    except (json.JSONDecodeError, AttributeError):
        raise ValueError("payload_json must be valid JSON")
    if not isinstance(payload, dict):
        raise ValueError("payload_json must contain a JSON object")

    sec = message.header.stamp.sec
    nanosec = message.header.stamp.nanosec
    timestamp = datetime.fromtimestamp(sec + nanosec / 1_000_000_000.0, tz=UTC)

    return TraceEvent(
        trace_id=message.trace_id,
        job_id=message.job_id,
        cell_id=message.cell_id,
        bundle_id=str(getattr(message, "bundle_id", "")),
        source_revision=str(getattr(message, "source_revision", "")),
        recipe_id=str(getattr(message, "recipe_id", "")),
        recipe_version=int(getattr(message, "recipe_version", 0)),
        recipe_sha256=str(getattr(message, "recipe_sha256", "")),
        task_id=str(getattr(message, "task_id", "")),
        task_sha256=str(getattr(message, "task_sha256", "")),
        execution_mode=str(getattr(message, "execution_mode", "")),
        calibration_ids=tuple(getattr(message, "calibration_ids", ())),
        calibration_sha256s=tuple(getattr(message, "calibration_sha256s", ())),
        component_instance_id=message.component_instance_id,
        command_id=message.command_id,
        sequence=0,
        event_type=message.event_type,
        severity=message.severity,
        payload=payload,
        timestamp=timestamp,
    )
