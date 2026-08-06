# Task 007 ROS interface package

## Goal
Turn the canonical CellForge ROS interface definitions into a buildable ROS 2 Jazzy package, so
runtime packages can use vendor-neutral generated message, service, and action types.

## Scope
Included: copying the 13 canonical definitions into `cellforge_interfaces`, ROSIDL CMake/package
metadata, interface-contract documentation, generated C++ and Python compatibility tests, and a
source/package drift test. Excluded: skill or device implementations, action servers, validation
logic, safety enforcement, vendor/protocol adapters, and all Task 008 work.

## Current state
`ros_interfaces/` contains five messages, three services, and five actions. The Task 001
`cellforge_interfaces` package is an ament placeholder. Tasks 001 through 006 are present in Git;
the clean starting branch was `task/006-cell-compiler` and this task uses
`task/007-ros-interfaces`. The Windows host has Python/uv but not GNU Make, ROS Jazzy, or colcon.
The equivalent untouched Python checks pass: Ruff format/check, mypy, 70 pytest tests, and example
validation.

## Design
Keep `ros_interfaces/` as the canonical design source and copy byte-identical definitions into
the ROS package because ROSIDL generation expects package-local interface paths. A Python test
prevents drift and rejects common vendor-specific terms. CMake generates all interfaces using
`rosidl_default_generators` and declares only generic ROS message dependencies.

Long-running actions expose command IDs, stable result codes/messages, standard ROS action
cancellation, and caller-supplied duration timeouts. `RunJob` gains the missing duration timeout,
in both source and packaged definitions, to meet the runtime timeout contract. Generated-type tests
cover a success result, invalid data remaining unauthorised at the transport boundary, timeout
representation, cancellation protocol availability, and a deterministic failure/outcome-certain
result. Safety state is read-only status; no interface controls safety-rated hardware.

## Work sequence
1. Create package-local `msg`, `srv`, and `action` definitions and synchronize the `RunJob` timeout;
   verify source/package parity with a pure Python test.
2. Configure ROSIDL generation and dependencies; add C++ compile/use and Python import tests.
3. Document interface semantics, compatibility, cancellation, timeout, and safety boundaries.
4. Run focused and repository checks, then inspect the full diff, update this plan, stage Task 007,
   commit, and verify clean Git state.

## Validation
Run `make lint`, `make test`, `make validate-examples`, `make ros-build`, and `make ros-test`.
Where GNU Make/ROS are unavailable, run the exact Python recipes directly with uv and record the
unavailable ROS commands. On Ubuntu Jazzy, expected evidence is a successful
`colcon build --packages-select cellforge_interfaces`, `colcon test`, compiled C++ generated-type
use, and Python imports for every generated type.

## Risks and rollback
Duplicated source definitions could drift; the parity test makes that a deterministic failure.
Adding a timeout field is backward compatible for ROS action goals because it adds a field but
requires clients to populate it intentionally. This task has no running hardware impact and no
safety authority. Revert its single task commit to restore the placeholder package.

## Progress
- [x] 2026-08-06 - Required repository, architecture, runtime, domain, safety, ROS, interface, and
  testing documents read; prerequisites and clean starting state verified.
- [x] 2026-08-06 - Dedicated Task 007 branch created; untouched Python baseline passes.
- [x] 2026-08-06 - ROSIDL package, source/package parity test, and C++/Python compatibility tests implemented.
- [x] 2026-08-06 - Full available validation passes: format/lint/mypy, 73 pytest tests, and example validation.
  Generated C++/Python ROS compatibility tests are present but require a Jazzy host.
- [ ] 2026-08-06 - Task diff inspected, staged, committed, and final Git state verified.

## Decisions
- 2026-08-06 - Keep the existing root definitions canonical and add a parity test rather than
  silently changing them into untracked duplicated inputs.
- 2026-08-06 - Add only generic ROS interfaces and JSON payload fields; vendor protocols and safety
  control remain outside this package.
- 2026-08-06 - Represent ROS action cancellation through the standard action protocol and test its
  availability; execution/cancellation behavior belongs to the Task 008 SDK and action servers.

## Results
Implemented the cellforge_interfaces ROSIDL package with all 13 canonical definitions, generic
ROS dependencies, generated C++ compile/use and Python import tests, interface documentation, and
a source/package drift and vendor-term test. RunJob now carries the missing duration timeout.
The direct Python equivalents of the available Make targets pass with 73 tests. The literal Make
targets are unavailable because GNU Make is absent. ROS Jazzy, colcon, and a usable Bash/WSL
