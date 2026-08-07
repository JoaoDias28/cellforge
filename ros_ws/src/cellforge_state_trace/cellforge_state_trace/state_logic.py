"""Pure state-aggregation logic, testable without ROS."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

CELL_STATE_OFFLINE = "OFFLINE"
CELL_STATE_STARTING = "STARTING"
CELL_STATE_IDLE = "IDLE"
CELL_STATE_READY = "READY"
CELL_STATE_RUNNING = "RUNNING"
CELL_STATE_PAUSED = "PAUSED"
CELL_STATE_RECOVERABLE_FAULT = "RECOVERABLE_FAULT"
CELL_STATE_TERMINAL_FAULT = "TERMINAL_FAULT"
CELL_STATE_MAINTENANCE = "MAINTENANCE"
CELL_STATE_STOPPING = "STOPPING"

_DEFAULT_HEARTBEAT_TIMEOUT_S = 3.0
_DEFAULT_SAFETY_TIMEOUT_S = 3.0


@dataclass
class DeviceStateEntry:
    """Mutable in-memory view of the last known state for one device."""

    component_instance_id: str
    state: str = CELL_STATE_OFFLINE
    ready: bool = False
    busy: bool = False
    faulted: bool = False
    active_command_id: str = ""
    fault_code: str = ""
    fault_message: str = ""
    heartbeat_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    details_json: str = "{}"

    @classmethod
    def from_ros_device_state(cls, message: Any) -> DeviceStateEntry:
        """Create an entry from a ROS ``DeviceState`` message without a ROS import chain."""
        sec = message.header.stamp.sec
        nanosec = message.header.stamp.nanosec
        return cls(
            component_instance_id=message.component_instance_id,
            state=message.state,
            ready=message.ready,
            busy=message.busy,
            faulted=message.faulted,
            active_command_id=message.active_command_id,
            fault_code=message.fault_code,
            fault_message=message.fault_message,
            heartbeat_at=datetime.fromtimestamp(sec + nanosec / 1_000_000_000.0, tz=UTC),
            details_json=message.details_json,
        )

    @property
    def stale(self) -> bool:
        """Return True when the device heartbeat has exceeded the allowed interval."""
        return datetime.now(UTC) - self.heartbeat_at > timedelta(
            seconds=_DEFAULT_HEARTBEAT_TIMEOUT_S
        )

    def update(self, message: Any) -> None:
        """Refresh from a new ROS ``DeviceState`` message."""
        self.state = message.state
        self.ready = message.ready
        self.busy = message.busy
        self.faulted = message.faulted
        self.active_command_id = message.active_command_id
        self.fault_code = message.fault_code
        self.fault_message = message.fault_message
        sec = message.header.stamp.sec
        nanosec = message.header.stamp.nanosec
        self.heartbeat_at = datetime.fromtimestamp(sec + nanosec / 1_000_000_000.0, tz=UTC)
        self.details_json = message.details_json


@dataclass
class SafetyStatusEntry:
    """Read-only safety status with freshness tracking.

    Safety enforcement belongs to rated hardware. This is a fail-closed software
    readiness indication that refuses normal operation when safety status is absent
    or stale. It never implements, overrides, or bypasses any protective function.
    """

    healthy: bool = False
    last_received_at: datetime | None = None
    timeout_s: float = _DEFAULT_SAFETY_TIMEOUT_S

    @property
    def stale_or_missing(self) -> bool:
        """Return True when safety data has never arrived or exceeded the timeout."""
        if self.last_received_at is None:
            return True
        return datetime.now(UTC) - self.last_received_at > timedelta(seconds=self.timeout_s)

    @property
    def effective_healthy(self) -> bool:
        """Return True only when safety is confirmed healthy and fresh."""
        return self.healthy and not self.stale_or_missing

    def update(self, healthy: bool, *, timestamp: datetime | None = None) -> None:
        self.healthy = healthy
        self.last_received_at = timestamp if timestamp is not None else datetime.now(UTC)


def compute_top_level_cell_state(
    *,
    all_required_ready: bool,
    safety_healthy: bool,
    any_faulted: bool,
    any_busy: bool,
    any_required_stale: bool,
) -> str:
    """Return the canonical top-level cell state from device and safety inputs.

    ``any_required_stale`` considers only the configured required-device set.
    Optional/non-required stale devices do not prevent readiness.
    """
    if any_faulted:
        return CELL_STATE_RECOVERABLE_FAULT
    if any_required_stale:
        return CELL_STATE_STARTING
    if all_required_ready and safety_healthy:
        return CELL_STATE_READY if not any_busy else CELL_STATE_RUNNING
    return CELL_STATE_STARTING
