"""Reusable generic adapter contract suite and deterministic fake-adapter example."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import timedelta
from enum import StrEnum
from typing import Protocol

from cellforge_device_sdk.adapter import (
    BaseDeviceAdapter,
    CancellationDisposition,
    OperationContext,
)
from cellforge_device_sdk.ids import new_command_id, new_trace_id
from cellforge_device_sdk.models import (
    CapabilityCommand,
    CommandResult,
    DeviceOperationFault,
    DeviceState,
    Fault,
    RestartReconciliation,
)
from cellforge_device_sdk.state import CanonicalStatePublisher


class ContractScenario(StrEnum):
    """The required adapter contract cases, independent of any vendor protocol."""

    NOMINAL = "nominal"
    INVALID_INPUT = "invalid_input"
    NOT_READY = "not_ready"
    CANCELLATION = "cancellation"
    TIMEOUT = "timeout"
    FAULT = "fault"
    RESTART_UNKNOWN = "restart_unknown"


class ContractTestAdapter(Protocol):
    """Minimal adapter operations required by the generic contract suite."""

    operation_started: asyncio.Event
    state_publisher: CanonicalStatePublisher

    def mark_ready(self) -> None: ...

    async def execute(self, command: CapabilityCommand) -> CommandResult: ...

    def cancel(self, command_id: str) -> bool: ...

    async def reconcile_after_restart(self) -> RestartReconciliation: ...


class ContractAdapterFactory(Protocol):
    """Build one deterministic adapter configured for the requested contract scenario."""

    def __call__(self, scenario: ContractScenario) -> ContractTestAdapter: ...


@dataclass(frozen=True, slots=True)
class ContractReport:
    """Named result codes from a successful generic contract execution."""

    result_codes: dict[ContractScenario, str]


def sample_command(*, timeout: timedelta = timedelta(milliseconds=50)) -> CapabilityCommand:
    """Create a valid, deterministic-shape command suitable for adapter contract tests."""

    return CapabilityCommand(
        command_id=new_command_id(),
        trace_id=new_trace_id(),
        capability="sdk.test.execute",
        input_payload_json='{"value":"ok"}',
        timeout=timeout,
    )


async def run_adapter_contract_suite(factory: ContractAdapterFactory) -> ContractReport:
    """Run all mandatory generic adapter behavior checks against a scenario factory."""

    results: dict[ContractScenario, CommandResult] = {}

    nominal = factory(ContractScenario.NOMINAL)
    nominal.mark_ready()
    results[ContractScenario.NOMINAL] = await nominal.execute(sample_command())
    assert results[ContractScenario.NOMINAL].success

    invalid = factory(ContractScenario.INVALID_INPUT)
    invalid.mark_ready()
    results[ContractScenario.INVALID_INPUT] = await invalid.execute(sample_command())
    assert results[ContractScenario.INVALID_INPUT].result_code == "sdk.command.invalid_input"
    assert invalid.state_publisher.snapshot.state is DeviceState.READY

    not_ready = factory(ContractScenario.NOT_READY)
    results[ContractScenario.NOT_READY] = await not_ready.execute(sample_command())
    assert results[ContractScenario.NOT_READY].result_code == "sdk.command.not_ready"

    cancellation = factory(ContractScenario.CANCELLATION)
    cancellation.mark_ready()
    cancellation_command = sample_command()
    cancellation_task = asyncio.create_task(cancellation.execute(cancellation_command))
    await asyncio.wait_for(cancellation.operation_started.wait(), timeout=0.2)
    assert cancellation.cancel(cancellation_command.command_id)
    results[ContractScenario.CANCELLATION] = await cancellation_task
    assert results[ContractScenario.CANCELLATION].result_code == "sdk.command.cancelled"
    assert results[ContractScenario.CANCELLATION].outcome_certain

    timeout = factory(ContractScenario.TIMEOUT)
    timeout.mark_ready()
    results[ContractScenario.TIMEOUT] = await timeout.execute(
        sample_command(timeout=timedelta(milliseconds=5))
    )
    assert results[ContractScenario.TIMEOUT].result_code == "sdk.command.timeout"
    assert not results[ContractScenario.TIMEOUT].outcome_certain
    assert timeout.state_publisher.snapshot.state is DeviceState.UNKNOWN

    fault = factory(ContractScenario.FAULT)
    fault.mark_ready()
    results[ContractScenario.FAULT] = await fault.execute(sample_command())
    assert results[ContractScenario.FAULT].result_code == "sdk.test.injected_fault"
    assert fault.state_publisher.snapshot.state is DeviceState.FAULT

    restarted = factory(ContractScenario.RESTART_UNKNOWN)
    reconciliation = await restarted.reconcile_after_restart()
    assert not reconciliation.outcome_certain
    assert restarted.state_publisher.snapshot.state is DeviceState.UNKNOWN
    assert not restarted.state_publisher.snapshot.ready

    return ContractReport(
        result_codes={scenario: result.result_code for scenario, result in results.items()}
    )


class FakeAdapter(BaseDeviceAdapter):
    """Test-only deterministic adapter proving the generic SDK contract suite."""

    def __init__(self, scenario: ContractScenario) -> None:
        super().__init__("00000000-0000-0000-0000-000000000008")
        self.scenario = scenario
        self.operation_started = asyncio.Event()

    async def execute_operation(self, context: OperationContext) -> CommandResult:
        self.operation_started.set()
        if self.scenario in {ContractScenario.CANCELLATION, ContractScenario.TIMEOUT}:
            await context.cancellation.wait()
        if self.scenario is ContractScenario.FAULT:
            raise DeviceOperationFault(
                Fault("sdk.test.injected_fault", "Injected deterministic fault.")
            )
        if self.scenario is ContractScenario.INVALID_INPUT:
            return CommandResult(
                command_id=context.command.command_id,
                trace_id=context.command.trace_id,
                success=False,
                result_code="sdk.command.invalid_input",
                result_message="The fake adapter rejected its test payload.",
            )
        return CommandResult(
            command_id=context.command.command_id,
            trace_id=context.command.trace_id,
            success=True,
            result_code="sdk.command.completed",
            result_message="Completed.",
        )

    async def request_cancellation(self, context: OperationContext) -> CancellationDisposition:
        if self.scenario is ContractScenario.CANCELLATION:
            return CancellationDisposition(True, "Fake adapter confirmed cancellation.")
        return await super().request_cancellation(context)

    async def read_restart_reconciliation(self) -> RestartReconciliation:
        if self.scenario is ContractScenario.RESTART_UNKNOWN:
            return RestartReconciliation(
                state=DeviceState.UNKNOWN,
                ready=False,
                outcome_certain=False,
                details={"source": "fake"},
            )
        return RestartReconciliation(state=DeviceState.READY, ready=True, outcome_certain=True)


def fake_adapter_factory(scenario: ContractScenario) -> FakeAdapter:
    """Build the documented fake adapter for one contract scenario."""

    return FakeAdapter(scenario)
