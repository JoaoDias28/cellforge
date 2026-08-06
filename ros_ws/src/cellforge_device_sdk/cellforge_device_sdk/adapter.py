"""Base adapter execution semantics for timeout, cancellation, faults, and restart recovery."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass

from cellforge_device_sdk.models import (
    CapabilityCommand,
    CommandResult,
    DeviceOperationFault,
    DeviceState,
    Fault,
    RestartReconciliation,
)
from cellforge_device_sdk.state import CanonicalStatePublisher


class CancellationToken:
    """Cooperative cancellation signal passed to a vendor/protocol operation."""

    def __init__(self) -> None:
        self._requested = asyncio.Event()

    @property
    def requested(self) -> bool:
        """Whether the caller requested cancellation."""

        return self._requested.is_set()

    def request(self) -> None:
        """Request cancellation without claiming that physical work has stopped."""

        self._requested.set()

    async def wait(self) -> None:
        """Wait for the caller to request cancellation."""

        await self._requested.wait()


@dataclass(frozen=True, slots=True)
class OperationContext:
    """Immutable command identity plus cooperative cancellation for one operation."""

    command: CapabilityCommand
    cancellation: CancellationToken


@dataclass(frozen=True, slots=True)
class CancellationDisposition:
    """What the adapter can prove after forwarding a cancellation request."""

    outcome_certain: bool
    message: str


class BaseDeviceAdapter(ABC):
    """Vendor-neutral base class that never infers completion after uncertainty."""

    def __init__(
        self, component_instance_id: str, *, state_publisher: CanonicalStatePublisher | None = None
    ) -> None:
        self.state_publisher = state_publisher or CanonicalStatePublisher(component_instance_id)
        self._active_context: OperationContext | None = None

    def mark_ready(self) -> None:
        """Publish readiness after an adapter-specific connection/readiness check."""

        self.state_publisher.transition(DeviceState.READY)

    async def execute(self, command: CapabilityCommand) -> CommandResult:
        """Run one command with explicit readiness, cancellation, deadline, and fault semantics."""

        invalid_fault = self.validate_command(command)
        if invalid_fault is not None:
            return self._failure(command, invalid_fault.code, invalid_fault.message)

        snapshot = self.state_publisher.snapshot
        if not snapshot.ready:
            return self._failure(command, "sdk.command.not_ready", "Device is not ready.")
        if self._active_context is not None or snapshot.busy:
            return self._failure(
                command, "sdk.command.busy", "Device already has an active command."
            )

        context = OperationContext(command=command, cancellation=CancellationToken())
        self._active_context = context
        self.state_publisher.transition(DeviceState.BUSY, active_command_id=command.command_id)
        operation = asyncio.create_task(self.execute_operation(context))
        cancellation_waiter = asyncio.create_task(context.cancellation.wait())

        try:
            done, _ = await asyncio.wait(
                {operation, cancellation_waiter},
                timeout=command.timeout.total_seconds(),
                return_when=asyncio.FIRST_COMPLETED,
            )
            if cancellation_waiter in done:
                return await self._finish_cancelled(command, context, operation)
            if operation in done:
                return self._finish_operation(command, operation)
            return await self._finish_timeout(command, context, operation)
        finally:
            cancellation_waiter.cancel()
            await asyncio.gather(cancellation_waiter, return_exceptions=True)
            self._active_context = None

    def cancel(self, command_id: str) -> bool:
        """Request cancellation for the matching command without inventing a completion state."""

        context = self._active_context
        if context is None or context.command.command_id != command_id:
            return False
        context.cancellation.request()
        return True

    async def reconcile_after_restart(self) -> RestartReconciliation:
        """Reconcile actual hardware state before allowing new work after a process restart."""

        self.state_publisher.transition(DeviceState.CONNECTING)
        reconciliation = await self.read_restart_reconciliation()
        if not reconciliation.outcome_certain:
            command_id = self.state_publisher.snapshot.last_uncertain_command_id
            if command_id is None:
                command_id = "00000000-0000-0000-0000-000000000000"
            self.state_publisher.mark_uncertain(command_id, details=reconciliation.details)
            return reconciliation

        self.state_publisher.transition(
            reconciliation.state,
            ready=reconciliation.ready,
            fault=reconciliation.fault,
            details=reconciliation.details,
        )
        return reconciliation

    def validate_command(self, command: CapabilityCommand) -> Fault | None:
        """Return a deterministic fault for adapter-specific invalid inputs, if any."""

        return None

    @abstractmethod
    async def execute_operation(self, context: OperationContext) -> CommandResult:
        """Perform the vendor/protocol operation and return only a stable final result."""

    @abstractmethod
    async def read_restart_reconciliation(self) -> RestartReconciliation:
        """Observe hardware after restart; do not guess a prior command's outcome."""

    async def request_cancellation(self, context: OperationContext) -> CancellationDisposition:
        """Forward cancellation to the device and state only what is known by default."""

        return CancellationDisposition(
            outcome_certain=False,
            message="Cancellation was requested but device completion is not yet confirmed.",
        )

    def _finish_operation(
        self, command: CapabilityCommand, operation: asyncio.Task[CommandResult]
    ) -> CommandResult:
        try:
            result = operation.result()
        except DeviceOperationFault as error:
            return self._result_for_fault(command, error.fault)
        except asyncio.CancelledError:
            return self._uncertain(
                command, "sdk.command.cancelled_uncertain", "Operation task was cancelled."
            )
        except Exception:
            return self._uncertain(
                command,
                "sdk.adapter.unexpected_exception",
                "Adapter operation ended unexpectedly; reconcile hardware before continuing.",
            )

        if result.command_id != command.command_id or result.trace_id != command.trace_id:
            return self._uncertain(
                command,
                "sdk.adapter.identity_mismatch",
                "Adapter returned a result for a different command or trace.",
            )
        self._publish_result_state(result)
        return result

    async def _finish_cancelled(
        self,
        command: CapabilityCommand,
        context: OperationContext,
        operation: asyncio.Task[CommandResult],
    ) -> CommandResult:
        disposition = await self.request_cancellation(context)
        operation.cancel()
        await asyncio.gather(operation, return_exceptions=True)
        if not disposition.outcome_certain:
            return self._uncertain(command, "sdk.command.cancelled_uncertain", disposition.message)
        result = self._failure(command, "sdk.command.cancelled", disposition.message)
        self._publish_result_state(result)
        return result

    async def _finish_timeout(
        self,
        command: CapabilityCommand,
        context: OperationContext,
        operation: asyncio.Task[CommandResult],
    ) -> CommandResult:
        context.cancellation.request()
        await self.request_cancellation(context)
        operation.cancel()
        await asyncio.gather(operation, return_exceptions=True)
        return self._uncertain(
            command,
            "sdk.command.timeout",
            "Command deadline expired; reconcile hardware before continuing.",
        )

    def _publish_result_state(self, result: CommandResult) -> None:
        if not result.outcome_certain:
            self.state_publisher.mark_uncertain(result.command_id)
        elif result.fault is not None:
            self.state_publisher.transition(DeviceState.FAULT, fault=result.fault)
        else:
            self.state_publisher.transition(DeviceState.READY)

    def _result_for_fault(self, command: CapabilityCommand, fault: Fault) -> CommandResult:
        result = CommandResult(
            command_id=command.command_id,
            trace_id=command.trace_id,
            success=False,
            result_code=fault.code,
            result_message=fault.message,
            fault=fault,
        )
        self._publish_result_state(result)
        return result

    def _uncertain(self, command: CapabilityCommand, code: str, message: str) -> CommandResult:
        result = CommandResult(
            command_id=command.command_id,
            trace_id=command.trace_id,
            success=False,
            result_code=code,
            result_message=message,
            outcome_certain=False,
        )
        self._publish_result_state(result)
        return result

    @staticmethod
    def _failure(command: CapabilityCommand, code: str, message: str) -> CommandResult:
        return CommandResult(
            command_id=command.command_id,
            trace_id=command.trace_id,
            success=False,
            result_code=code,
            result_message=message,
        )
