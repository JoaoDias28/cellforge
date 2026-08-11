"""Contract and pure-unit tests for the Task 008 device and skill SDK."""

from __future__ import annotations

import asyncio
import sys
from datetime import timedelta
from pathlib import Path

import pytest

SDK_ROOT = Path(__file__).resolve().parents[1] / "ros_ws" / "src" / "cellforge_device_sdk"
sys.path.insert(0, str(SDK_ROOT))

from cellforge_device_sdk.contract import (  # noqa: E402
    ContractScenario,
    fake_adapter_factory,
    run_adapter_contract_suite,
    sample_command,
)
from cellforge_device_sdk.ids import new_command_id, new_trace_id  # noqa: E402
from cellforge_device_sdk.models import (  # noqa: E402
    CapabilityCommand,
    DeviceState,
    DeviceStateSnapshot,
    Fault,
)
from cellforge_device_sdk.state import CanonicalStatePublisher  # noqa: E402


def test_sample_fake_adapter_passes_generic_contract_suite() -> None:
    """The documented fake adapter exercises every required adapter contract case."""

    report = asyncio.run(run_adapter_contract_suite(fake_adapter_factory))

    assert report.result_codes == {
        ContractScenario.NOMINAL: "sdk.command.completed",
        ContractScenario.INVALID_INPUT: "sdk.command.invalid_input",
        ContractScenario.NOT_READY: "sdk.command.not_ready",
        ContractScenario.CANCELLATION: "sdk.command.cancelled",
        ContractScenario.TIMEOUT: "sdk.command.timeout",
        ContractScenario.FAULT: "sdk.test.injected_fault",
    }


def test_invalid_command_input_is_rejected_before_adapter_operation() -> None:
    """Malformed command identity, payload, and deadline cannot become executable work."""

    with pytest.raises(ValueError, match="command_id"):
        CapabilityCommand(
            command_id="not-a-uuid",
            trace_id=new_trace_id(),
            capability="sdk.test.execute",
            input_payload_json="{}",
            timeout=timedelta(seconds=1),
        )
    with pytest.raises(ValueError, match="JSON object"):
        CapabilityCommand(
            command_id=new_command_id(),
            trace_id=new_trace_id(),
            capability="sdk.test.execute",
            input_payload_json="[]",
            timeout=timedelta(seconds=1),
        )
    with pytest.raises(ValueError, match="positive"):
        CapabilityCommand(
            command_id=new_command_id(),
            trace_id=new_trace_id(),
            capability="sdk.test.execute",
            input_payload_json="{}",
            timeout=timedelta(0),
        )


def test_state_publisher_is_canonical_monotonic_and_retains_uncertain_command() -> None:
    """State publication makes uncertainty and the command needing recovery observable."""

    emitted: list[DeviceStateSnapshot] = []
    publisher = CanonicalStatePublisher("component-008", emitted.append)

    ready = publisher.transition(DeviceState.READY, details={"source": "test"})
    uncertain = publisher.mark_uncertain(new_command_id(), details={"reason": "lost_link"})

    assert ready.revision == 1
    assert uncertain.revision == 2
    assert uncertain.state is DeviceState.UNKNOWN
    assert not uncertain.ready
    assert uncertain.last_uncertain_command_id is not None
    assert uncertain.fault == Fault(
        code="sdk.communication.outcome_unknown",
        message="Command outcome is unknown; reconcile hardware before continuing.",
    )
    assert [snapshot.revision for snapshot in emitted] == [1, 2]


def test_state_heartbeat_refreshes_time_without_changing_semantic_state() -> None:
    emitted: list[DeviceStateSnapshot] = []
    publisher = CanonicalStatePublisher("component-008", emitted.append)
    ready = publisher.transition(DeviceState.READY, details={"source": "test"})

    heartbeat = publisher.heartbeat()

    assert heartbeat.revision == ready.revision + 1
    assert heartbeat.heartbeat_at >= ready.heartbeat_at
    assert heartbeat.state is ready.state
    assert heartbeat.ready is ready.ready
    assert heartbeat.details == ready.details
    assert emitted[-1] == heartbeat


def test_not_ready_adapter_rejects_without_starting_operation() -> None:
    """Readiness is an explicit precondition, not an assumption based on process startup."""

    adapter = fake_adapter_factory(ContractScenario.NOT_READY)
    result = asyncio.run(adapter.execute(sample_command()))

    assert result.result_code == "sdk.command.not_ready"
    assert adapter.state_publisher.snapshot.state is DeviceState.UNKNOWN
    assert not adapter.operation_started.is_set()
