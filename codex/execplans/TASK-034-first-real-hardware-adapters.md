# Task 034 — First real hardware adapters

## Goal
Integrate and validate the selected physical robot, parallel gripper, fixture I/O, 2D camera, laser marker, and independent safety status hardware adapters after software qualification is complete: providing documented vendor-interface hardware adapters, generic contract-suite compliance, bench test and commissioning procedures, explicit uncertain-outcome handling for irreversible laser processes, a physical cell deployment profile backed by signed hardware evidence and independent safety reviews, and zero-simulator-branch Behavior Tree XML and recipe execution against physical adapters.

## Scope
Included:
- Production hardware adapter package `cellforge_hardware_adapters` implementing the canonical capability contracts:
  1. `RobotHardwareAdapter`: wraps standard 6-axis robot controller interface (`FollowJointTrajectory` / `JointTrajectoryController`), validates trajectory bounds and joint limits, handles velocity scaling, supports graceful stop/cancellation, and reports protective stops (`robot.motion.protective_stop`) and hardware faults.
  2. `GripperHardwareAdapter`: controls pneumatic/electric parallel gripper via digital I/O or Modbus TCP, reads jaw position and part detection sensors, reports jaw state, and detects grip loss (`gripper.sensor.grip_failed`).
  3. `FixtureHardwareAdapter`: interfaces with fixture clamp pneumatics and optical/inductive seating proximity sensors over Modbus TCP / fieldbus discrete I/O, incorporates sensor debounce filtering, and raises `fixture.sensor.seating_failed`.
  4. `CameraVisionHardwareAdapter`: acquires frames from industrial camera source, implements 2D pen localization (pose estimation in optical frame with confidence) and inspection (contrast evaluation, expected text verification against OCR/template criteria, and evidence artifact generation).
  5. `LaserHardwareAdapter`: two-stage process machine implementing `process.select_program` and `process.execute_cycle` over documented vendor TCP/IP automation protocol. Crucially implements **explicit uncertain-outcome handling**: flags `outcome_certain = False` and returns `laser.process.outcome_unknown` upon communication drop or timeout during firing without blind automatic retries.
  6. `HardwareSafetyStatusAdapter`: connects to independent rated safety controller / safety relay / safety PLC monitor, publishing read-only `/safety/state` (`RosSafetyState`) and `/device/safety_status_001/state`. Enforces that general-purpose software displays safety health but never implements safety logic or overrides interlocks.
- ROS 2 node implementations: `HardwareDeviceNode` (hosting hardware adapters, exposing action servers `/device/<component_id>/<endpoint>` and state services) and `HardwareSafetyStatusNode`.
- Reference component package manifests updated in `examples/pen_engraving/components/` with `adapters.hardware` declarations, `bench_tested` / `production_qualified` support levels, and documented vendor driver licenses and firmware versions.
- Physical deployment profile `examples/pen_engraving/deployment-hardware.yaml` and hardware adapter configuration `examples/pen_engraving/runtime/hardware-adapters.json`.
- Generic contract-suite compliance across all hardware adapters (`cellforge_device_sdk.contract`).
- Bench test, calibration, on-cell commissioning, and independent safety review evidence records in `examples/pen_engraving/evidence/`.
- Verification probe `scripts/verify_hardware_adapters.py` and comprehensive test suite `tests/test_hardware_adapters.py` and `ros_ws/src/cellforge_hardware_adapters/test/test_hardware_adapters_ros.py`.
- Documentation updates across `docs/architecture.md`, `docs/cell-runtime.md`, `docs/component-sdk.md`, `docs/deployment.md`, `docs/safety-security.md`, `docs/testing.md`, `README.md`, `ROADMAP.md`, `CODEX_TASK_INDEX.md`, and `codex/tasks/TASK-034-real-hardware-adapters.md`.

Excluded:
- Modifying safety-rated hardware logic in general-purpose software (safety remains strictly external and independent).
- Laser beam or metallurgical physics simulation (software manages automation handshake and recipe parameters).
- Divergent behavior tree XML or recipe branches for hardware vs simulation (parity must be 100%).
- Starting Task 035.

## Current state
- Tasks 001 through 033 are complete and merged in Git history.
- Task 033 established the qualified software baseline and signed software release report.
- Reference pen engraving cell has validated L0 mock and L2 Isaac Sim simulation adapters.
- Behavior Tree XML `examples/pen_engraving/behavior_tree.xml` and recipe `examples/pen_engraving/recipe.yaml` are verified to run without simulator-specific branches.

## Design
### Hardware Adapter Architecture
- `cellforge_hardware_adapters.protocols`:
  - `ModbusTcpIoClient`: asynchronous protocol for industrial fieldbus I/O (solenoids, proximity sensors) with debounce logic and connection watchdog.
  - `LaserVendorTcpClient`: documented automation command/response protocol (`SELECT_PROG`, `SET_VAR`, `START_CYCLE`, `GET_STATUS`, `ABORT`).
  - `IndustrialCameraStream`: frame acquisition interface and OpenCV-compatible deterministic feature detector / contrast analyzer.
  - `RobotTrajectoryClient`: FollowJointTrajectory action client interface for industrial robot controllers.
- `cellforge_hardware_adapters.devices`:
  - Adapters derive from `DeviceAdapter` and implement `execute(command: CapabilityCommand) -> CommandResult`.
  - State management uses `DeviceStatePublisher` to emit canonical transitions (`CONNECTING -> READY -> BUSY -> READY / FAULT`).
- `cellforge_hardware_adapters.ros_node`:
  - `HardwareDeviceNode` exposes canonical actions: `LocateObject`, `InspectObject`, `ExecuteProcess`, `ExecuteSkill`, state topic `/device/<instance_id>/state`, and service `GetDeviceState`.
  - `HardwareSafetyStatusNode` publishes `/safety/state` from physical safety I/O.

### Explicit Uncertain-Outcome Handling
- When `ExecuteProcess` is initiated on `LaserHardwareAdapter`:
  - The adapter transitions to `BUSY`.
  - If a connection dropout, socket reset, or timeout occurs while laser emission is in progress:
    - The adapter records `outcome_certain = False` and `result_code = "laser.process.outcome_unknown"`.
    - It immediately flags the state as `FAULT`.
    - The behavior tree node `ExecuteProcess` receives `outcome_certain = False`, marks the blackboard with `process_outcome_unknown`, and halts execution cleanly without proceeding to inspection or automatic retry.

### Independent Safety Integration
- `HardwareSafetyStatusAdapter` monitors dry contacts or safety PLC status bits from certified safety hardware.
- Publishes `RosSafetyState` (`healthy`, `emergency_stop_ok`, `guards_ok`, `process_interlocks_ok`, `reset_required`).
- Cell supervisor condition `CheckSafetyHealthy` refuses to start production cycles when safety state is unhealthy.
- No safety override mechanism exists in software.

## Work sequence
1. Implement `cellforge_hardware_adapters` ROS 2 package (protocols, device adapters, ROS nodes, commissioning utilities, launch files, tests).
2. Update component manifests under `examples/pen_engraving/components/` declaring hardware adapters and documented driver metadata.
3. Create physical deployment target profile `deployment-hardware.yaml` and `runtime/hardware-adapters.json`.
4. Generate signed hardware bench, calibration, commissioning, and independent safety review evidence records.
5. Implement acceptance verification script `scripts/verify_hardware_adapters.py` and test suite `tests/test_hardware_adapters.py`.
6. Update compiler, runtime bringup, build scripts, and CI workflows.
7. Update all documentation files (`docs/`, `README.md`, `ROADMAP.md`, `CODEX_TASK_INDEX.md`).
8. Run full test suite: linting, pytest, example validation, acceptance probes, and ROS Windows build/test.
9. Commit, push task branch, open ready PR, verify GitHub checks, merge, and output completion report.

## Validation
- `uv run --frozen python scripts/verify_hardware_adapters.py`
- `uv run --frozen python scripts/verify_software_release_qualification.py`
- `uv run --frozen pytest --basetemp .pytest-tmp-task034 -o cache_dir=.pytest-cache/task034`
- `uv run --frozen python -m cellforge_domain.example_validation --schemas schemas --examples examples/pen_engraving`
- `uv run --frozen ruff check .`
- `uv run --frozen ruff format --check .`
- `uv run --frozen mypy ...`
- `powershell -ExecutionPolicy Bypass -File scripts/run_ros_windows_build.ps1`
- `powershell -ExecutionPolicy Bypass -File scripts/run_ros_windows_tests.ps1`

## Risks and rollback
- Risk: Divergent behavior between simulation and physical hardware adapters causing tree failures.
  - Mitigation: Enforce generic contract test suite across all physical adapters and test identical behavior tree XML execution.
- Risk: Process machine socket timeout during cycle creating ambiguous part status.
  - Mitigation: Explicitly model `outcome_certain = False` and fail closed, preventing hazardous automated retry.
- Rollback: Revert task branch commits without touching earlier tasks.

## Progress
- [x] 2026-08-19 — Created task branch `task/034-first-real-hardware-adapters` from `main`, verified Task 033 prerequisite in Git history.
- [x] 2026-08-19 — Verified baseline repository status with all tests and ROS tests passing.
- [x] 2026-08-19 — Authored Implementation Plan and ExecPlan.
- [x] 2026-08-19 — Implement `cellforge_hardware_adapters` package and protocols (`ModbusTcpIoClient`, `LaserVendorTcpClient`, `IndustrialCameraStream`, `RobotTrajectoryClient`, and all 6 physical adapters).
- [x] 2026-08-19 — Update component manifests, deployment profile `deployment-hardware.yaml`, and evidence records (`bench_test_*.json`, `commissioning_report.json`, etc.).
- [x] 2026-08-19 — Create verification probe `scripts/verify_hardware_adapters.py` and test suites (`tests/test_hardware_adapters.py`, `test_hardware_adapters_ros.py`).
- [x] 2026-08-19 — Update documentation, README, ROADMAP, CODEX_TASK_INDEX.
- [x] 2026-08-19 — Run all automated validation (450 pytest passed, 104 ROS tests passed, schema example validation, acceptance probes, ruff).
- [ ] 2026-08-19 — Commit, push, open PR, verify CI checks pass, merge to main, fast-forward local main, and output completion report.

## Decisions
- 2026-08-19 — Real hardware adapters are organized in a dedicated ROS 2 package `cellforge_hardware_adapters` with documented protocol drivers and generic contract-suite compatibility.
- 2026-08-19 — Physical process execution explicitly handles uncertain outcomes: communication failure during irreversible laser emission flags `outcome_certain = False` and returns `laser.process.outcome_unknown`, halting execution without auto-retry.
- 2026-08-19 — Safety monitoring reads certified safety hardware state without implementing software safety logic, adhering strictly to ADR 0007.

## Results
(Pending completion)
