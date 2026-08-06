# cellforge_interfaces

`cellforge_interfaces` is the vendor-neutral ROS 2 Jazzy contract package shared by CellForge
runtime nodes. It generates five messages, three short services, and five actions from the
definitions in this package.

## Source definitions

The repository-root `ros_interfaces/` directory remains the canonical design source. The package
copies are intentionally byte-identical so ROSIDL can generate package-local types. The pure
Python `tests/test_ros_interface_definitions.py` test fails if either source drifts or a common
vendor/protocol-specific term appears in an interface definition.

## Contract semantics

- `DeviceState`, `CellState`, `SafetyState`, and `JobEvent` publish canonical state and
  traceability. `SafetyState` is read-only status; it cannot command or bypass functional safety.
- `GetDeviceState`, `SetDiscreteOutput`, and `ValidateRecipe` are short deterministic operations.
  A response result code is stable application data, not a vendor error number.
- All actions are long-running operations. They expose feedback, stable `success`/`result_code`/
  `result_message` result fields, standard ROS action cancellation, and caller-supplied timeouts.
  Action servers validate input, reject unsafe or not-ready commands, enforce/observe timeouts,
  and map failures to deterministic result codes; generated types alone do not authorize work.
- `ExecuteProcess.outcome_certain` is false after communication uncertainty. Consumers must enter
  recovery and must not infer that a hazardous process either completed or failed.
- JSON fields carry versioned, capability-level payloads when a compact extensibility boundary is
  needed. They must not carry vendor control protocols or allow arbitrary safety overrides.

## Build and test

On Ubuntu 24.04 with ROS 2 Jazzy installed:

```bash
cd ros_ws
colcon build --packages-select cellforge_interfaces
colcon test --packages-select cellforge_interfaces --return-code-on-test-failure
colcon test-result --verbose
```

The package test suite compiles and uses all generated C++ types, imports every generated Python
type, and exercises success, invalid-input transport, timeout, cancellation-protocol, and
deterministic-failure representations. It is an interface compatibility check, not device,
hardware, or functional-safety validation.
