"""Stable state, command, fault, and reconciliation values for device adapters."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

from cellforge_device_sdk.ids import validate_uuid

FAULT_CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_-]*(?:\.[a-z][a-z0-9_-]*){2,}$")


class DeviceState(StrEnum):
    """The canonical lifecycle states published by all adapters."""

    UNKNOWN = "UNKNOWN"
    OFFLINE = "OFFLINE"
    CONNECTING = "CONNECTING"
    NOT_READY = "NOT_READY"
    READY = "READY"
    BUSY = "BUSY"
    FAULT = "FAULT"
    MAINTENANCE = "MAINTENANCE"


def _validate_json_object(value: str, *, field_name: str) -> str:
    try:
        decoded = json.loads(value)
    except (TypeError, json.JSONDecodeError) as error:
        raise ValueError(f"{field_name} must be JSON") from error
    if not isinstance(decoded, dict):
        raise ValueError(f"{field_name} must contain a JSON object")
    return json.dumps(decoded, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True, slots=True)
class Fault:
    """A stable, operator-safe fault with optional diagnostic data."""

    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not FAULT_CODE_PATTERN.fullmatch(self.code):
            raise ValueError("fault code must have at least three stable dot-separated segments")
        if not self.message.strip():
            raise ValueError("fault message must not be blank")


class DeviceOperationFault(Exception):
    """Expected adapter failure that maps deterministically to a public ``Fault``."""

    def __init__(self, fault: Fault) -> None:
        self.fault = fault
        super().__init__(fault.code)


@dataclass(frozen=True, slots=True)
class CapabilityCommand:
    """A validated logical capability command, independent of a vendor protocol."""

    command_id: str
    trace_id: str
    capability: str
    input_payload_json: str
    timeout: timedelta

    def __post_init__(self) -> None:
        validate_uuid(self.command_id, field_name="command_id")
        validate_uuid(self.trace_id, field_name="trace_id")
        if not FAULT_CODE_PATTERN.fullmatch(self.capability):
            raise ValueError("capability must have at least three stable dot-separated segments")
        object.__setattr__(
            self,
            "input_payload_json",
            _validate_json_object(self.input_payload_json, field_name="input_payload_json"),
        )
        if self.timeout <= timedelta(0):
            raise ValueError("timeout must be positive")


@dataclass(frozen=True, slots=True)
class CommandResult:
    """Stable final outcome for a command; uncertainty is deliberately explicit."""

    command_id: str
    trace_id: str
    success: bool
    result_code: str
    result_message: str
    output_payload_json: str = "{}"
    fault: Fault | None = None
    outcome_certain: bool = True

    def __post_init__(self) -> None:
        validate_uuid(self.command_id, field_name="command_id")
        validate_uuid(self.trace_id, field_name="trace_id")
        if not FAULT_CODE_PATTERN.fullmatch(self.result_code):
            raise ValueError("result code must have at least three stable dot-separated segments")
        if not self.result_message.strip():
            raise ValueError("result message must not be blank")
        object.__setattr__(
            self,
            "output_payload_json",
            _validate_json_object(self.output_payload_json, field_name="output_payload_json"),
        )
        if self.success and self.fault is not None:
            raise ValueError("successful results must not include a fault")
        if self.fault is not None and self.result_code != self.fault.code:
            raise ValueError("fault result code must match fault code")


@dataclass(frozen=True, slots=True)
class DeviceStateSnapshot:
    """State publisher value with a monotonic revision and no hidden active outcome."""

    component_instance_id: str
    state: DeviceState
    ready: bool
    busy: bool
    fault: Fault | None
    active_command_id: str | None
    last_uncertain_command_id: str | None
    heartbeat_at: datetime
    revision: int
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.component_instance_id.strip():
            raise ValueError("component_instance_id must not be blank")
        if self.active_command_id is not None:
            validate_uuid(self.active_command_id, field_name="active_command_id")
        if self.last_uncertain_command_id is not None:
            validate_uuid(self.last_uncertain_command_id, field_name="last_uncertain_command_id")
        if self.revision < 0:
            raise ValueError("revision must not be negative")


@dataclass(frozen=True, slots=True)
class RestartReconciliation:
    """Hardware observation after restart; unproven outcomes cannot become ready."""

    state: DeviceState
    ready: bool
    outcome_certain: bool
    fault: Fault | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.outcome_certain and self.ready:
            raise ValueError("an uncertain restart reconciliation must not report ready")
