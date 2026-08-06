# Task 008 Device and skill SDK

## Goal
Provide a reusable, vendor-neutral Python ROS 2 adapter SDK that publishes canonical state,
propagates command and trace identity, returns deterministic results and faults, and makes timeout,
cancellation, and restart uncertainty explicit.

## Scope
Included: the `cellforge_device_sdk` ament-Python package; pure state, ID, result, fault,
timeout/cancellation, restart-reconciliation, and ROS-message publishing helpers; a generic adapter
contract harness; a fake adapter demonstrating that harness; SDK lifecycle documentation; and unit
tests. Excluded: vendor protocols, real hardware I/O, behavior-tree supervisor logic, safety-rated
control, state aggregation, and Task 009 mock-adapter packages.

## Current state
Task 007 provides the canonical `cellforge_interfaces` package and action/message definitions.
The SDK package is implemented. The workstation has Python and uv, but no GNU Make, ROS Jazzy installation, colcon, or hardware. The task branch is `task/007-ros-interfaces` with a clean worktree;
Task 007 is commit `5b3c0e6`.

## Design
The SDK stays below skills and vendor adapters while preserving pure-domain boundaries: its core
uses only Python standard-library types and does not import CellForge domain, vendor, safety, or
ROS packages. `CanonicalStatePublisher` retains a monotonic state revision and can publish a
canonical snapshot to an injected sink; the optional ROS conversion imports generated interfaces
only at the publishing edge. Command and trace identifiers are validated UUID values.

`BaseDeviceAdapter` validates readiness and input before starting an operation, enforces its
caller-supplied deadline, exposes cooperative cancellation, maps declared `DeviceOperationFault`
instances to stable fault/result codes, and treats timeouts, unknown exceptions, and incomplete
restart reconciliation as uncertain outcomes. An uncertain command blocks readiness and is never
replayed automatically. Safety remains read-only external status and is not controlled by this SDK.

The generic contract harness executes nominal, invalid-input, not-ready, cancellation, timeout,
fault-mapping, and restart-uncertainty cases against a factory. A deterministic fake is test-only
evidence, not a hardware or functional-safety validation.

## Work sequence
1. Add the Task 008 ExecPlan and record the clean prerequisite/baseline evidence.
2. Implement the ament-Python SDK core and ROS publishing edge; document lifecycle/readiness and
   uncertainty behavior.
3. Add the reusable contract harness, fake adapter, and focused tests for every required scenario.
4. Run direct Python equivalents and all available repository checks; inspect the diff; update this
   plan with results; stage and commit only Task 008.

## Validation
Run `make lint`, `make test`, `make validate-examples`, `make ros-build`, and `make ros-test`.
When Make/ROS are unavailable, run `uv sync --locked --all-packages`, Ruff format/check, mypy,
pytest, and example validation directly. Run focused SDK tests and, on a Jazzy host, build/test the
whole workspace with colcon. Expected evidence includes the fake adapter passing the generic suite
and separate tests for all required result paths.

## Risks and rollback
The main risk is falsely treating a command as completed after loss of communication. Timeout,
unexpected failure, and incomplete restart reconciliation deliberately result in `outcome_certain`
being false and a non-ready state. This SDK has no authority over independent functional safety or
physical I/O. Reverting the Task 008 commit removes the new package and tests without changing the
Task 007 interfaces.

## Progress
- [x] 2026-08-06 - Required repository, Task 007, runtime, domain, safety, interface, SDK, and
  testing documentation read; clean Task 007 prerequisite and current branch verified.
- [x] 2026-08-06 - Pre-edit Make targets attempted; unavailable because GNU Make is not installed.
- [x] 2026-08-06 - Implemented and unit-tested the SDK, generic contract suite, and documented fake adapter.
- [x] 2026-08-06 - Direct Python validation passed: Ruff, mypy, 77 pytest tests, and example validation; ROS checks remain unavailable pending Jazzy/colcon.

## Decisions
- 2026-08-06 - Put deterministic adapter behavior in a pure Python core so it is unit-testable
  without ROS or hardware; keep generated ROS message conversion at a narrow optional edge.
- 2026-08-06 - Timeouts and unrecognised failures always preserve uncertainty rather than implying
  that a physical command failed or completed.

## Results
Implemented the `cellforge_device_sdk` ament-Python package with canonical state publication,
validated command/trace UUIDs, stable result/fault values, cooperative cancellation, timeout and
restart reconciliation semantics, and the narrow generated-ROS state conversion edge. The generic
contract harness and fake adapter pass nominal, invalid-input, not-ready, cancellation, timeout,
fault-mapping, and restart-uncertainty coverage. The full available Python suite passes (77 tests),
as do Ruff, mypy, and example validation. GNU Make, ROS Jazzy, and colcon are unavailable locally,
so ROS build/test and actual generated-message publishing remain unexecuted.
