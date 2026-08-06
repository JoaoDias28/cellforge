# cellforge_device_sdk

`cellforge_device_sdk` provides common lifecycle and result semantics for CellForge device
adapters and skills. It is an `ament_python` package for ROS 2 Jazzy. Its execution core has no
ROS, vendor-SDK, or safety-control import, so contract behavior remains deterministic in unit tests;
`RosDeviceStatePublisher` is the narrow edge that converts a canonical snapshot to the generated
`cellforge_interfaces/msg/DeviceState` message.

## Lifecycle and readiness

An adapter starts `UNKNOWN`, publishes `CONNECTING` while it checks the device, and calls
`mark_ready()` only after its own connection and readiness checks pass. Commands are rejected with
`sdk.command.not_ready` before the adapter is ready and `sdk.command.busy` while another command is
active. The adapter publishes `BUSY` with the command ID while an operation runs and emits a
monotonically revisioned canonical snapshot on each transition.

Callers provide a UUID command ID, UUID trace ID, capability ID, JSON-object input, and positive
timeout through `CapabilityCommand`. Result codes and fault codes are stable, dot-separated
application data; vendor error numbers belong only in diagnostic details. `Fault` and
`CommandResult` deliberately carry no raw exception text.

## Cancellation, timeout, and uncertainty

Long operations receive an `OperationContext` with a cooperative `CancellationToken`. A caller uses
`adapter.cancel(command_id)`; the adapter must forward that request in `request_cancellation()`. It
may return `sdk.command.cancelled` only if it can prove the operation was stopped. If not, the SDK
returns `sdk.command.cancelled_uncertain`, marks the state `UNKNOWN`, and blocks new work.

Timeouts always produce `sdk.command.timeout` with `outcome_certain=false` and the same
`UNKNOWN`/not-ready state. Unexpected exceptions and mismatched command/trace IDs use the same
conservative outcome. The SDK never retries or replays an uncertain command.

After a process restart, adapters must implement `read_restart_reconciliation()`. A reconciliation
that cannot prove the prior physical outcome remains `UNKNOWN` and not ready. A supervisor must
enter explicit recovery rather than infer that a process completed or failed.

## Functional-safety boundary

This SDK can display read-only safety status and reject normal operations based on an adapter's
declared preconditions, but it neither implements nor bypasses safety-rated protective functions.
Emergency stops, guard locking, laser enables, and safe stops remain independent rated hardware.

## Contract suite

Use `run_adapter_contract_suite()` with a scenario factory in every simulation and hardware adapter
test package. It verifies nominal execution, invalid input, not-ready rejection, cancellation,
timeout, stable fault mapping, and uncertain restart state. `FakeAdapter` and
`fake_adapter_factory` are a deterministic test-only example; their passing suite is not hardware
or functional-safety evidence.

```python
import asyncio

from cellforge_device_sdk.contract import fake_adapter_factory, run_adapter_contract_suite

report = asyncio.run(run_adapter_contract_suite(fake_adapter_factory))
assert report.result_codes["fault"] == "sdk.test.injected_fault"
```
