"""Correlation validation for durable trace events.

Events representing commands must carry the identifiers required for audit and
correlation (trace_id, job_id, command_id).  Events that genuinely represent
non-command observations (cell state changes, operator acknowledgements) are
exempt from the command_id requirement but still require trace and job context.
"""

from __future__ import annotations

import re

_VALID_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")

_EVENT_TYPES_REQUIRING_COMMAND_ID: set[str] = {
    "device.command.requested",
    "device.command.accepted",
    "device.command.completed",
    "device.command.rejected",
    "device.command.cancelled",
}


class CorrelationError(ValueError):
    """Raised when a trace event lacks correlation identifiers required by its type."""


def validate_correlation(
    *,
    trace_id: str,
    job_id: str,
    command_id: str,
    event_type: str,
) -> None:
    """Validate that *event_type* carries the correlation identifiers it needs.

    Every event must carry a non-empty trace_id and job_id as UUIDs.
    Command-related events additionally require a non-empty command_id.
    """
    if not trace_id.strip():
        raise CorrelationError("trace_id must not be empty")
    if not _VALID_UUID.fullmatch(trace_id):
        raise CorrelationError(f"trace_id must be a UUID, got '{trace_id}'")
    if not job_id.strip():
        raise CorrelationError("job_id must not be empty")
    if not _VALID_UUID.fullmatch(job_id):
        raise CorrelationError(f"job_id must be a UUID, got '{job_id}'")

    if event_type in _EVENT_TYPES_REQUIRING_COMMAND_ID:
        if not command_id.strip():
            raise CorrelationError(f"event type '{event_type}' requires a non-empty command_id")
        if not _VALID_UUID.fullmatch(command_id):
            raise CorrelationError(f"command_id must be a UUID, got '{command_id}'")
