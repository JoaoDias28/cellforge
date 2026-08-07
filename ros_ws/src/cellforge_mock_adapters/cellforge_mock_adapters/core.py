"""Deterministic L0 mock adapter engine built on the Task 008 device SDK.

The engine owns only generic mock behavior: validated scenario lookup, configurable operation
timing, catalog fault injection, certain cancellation, and configurable restart reconciliation.
Device-specific payload checks and deterministic outputs live in ``devices.py``. All completion
paths flow through ``BaseDeviceAdapter`` so a mock can never report success without publishing the
coherent BUSY -> READY/FAULT/UNKNOWN transition sequence first.
"""

from __future__ import annotations

import asyncio
import json
from abc import abstractmethod
from collections.abc import Callable
from typing import Any

from cellforge_device_sdk.adapter import (
    BaseDeviceAdapter,
    CancellationDisposition,
    OperationContext,
)
from cellforge_device_sdk.models import (
    CapabilityCommand,
    CommandResult,
    DeviceOperationFault,
    DeviceState,
    DeviceStateSnapshot,
    Fault,
    RestartReconciliation,
)
from cellforge_device_sdk.state import CanonicalStatePublisher

from cellforge_mock_adapters.scenarios import (
    UNCERTAIN_FAULT_CODES,
    DeviceScenario,
    OperationBehavior,
)


class MockDeviceAdapter(BaseDeviceAdapter):
    """L0 contract mock with configurable timing, deterministic outcomes, and fault injection."""

    def __init__(
        self,
        scenario: DeviceScenario,
        *,
        state_sink: Callable[[DeviceStateSnapshot], None] | None = None,
    ) -> None:
        publisher = CanonicalStatePublisher(scenario.component_instance_id, state_sink)
        super().__init__(scenario.component_instance_id, state_publisher=publisher)
        self.scenario = scenario
        self.operation_started = asyncio.Event()

    def validate_command(self, command: CapabilityCommand) -> Fault | None:
        """Reject capabilities outside the scenario and invalid payloads before any work."""

        behavior = self.scenario.operations.get(command.capability)
        if behavior is None:
            return Fault(
                code="sdk.command.invalid_input",
                message=(
                    f"Capability '{command.capability}' is not configured for this "
                    f"'{self.scenario.device_kind}' mock."
                ),
            )
        payload = json.loads(command.input_payload_json)
        return self.validate_payload(command.capability, payload)

    async def execute_operation(self, context: OperationContext) -> CommandResult:
        """Wait the configured duration, then apply the configured deterministic outcome."""

        self.operation_started.set()
        command = context.command
        behavior = self._behavior(command)
        await asyncio.sleep(behavior.duration_seconds)
        if behavior.fault is not None:
            return self._fault_result(command, behavior)
        payload = json.loads(command.input_payload_json)
        return self.complete_operation(command, payload)

    async def request_cancellation(self, context: OperationContext) -> CancellationDisposition:
        """A virtual timer provably stops, so mock cancellation is always outcome-certain."""

        return CancellationDisposition(
            outcome_certain=True,
            message="Mock operation timer stopped; no physical state exists to reconcile.",
        )

    async def read_restart_reconciliation(self) -> RestartReconciliation:
        """Report the configured restart outcome; an L0 mock has no hidden physical state."""

        if self.scenario.restart == "uncertain":
            return RestartReconciliation(
                state=DeviceState.UNKNOWN,
                ready=False,
                outcome_certain=False,
                details={"source": "mock", "reason": "configured_uncertain_restart"},
            )
        return RestartReconciliation(
            state=DeviceState.READY,
            ready=True,
            outcome_certain=True,
            details={"source": "mock"},
        )

    def validate_payload(self, capability: str, payload: dict[str, Any]) -> Fault | None:
        """Device-specific input validation; defaults to accepting the payload."""

        return None

    @abstractmethod
    def complete_operation(
        self, command: CapabilityCommand, payload: dict[str, Any]
    ) -> CommandResult:
        """Produce the deterministic device-specific success or declared failure result."""

    def _behavior(self, command: CapabilityCommand) -> OperationBehavior:
        return self.scenario.operations[command.capability]

    def _fault_result(
        self, command: CapabilityCommand, behavior: OperationBehavior
    ) -> CommandResult:
        assert behavior.fault is not None
        if behavior.fault in UNCERTAIN_FAULT_CODES:
            return CommandResult(
                command_id=command.command_id,
                trace_id=command.trace_id,
                success=False,
                result_code=behavior.fault,
                result_message=(
                    f"Mock device reports an uncertain outcome for '{behavior.capability}'; "
                    "reconcile before continuing."
                ),
                outcome_certain=False,
            )
        raise DeviceOperationFault(
            Fault(
                code=behavior.fault,
                message=f"Scenario-injected fault for '{behavior.capability}'.",
                details={"capability": behavior.capability, "source": "mock"},
            )
        )


def success_result(command: CapabilityCommand, output: dict[str, Any]) -> CommandResult:
    """Build a deterministic success result with a real, non-empty output payload."""

    return CommandResult(
        command_id=command.command_id,
        trace_id=command.trace_id,
        success=True,
        result_code=f"{command.capability}.completed",
        result_message=f"'{command.capability}' completed by the L0 mock.",
        output_payload_json=json.dumps(output, sort_keys=True),
    )
