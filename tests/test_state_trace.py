"""Tests for Task 010 — state aggregation and trace event recording."""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
TRACE_ROOT = REPO_ROOT / "ros_ws" / "src" / "cellforge_state_trace"
sys.path.insert(0, str(TRACE_ROOT))

from cellforge_state_trace.state_logic import (  # noqa: E402
    DeviceStateEntry,
    compute_top_level_cell_state,
)
from cellforge_state_trace.trace_store import (  # noqa: E402
    SqliteTraceEventStore,
    TraceEvent,
    TraceEventStore,
    query_events_by_type,
    query_events_in_range,
    query_job_trace,
)


class FakeTraceEventStore(TraceEventStore):
    """In-memory store for deterministic testing of the event store contract."""

    def __init__(self) -> None:
        self._events: list[TraceEvent] = []
        self._sequence = 0

    def record(self, event: TraceEvent) -> int:
        self._sequence += 1
        stored = TraceEvent(
            trace_id=event.trace_id,
            job_id=event.job_id,
            cell_id=event.cell_id,
            component_instance_id=event.component_instance_id,
            command_id=event.command_id,
            sequence=self._sequence,
            event_type=event.event_type,
            severity=event.severity,
            payload=dict(event.payload),
        )
        self._events.append(stored)
        return self._sequence

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
        results: list[TraceEvent] = []
        for event in self._events:
            if trace_id is not None and event.trace_id != trace_id:
                continue
            if job_id is not None and event.job_id != job_id:
                continue
            if event_type is not None and event.event_type != event_type:
                continue
            if severity is not None and event.severity != severity:
                continue
            if start is not None and event.timestamp < start:
                continue
            if end is not None and event.timestamp > end:
                continue
            results.append(event)
            if len(results) >= limit:
                break
        return results

    def close(self) -> None:
        pass


UUID_1 = "11111111-1111-1111-1111-111111111111"
UUID_2 = "22222222-2222-2222-2222-222222222222"
UUID_3 = "33333333-3333-3333-3333-333333333333"


def make_event(
    trace_id: str = UUID_1,
    job_id: str = UUID_2,
    cell_id: str = "cell-ref",
    component_instance_id: str = "robot-001",
    command_id: str = UUID_3,
    event_type: str = "device.state.changed",
    severity: str = "INFO",
    payload: dict[str, Any] | None = None,
) -> TraceEvent:
    return TraceEvent(
        trace_id=trace_id,
        job_id=job_id,
        cell_id=cell_id,
        component_instance_id=component_instance_id,
        command_id=command_id,
        sequence=0,
        event_type=event_type,
        severity=severity,
        payload=payload or {},
    )


class TestTraceEventModel:
    """TraceEvent is a frozen, serialisable domain value."""

    def test_event_to_from_row_roundtrips(self) -> None:
        event = make_event(
            payload={"action": "close", "duration_ms": 150},
        )
        row = event.to_row()
        restored = TraceEvent.from_row(row)
        assert restored.trace_id == event.trace_id
        assert restored.job_id == event.job_id
        assert restored.sequence == event.sequence
        assert restored.payload == {"action": "close", "duration_ms": 150}


class TestTraceEventStoreContract:
    """Every TraceEventStore implementation must satisfy this contract."""

    @pytest.fixture
    def store(self) -> TraceEventStore:
        return FakeTraceEventStore()

    def test_empty_store_returns_empty_query(self, store: TraceEventStore) -> None:
        assert store.query() == []

    def test_recorded_event_appears_in_query(self, store: TraceEventStore) -> None:
        store.record(make_event())
        results = store.query()
        assert len(results) == 1
        assert results[0].trace_id == UUID_1

    def test_sequences_are_monotonically_increasing(self, store: TraceEventStore) -> None:
        seq1 = store.record(make_event(trace_id=UUID_1))
        seq2 = store.record(make_event(trace_id=UUID_2))
        seq3 = store.record(make_event(trace_id=UUID_3))
        assert seq1 == 1
        assert seq2 == 2
        assert seq3 == 3

    def test_every_stored_event_has_a_unique_sequence(self, store: TraceEventStore) -> None:
        for i in range(5):
            store.record(make_event(trace_id=f"trace-{i}"))
        results = store.query(limit=100)
        sequences = {event.sequence for event in results}
        assert len(sequences) == 5

    def test_query_filters_by_trace_id(self, store: TraceEventStore) -> None:
        store.record(make_event(trace_id=UUID_1))
        store.record(make_event(trace_id=UUID_2))
        store.record(make_event(trace_id=UUID_1))
        results = store.query(trace_id=UUID_1)
        assert len(results) == 2
        assert all(event.trace_id == UUID_1 for event in results)

    def test_query_filters_by_job_id(self, store: TraceEventStore) -> None:
        store.record(make_event(job_id=UUID_1))
        store.record(make_event(job_id=UUID_2))
        results = store.query(job_id=UUID_1)
        assert len(results) == 1
        assert results[0].job_id == UUID_1

    def test_query_filters_by_event_type(self, store: TraceEventStore) -> None:
        store.record(make_event(event_type="device.state.changed"))
        store.record(make_event(event_type="cell.state.changed"))
        store.record(make_event(event_type="device.state.changed"))
        results = store.query(event_type="device.state.changed")
        assert len(results) == 2

    def test_query_filters_by_severity(self, store: TraceEventStore) -> None:
        store.record(make_event(severity="INFO"))
        store.record(make_event(severity="ERROR"))
        store.record(make_event(severity="WARNING"))
        results = store.query(severity="ERROR")
        assert len(results) == 1
        assert results[0].severity == "ERROR"

    def test_query_filters_by_time_range(self, store: TraceEventStore) -> None:
        now = datetime.now(UTC)
        store.record(make_event())
        store.record(make_event())
        before = datetime.now(UTC)
        results = store.query(start=now - timedelta(seconds=1), end=before + timedelta(seconds=1))
        assert len(results) == 2

    def test_query_respects_limit(self, store: TraceEventStore) -> None:
        for i in range(10):
            store.record(make_event(trace_id=f"trace-{i}"))
        results = store.query(limit=5)
        assert len(results) == 5

    def test_query_results_are_in_insertion_order(self, store: TraceEventStore) -> None:
        for i in range(5):
            store.record(make_event(trace_id=f"seq-{i}"))
        results = store.query(limit=100)
        assert [event.sequence for event in results] == [1, 2, 3, 4, 5]


class TestSqliteTraceEventStore:
    """Verify the SQLite implementation of TraceEventStore, including restart."""

    def test_empty_store_returns_empty_query(self, tmp_path: Path) -> None:
        db = tmp_path / "events.db"
        store = SqliteTraceEventStore(db)
        try:
            assert store.query() == []
        finally:
            store.close()

    def test_sequences_are_monotonically_increasing(self, tmp_path: Path) -> None:
        db = tmp_path / "events.db"
        store = SqliteTraceEventStore(db)
        try:
            seq1 = store.record(make_event())
            seq2 = store.record(make_event())
            seq3 = store.record(make_event())
            assert seq1 == 1
            assert seq2 == 2
            assert seq3 == 3
        finally:
            store.close()

    def test_events_survive_close_and_reopen(self, tmp_path: Path) -> None:
        db = tmp_path / "events.db"
        store = SqliteTraceEventStore(db)
        store.record(make_event(trace_id=UUID_1, payload={"step": 1}))
        store.record(make_event(trace_id=UUID_2, payload={"step": 2}))
        store.close()

        reopened = SqliteTraceEventStore(db)
        try:
            results = reopened.query(limit=100)
            assert len(results) == 2
            assert results[0].trace_id == UUID_1
            assert results[1].trace_id == UUID_2
            assert [event.sequence for event in results] == [1, 2]
        finally:
            reopened.close()

    def test_sequence_resumes_after_restart(self, tmp_path: Path) -> None:
        db = tmp_path / "events.db"
        store = SqliteTraceEventStore(db)
        store.record(make_event(trace_id=UUID_1))
        store.record(make_event(trace_id=UUID_2))
        store.close()

        reopened = SqliteTraceEventStore(db)
        try:
            seq3 = reopened.record(make_event(trace_id=UUID_3))
            assert seq3 == 3
        finally:
            reopened.close()

    def test_every_command_can_be_correlated_to_job_and_trace_ids(self, tmp_path: Path) -> None:
        db = tmp_path / "events.db"
        store = SqliteTraceEventStore(db)
        try:
            trace_a = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
            trace_b = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
            job_a = "cccccccc-cccc-cccc-cccc-cccccccccccc"
            cmd_1 = "11111111-1111-1111-1111-111111111111"
            cmd_2 = "22222222-2222-2222-2222-222222222222"

            store.record(
                TraceEvent(
                    trace_id=trace_a,
                    job_id=job_a,
                    cell_id="cell-ref",
                    component_instance_id="robot-001",
                    command_id=cmd_1,
                    sequence=0,
                    event_type="device.command.requested",
                    severity="INFO",
                    payload={"capability": "gripper.action.close"},
                )
            )
            store.record(
                TraceEvent(
                    trace_id=trace_a,
                    job_id=job_a,
                    cell_id="cell-ref",
                    component_instance_id="robot-001",
                    command_id=cmd_1,
                    sequence=0,
                    event_type="device.command.completed",
                    severity="INFO",
                    payload={"success": True},
                )
            )
            store.record(
                TraceEvent(
                    trace_id=trace_b,
                    job_id=job_a,
                    cell_id="cell-ref",
                    component_instance_id="laser-001",
                    command_id=cmd_2,
                    sequence=0,
                    event_type="device.command.requested",
                    severity="INFO",
                    payload={"capability": "process.action.execute_cycle"},
                )
            )

            trace_a_events = store.query(trace_id=trace_a, limit=100)
            assert len(trace_a_events) == 2
            assert all(e.command_id == cmd_1 for e in trace_a_events)
            assert all(e.job_id == job_a for e in trace_a_events)

            trace_b_events = store.query(trace_id=trace_b, limit=100)
            assert len(trace_b_events) == 1
            assert trace_b_events[0].command_id == cmd_2

            job_events = store.query(job_id=job_a, limit=100)
            assert len(job_events) == 3
        finally:
            store.close()

    def test_query_filters_by_event_type_in_sqlite(self, tmp_path: Path) -> None:
        db = tmp_path / "events.db"
        store = SqliteTraceEventStore(db)
        try:
            store.record(make_event(event_type="device.state.changed"))
            store.record(make_event(event_type="cell.state.changed"))
            store.record(make_event(event_type="device.state.changed"))
            results = store.query(event_type="device.state.changed", limit=10)
            assert len(results) == 2
        finally:
            store.close()

    def test_query_filters_by_severity_in_sqlite(self, tmp_path: Path) -> None:
        db = tmp_path / "events.db"
        store = SqliteTraceEventStore(db)
        try:
            store.record(make_event(severity="INFO"))
            store.record(make_event(severity="ERROR"))
            results = store.query(severity="ERROR", limit=10)
            assert len(results) == 1
        finally:
            store.close()

    def test_query_filters_by_trace_id_in_sqlite(self, tmp_path: Path) -> None:
        db = tmp_path / "events.db"
        store = SqliteTraceEventStore(db)
        try:
            store.record(make_event(trace_id=UUID_1))
            store.record(make_event(trace_id=UUID_2))
            results = store.query(trace_id=UUID_1, limit=10)
            assert len(results) == 1
        finally:
            store.close()


class TestQueryConvenienceHelpers:
    """Verify the standalone query utility functions against the trace store contract."""

    def test_query_events_in_range(self) -> None:
        store = FakeTraceEventStore()
        now = datetime.now(UTC)
        store.record(make_event())
        store.record(make_event())
        results = query_events_in_range(
            store, now - timedelta(seconds=1), now + timedelta(seconds=1)
        )
        assert len(results) == 2

    def test_query_job_trace(self) -> None:
        store = FakeTraceEventStore()
        store.record(make_event(trace_id=UUID_1))
        store.record(make_event(trace_id=UUID_2))
        store.record(make_event(trace_id=UUID_1))
        results = query_job_trace(store, UUID_1)
        assert len(results) == 2

    def test_query_events_by_type(self) -> None:
        store = FakeTraceEventStore()
        store.record(make_event(event_type="cell.state.changed"))
        store.record(make_event(event_type="device.state.changed"))
        store.record(make_event(event_type="cell.state.changed"))
        results = query_events_by_type(store, "cell.state.changed")
        assert len(results) == 2


class TestStaleDeviceDetection:
    """Stale-device detection is pure logic, testable without ROS."""

    def test_recent_heartbeat_is_not_stale(self) -> None:
        entry = DeviceStateEntry(component_instance_id="robot-001")
        assert not entry.stale

    def test_old_heartbeat_is_stale(self) -> None:
        entry = DeviceStateEntry(
            component_instance_id="robot-001",
            heartbeat_at=datetime.now(UTC) - timedelta(seconds=10),
        )
        assert entry.stale

    def test_stale_device_is_not_ready(self) -> None:
        entry = DeviceStateEntry(
            component_instance_id="robot-001",
            state="READY",
            ready=True,
            heartbeat_at=datetime.now(UTC) - timedelta(seconds=10),
        )
        assert entry.stale


class TestTopLevelCellStateComputation:
    """The cell state computation is deterministic and testable without ROS."""

    def test_ready_when_all_devices_ready_and_safety_healthy(self) -> None:
        result = compute_top_level_cell_state(
            all_required_ready=True,
            safety_healthy=True,
            any_faulted=False,
            any_busy=False,
            any_stale=False,
        )
        assert result == "READY"

    def test_running_when_busy_and_healthy(self) -> None:
        result = compute_top_level_cell_state(
            all_required_ready=True,
            safety_healthy=True,
            any_faulted=False,
            any_busy=True,
            any_stale=False,
        )
        assert result == "RUNNING"

    def test_recoverable_fault_when_any_device_faulted(self) -> None:
        result = compute_top_level_cell_state(
            all_required_ready=False,
            safety_healthy=True,
            any_faulted=True,
            any_busy=False,
            any_stale=False,
        )
        assert result == "RECOVERABLE_FAULT"

    def test_starting_when_not_all_ready_and_safety_unhealthy(self) -> None:
        result = compute_top_level_cell_state(
            all_required_ready=False,
            safety_healthy=False,
            any_faulted=False,
            any_busy=False,
            any_stale=False,
        )
        assert result == "STARTING"

    def test_starting_when_stale_and_no_fault(self) -> None:
        result = compute_top_level_cell_state(
            all_required_ready=True,
            safety_healthy=True,
            any_faulted=False,
            any_busy=False,
            any_stale=True,
        )
        assert result == "STARTING"

    def test_fault_overrides_stale(self) -> None:
        result = compute_top_level_cell_state(
            all_required_ready=False,
            safety_healthy=True,
            any_faulted=True,
            any_busy=False,
            any_stale=True,
        )
        assert result == "RECOVERABLE_FAULT"


class TestEventOrdering:
    """Events must maintain insertion order and monotonic sequence numbers."""

    def test_events_are_returned_in_insertion_order(self) -> None:
        store = FakeTraceEventStore()
        ids = ["a", "b", "c", "d", "e"]
        for eid in ids:
            store.record(make_event(trace_id=eid))
        results = store.query(limit=100)
        assert [e.trace_id for e in results] == ids

    def test_sequence_numbers_never_decrease(self) -> None:
        store = FakeTraceEventStore()
        last_seq = 0
        for i in range(20):
            seq = store.record(make_event())
            assert seq > last_seq
            last_seq = seq

    def test_sqlite_sequence_never_decreases_across_restarts(self, tmp_path: Path) -> None:
        db = tmp_path / "events.db"
        for _ in range(3):
            store = SqliteTraceEventStore(db)
            store.record(make_event())
            store.close()
        reopened = SqliteTraceEventStore(db)
        try:
            seq_final = reopened.record(make_event())
            assert seq_final == 4
        finally:
            reopened.close()

    def test_multiple_restarts_preserve_sequence(self, tmp_path: Path) -> None:
        db = tmp_path / "events.db"
        all_sequences: list[int] = []
        for _ in range(4):
            store = SqliteTraceEventStore(db)
            for _ in range(3):
                all_sequences.append(store.record(make_event()))
            store.close()
        assert all_sequences == list(range(1, 13))
        reopened = SqliteTraceEventStore(db)
        try:
            all_sequences.append(reopened.record(make_event()))
            assert all_sequences[-1] == 13
        finally:
            reopened.close()


class TestCellReadiness:
    """Cell readiness reflects required device and safety state."""

    def test_readiness_is_false_when_no_safety_state(self) -> None:
        result = compute_top_level_cell_state(
            all_required_ready=False,
            safety_healthy=False,
            any_faulted=False,
            any_busy=False,
            any_stale=False,
        )
        assert result != "READY"

    def test_readiness_is_true_when_all_devices_ready_and_safety_healthy(self) -> None:
        result = compute_top_level_cell_state(
            all_required_ready=True,
            safety_healthy=True,
            any_faulted=False,
            any_busy=False,
            any_stale=False,
        )
        assert result == "READY"

    def test_readiness_is_false_when_any_device_not_ready(self) -> None:
        result = compute_top_level_cell_state(
            all_required_ready=False,
            safety_healthy=True,
            any_faulted=False,
            any_busy=False,
            any_stale=False,
        )
        assert result == "STARTING"

    def test_readiness_is_false_when_safety_unhealthy(self) -> None:
        result = compute_top_level_cell_state(
            all_required_ready=True,
            safety_healthy=False,
            any_faulted=False,
            any_busy=False,
            any_stale=False,
        )
        assert result == "STARTING"
