"""Canonical adapter state publishing with an optional generated-ROS conversion edge."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any, Protocol

from cellforge_device_sdk.models import DeviceState, DeviceStateSnapshot, Fault


class CanonicalStatePublisher:
    """Own and emit an adapter's monotonically-versioned canonical state."""

    def __init__(
        self, component_instance_id: str, sink: Callable[[DeviceStateSnapshot], None] | None = None
    ) -> None:
        now = datetime.now(UTC)
        self._sink = sink
        self._snapshot = DeviceStateSnapshot(
            component_instance_id=component_instance_id,
            state=DeviceState.UNKNOWN,
            ready=False,
            busy=False,
            fault=None,
            active_command_id=None,
            last_uncertain_command_id=None,
            heartbeat_at=now,
            revision=0,
        )

    @property
    def snapshot(self) -> DeviceStateSnapshot:
        """Return the latest immutable state snapshot."""

        return self._snapshot

    def transition(
        self,
        state: DeviceState,
        *,
        ready: bool | None = None,
        busy: bool | None = None,
        fault: Fault | None = None,
        active_command_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> DeviceStateSnapshot:
        """Publish a state transition and return the emitted snapshot."""

        snapshot = replace(
            self._snapshot,
            state=state,
            ready=state is DeviceState.READY if ready is None else ready,
            busy=state is DeviceState.BUSY if busy is None else busy,
            fault=fault,
            active_command_id=active_command_id,
            heartbeat_at=datetime.now(UTC),
            revision=self._snapshot.revision + 1,
            details={} if details is None else details,
        )
        self._snapshot = snapshot
        if self._sink is not None:
            self._sink(snapshot)
        return snapshot

    def mark_uncertain(
        self, command_id: str, *, details: dict[str, Any] | None = None
    ) -> DeviceStateSnapshot:
        """Block new work after an outcome that has not been reconciled with hardware."""

        snapshot = replace(
            self._snapshot,
            state=DeviceState.UNKNOWN,
            ready=False,
            busy=False,
            fault=Fault(
                code="sdk.communication.outcome_unknown",
                message="Command outcome is unknown; reconcile hardware before continuing.",
            ),
            active_command_id=None,
            last_uncertain_command_id=command_id,
            heartbeat_at=datetime.now(UTC),
            revision=self._snapshot.revision + 1,
            details={} if details is None else details,
        )
        self._snapshot = snapshot
        if self._sink is not None:
            self._sink(snapshot)
        return snapshot

    def heartbeat(self) -> DeviceStateSnapshot:
        """Refresh and emit the current state without changing its semantic fields."""

        snapshot = replace(
            self._snapshot,
            heartbeat_at=datetime.now(UTC),
            revision=self._snapshot.revision + 1,
        )
        self._snapshot = snapshot
        if self._sink is not None:
            self._sink(snapshot)
        return snapshot


class RosPublisher(Protocol):
    """The minimal publish protocol supplied by an ``rclpy`` publisher."""

    def publish(self, message: object) -> None: ...


class RosDeviceStatePublisher:
    """Convert canonical state at the ROS edge without importing ROS in the core SDK."""

    def __init__(self, publisher: RosPublisher) -> None:
        self._publisher = publisher

    def publish(self, snapshot: DeviceStateSnapshot) -> None:
        """Publish one ``cellforge_interfaces/DeviceState`` generated message."""

        try:
            from cellforge_interfaces.msg import (
                DeviceState as RosDeviceState,
            )
        except ImportError as error:  # pragma: no cover - requires a ROS Jazzy environment
            raise RuntimeError(
                "cellforge_interfaces must be sourced before ROS state publishing"
            ) from error

        message = RosDeviceState()
        timestamp = snapshot.heartbeat_at
        message.header.stamp.sec = int(timestamp.timestamp())
        message.header.stamp.nanosec = timestamp.microsecond * 1_000
        message.component_instance_id = snapshot.component_instance_id
        message.state = snapshot.state.value
        message.ready = snapshot.ready
        message.busy = snapshot.busy
        message.faulted = snapshot.fault is not None
        message.active_command_id = snapshot.active_command_id or ""
        message.fault_code = snapshot.fault.code if snapshot.fault is not None else ""
        message.fault_message = snapshot.fault.message if snapshot.fault is not None else ""
        message.details_json = json.dumps(snapshot.details, sort_keys=True, separators=(",", ":"))
        self._publisher.publish(message)
