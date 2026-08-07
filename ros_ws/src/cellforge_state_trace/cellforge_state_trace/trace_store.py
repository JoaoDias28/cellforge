"""Durable trace event storage with monotonic sequence numbering and query support."""

from __future__ import annotations

import json
import sqlite3
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
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_row(self) -> tuple[Any, ...]:
        return (
            self.trace_id,
            self.job_id,
            self.cell_id,
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
            component_instance_id=row[3],
            command_id=row[4],
            sequence=row[5],
            event_type=row[6],
            severity=row[7],
            payload=json.loads(row[8]) if row[8] else {},
            timestamp=datetime.fromisoformat(row[9]),
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
    component_instance_id TEXT NOT NULL DEFAULT '',
    command_id TEXT NOT NULL DEFAULT '',
    sequence INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'INFO',
    payload_json TEXT NOT NULL DEFAULT '{}',
    recorded_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_events_trace_id ON events(trace_id);
CREATE INDEX IF NOT EXISTS idx_events_job_id ON events(job_id);
CREATE INDEX IF NOT EXISTS idx_events_event_type ON events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_severity ON events(severity);
CREATE INDEX IF NOT EXISTS idx_events_recorded_at ON events(recorded_at);
"""


class SqliteTraceEventStore(TraceEventStore):
    """SQLite-backed append-only trace event store with restart-safe sequencing."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(_DDL)
        self._conn.commit()
        self._sequence = self._load_max_sequence()

    def _load_max_sequence(self) -> int:
        row = self._conn.execute("SELECT COALESCE(MAX(sequence), 0) FROM events").fetchone()
        return int(row[0]) if row else 0

    def record(self, event: TraceEvent) -> int:
        next_seq = self._sequence + 1
        self._conn.execute(
            "INSERT INTO events (trace_id, job_id, cell_id, component_instance_id, "
            "command_id, sequence, event_type, severity, payload_json, recorded_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                event.trace_id,
                event.job_id,
                event.cell_id,
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
            "trace_id, job_id, cell_id, component_instance_id, command_id, "
            "sequence, event_type, severity, payload_json, recorded_at"
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
    """Return all events for a single trace."""
    return store.query(trace_id=trace_id, limit=10000)


def query_events_by_type(
    store: TraceEventStore, event_type: str, *, limit: int = 1000
) -> list[TraceEvent]:
    """Return the most recent events of a given type."""
    return store.query(event_type=event_type, limit=limit)
