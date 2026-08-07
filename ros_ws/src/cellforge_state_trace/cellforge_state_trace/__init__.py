"""Cell state aggregation and durable trace event recording."""

from cellforge_state_trace.correlation import CorrelationError, validate_correlation
from cellforge_state_trace.state_logic import (
    CELL_STATE_OFFLINE,
    CELL_STATE_RECOVERABLE_FAULT,
    CELL_STATE_STARTING,
    DeviceStateEntry,
    SafetyStatusEntry,
    compute_top_level_cell_state,
)
from cellforge_state_trace.trace_store import (
    SqliteTraceEventStore,
    TraceEvent,
    TraceEventStore,
    convert_job_event_to_trace_event,
    query_events_by_type,
    query_events_in_range,
    query_job_trace,
)

__all__ = [
    "CELL_STATE_OFFLINE",
    "CELL_STATE_RECOVERABLE_FAULT",
    "CELL_STATE_STARTING",
    "CorrelationError",
    "DeviceStateEntry",
    "SafetyStatusEntry",
    "SqliteTraceEventStore",
    "TraceEvent",
    "TraceEventStore",
    "compute_top_level_cell_state",
    "convert_job_event_to_trace_event",
    "query_events_by_type",
    "query_events_in_range",
    "query_job_trace",
    "validate_correlation",
]
