# Task 009 Contract mock adapters

## Goal
Provide L0 contract mocks for robot motion, gripper, fixture, vision locator, process machine, and
inspection so behavior-tree, scenario, and supervisor work can be developed and tested without
Isaac Sim or hardware. Every mock speaks the canonical ROS contracts, runs the generic adapter
contract suite, selects faults from scenario configuration, and publishes coherent canonical state
transitions before reporting completion.

## Scope
Included: a new `cellforge_mock_adapters` ament-Python package with a pure deterministic core
(scenario parsing/validation, configurable timing, six device mock adapters on the Task 008 SDK),
contract-suite factories, an `rclpy` node edge, a complete mock-cell launch file and scenario
configuration, repo-level deterministic tests, a Jazzy-only colcon smoke test, and documentation.
Excluded: physics/geometry simulation (L1+), a safety-status adapter, behavior-tree supervision
(Task 011), scenario orchestration (Task 018), hardware adapters, and any safety-rated function.

## Current state
Task 008 provides `cellforge_device_sdk` with `BaseDeviceAdapter` (readiness, BUSY/READY/FAULT/
UNKNOWN transitions, timeout, cooperative cancellation, restart reconciliation) and the generic
`run_adapter_contract_suite` with `ContractScenario` factories. Task 007 provides
`cellforge_interfaces` (`ExecuteSkill`, `ExecuteProcess`, `LocateObject`, `InspectObject`,
`DeviceState`, `GetDeviceState`). The pen-engraving example cell declares instances robot-001,
gripper-001, laser-001, camera-001, fixture-001 and requires ten capabilities. Robot and laser
fault catalogs exist under `examples/pen_engraving/components/*/docs/faults.md`. This Windows host
has Python 3.12/uv but no GNU Make, ROS Jazzy, or colcon. Pre-existing baseline: 76 pytest tests
pass; `test_packaged_interfaces_match_canonical_source_definitions` fails because
`core.autocrlf=true` checks packaged interface files out as CRLF while canonical sources stay LF
(byte-parity test artifact; index content is identical LF). With the default TEMP, 26 tests error
on a pytest temp-directory permission problem; redirecting TEMP/TMP to a writable directory
avoids that environment issue. Ruff format/check, mypy, and example validation pass.

## Design
One configurable engine, six thin device mocks:

- `scenarios.py` parses and strictly validates a JSON-compatible scenario document per device:
  declared device kind, component instance ID, per-capability operation behavior
  (`duration_seconds` > 0, optional catalog `fault`), restart reconciliation (`ready` or
  `uncertain`), and device-specific deterministic data (jaw state, clamp/seating, object pose,
  known programs, interlock-permitted status, inspection measurements). Unknown keys, unknown
  capabilities, non-positive durations, and fault codes outside the device catalog (plus the
  documented SDK test hook `sdk.test.injected_fault`) are rejected with structured errors.
- `core.py` holds `MockDeviceAdapter(BaseDeviceAdapter)`: validates capability membership and
  payload (`sdk.command.invalid_input`), waits the configured duration, raises
  `DeviceOperationFault` for injected catalog faults, supports the device-reported uncertainty
  code (`laser.process.outcome_unknown`) as an explicit `outcome_certain=False` result, and
  confirms cancellation as certain because a virtual timer provably leaves no physical state.
  All completion paths flow through the SDK base, so BUSY precedes READY/FAULT/UNKNOWN and no
  success is reported without the published transition sequence.
- `devices.py` defines the six mocks with canonical capabilities and fault catalogs: robot
  (`robot.motion.*`, `robot.communication.lost` per the component catalog), gripper, fixture
  (`fixture.sensor.seating_failed` per the SDK doc), vision locator (`camera.*`, `vision.*`),
  process machine (exact laser catalog codes, two-stage select-program then execute-cycle per
  `docs/component-sdk.md` §8), and inspection. Success results carry deterministic
  config/payload-derived output JSON (never empty placeholders).
- `ros_node.py` is the thin Jazzy-only edge: parameters select the node name/instance/scenario
  file; it publishes canonical `DeviceState`, serves canonical actions (`ExecuteSkill` for
  robot/gripper/fixture/program selection, `ExecuteProcess` for cycles, `LocateObject`,
  `InspectObject`) and `GetDeviceState`, forwards cancellation and goal timeouts, and refuses to
  become ready on invalid scenario configuration. Scenario files are JSON so the node needs no
  dependency beyond rclpy and the workspace packages.
- `launch/mock_cell.launch.py` starts six nodes (mock_robot, mock_gripper, mock_fixture,
  mock_vision_locator, mock_inspection, mock_laser) bound to `config/mock_cell_scenarios.json`;
  the vision locator and inspection nodes share component instance camera-001 because the
  reference cell puts both vision capabilities on one camera.
- Contract factories map each `ContractScenario` onto mock configuration, using the documented
  `sdk.test.execute` test-hook capability so the generic suite drives device-independent cases.

Safety boundary: mocks only consume configured safety *status* (for example laser
interlock-permitted) and refuse operation with catalog faults; they implement no safety function.

## Work sequence
1. Add this ExecPlan; record baseline evidence (done above).
2. Implement `scenarios.py` with strict validation and device catalogs.
3. Implement `core.py` and `devices.py` with the six mocks and contract factories.
4. Implement `ros_node.py`, `launch/mock_cell.launch.py`, and
   `config/mock_cell_scenarios.json`; add package metadata and README.
5. Add repo-level tests: generic suite for all six mocks, invalid configuration, unsupported
   fault rejection, configured device faults, timeout, cancellation, state-ordering, repeated
   determinism, non-empty success outputs, process two-stage behavior, and launch/config
   validation against `examples/pen_engraving/cell.yaml`.
6. Add the Jazzy-only colcon smoke test; update the Makefile mypy path and mypy overrides.
7. Run available checks, update this plan, inspect the diff, commit only Task 009.

## Validation
- `uv sync --locked --all-packages`
- `uv run --frozen ruff format --check .` and `uv run --frozen ruff check .`
- `uv run --frozen mypy <same paths as Makefile lint>`
- `uv run --frozen pytest` (with TEMP/TMP redirected to a writable directory on this host)
- `uv run --frozen python -m cellforge_domain.example_validation --schemas schemas --examples examples/pen_engraving`
- Unavailable here (exact commands for an Ubuntu 24.04 + ROS 2 Jazzy host):
  `make lint`, `make test`, `make validate-examples`, `make ros-build`, `make ros-test`;
  package-level: `cd ros_ws && colcon test --packages-select cellforge_mock_adapters --return-code-on-test-failure`.

## Risks and rollback
The main risk is a mock implying physical completion; the design routes every outcome through the
SDK uncertainty rules, uses catalog fault codes, and documents L0 fidelity limits (timing and
interface behavior only; no geometry, physics, or process-quality evidence). ROS node code cannot
execute on this host, so it is kept thin and covered by a colcon smoke test on Jazzy plus
deterministic repo-level launch/configuration validation. Reverting the Task 009 commit removes
the package and tests without touching Tasks 001-008 artifacts.

## Progress
- [x] 2026-08-07 - Required docs, Tasks 001-008 implementation, and Git history reviewed;
  prerequisites verified; branch `task/009-mock-adapters` created; baseline checks recorded.

## Decisions
- 2026-08-07 - One configurable mock engine with six device wrappers instead of six diverging
  implementations, so contract behavior stays uniform and device differences live in validated
  scenario data.
- 2026-08-07 - Scenario files are JSON (stdlib only at the ROS edge); PyYAML remains a dev-only
  dependency used by repo tests for `cell.yaml` cross-checks.
- 2026-08-07 - The generic suite's `sdk.test.execute` capability and `sdk.test.injected_fault`
  code are supported as an explicit, documented test hook in every mock; all other fault codes
  must come from the device catalog, and unsupported codes are rejected at configuration time.

## Results
Implemented the `cellforge_mock_adapters` ament-Python package containing a pure deterministic
core (scenario parsing with strict validation, configurable timing, fault injection engine),
six L0 device mocks (robot motion, gripper, fixture, vision locator, process machine,
inspection) each with canonical capabilities, device fault catalogs, and contract-suite
factories; the `rclpy` node edge; a complete mock-cell launch file and scenario configuration
matching the pen-engraving reference cell; 11 deterministic repo-level tests covering the
generic contract suite, invalid config, unsupported faults, configured device faults, timeout,
cancellation, state-transition ordering, repeated determinism, non-empty outputs, process
two-stage and interlock behaviour, and launch/config validation against `cell.yaml` and
`recipe.yaml`; a Jazzy-only colcon smoke test; package README and a short docs/simulation.md
section.

Full available suite: ruff format/check clean, mypy strict in 43 source files, 87 pytest tests
passed (11 new, 76 existing, 1 pre-existing CRLF parity failure), example validation passed.
GNU Make, ROS 2 Jazzy, and colcon are unavailable; the exact commands for the Jazzy environment
are recorded below.

## Progress
- [x] 2026-08-07 - Required docs, Tasks 001-008 implementation, and Git history reviewed;
  prerequisites verified; branch `task/009-mock-adapters` created; baseline checks recorded.
- [x] 2026-08-07 - Implemented the pure core (scenarios, engine, six mocks, factories).
- [x] 2026-08-07 - Implemented ROS node, launch file, scenario configuration, package metadata, README.
- [x] 2026-08-07 - Implemented 11 deterministic tests covering all required scenarios.
- [x] 2026-08-07 - All available checks pass (ruff, mypy, 87 pytest, validate-examples).
  Unavailable: `make lint`, `make test`, `make validate-examples`, `make ros-build`, `make ros-test`;
  `colcon test --packages-select cellforge_mock_adapters` on a Jazzy host.
