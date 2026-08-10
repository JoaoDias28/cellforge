# Task 019 — MoveIt and MTC motion service

## Goal
Expose collision-aware pose motion and staged pick/load/unload manipulation through stable
CellForge ROS 2 actions, with plan-only operation, deterministic failures, cancellation, trace
evidence, and a supported reference six-axis robot configuration.

## Scope
Included: planner-neutral motion actions; planning-scene synchronization tied to canonical
`cell.yaml` and USD digests; a C++ application service and MoveIt/MTC adapter; named safe poses;
reference robot URDF/SRDF, kinematics, limits, controllers and OMPL configuration; fake-backend
unit and ROS action tests; and a GPU/hardware-independent headless contract check.

Excluded: Task 020 physical pen simulation, behavior-tree workflow changes, vendor robot drivers,
production qualification, process control, collision geometry generation from USD, and any
functional-safety enforcement or certification claim.

## Current state
Clean `main` at `c26d8dd` contains merged Tasks 007 (`5b3c0e6`) and 008 (`5c75c67`) and all work
through Task 018. Task 007 owns canonical ROS interfaces and Task 008 owns adapter cancellation,
timeout, stable fault, and restart semantics. The reference robot component has only a one-link
placeholder URDF/SRDF, and no `cellforge_motion` package exists. The pre-edit repository-local
baseline passes Ruff, strict mypy, 269 pytest tests, and validation of 5 canonical schemas,
6 component schemas, and 19 YAML examples. GNU Make, ROS 2 Jazzy/colcon, and Isaac Sim 6 are not
installed on this Windows host; hosted Ubuntu/Jazzy CI is authoritative for ROS/MoveIt builds.
GitHub CLI is installed but its saved token is invalid.

## Design
`cellforge_interfaces` gains `MoveToPose`, `ExecuteManipulation`, and `SyncPlanningScene` contracts.
Goals carry stable component/command/trace identities, bounded scaling and timeout, but no planner
plugin names. A target is exactly one named safe pose or stamped Cartesian pose. Manipulation uses
the stable operations `pick`, `load`, and `unload` and supplies object and tool-frame identity.

`cellforge_motion::MotionService` is the application boundary. It validates requests, requires a
synchronized scene, calls an abstract `MotionPlanner` port, enforces caller cancellation/deadlines,
maps backend outcomes to stable `motion.*` codes, and emits deterministic JSON evidence. The real
adapter uses MoveGroupInterface for pose planning/execution and MoveIt Task Constructor for staged
manipulation. The node alone maps ROS messages and publishes canonical `JobEvent` records. A fake
planner drives deterministic nominal, unreachable, collision, timeout, cancellation, execution,
scene, and evidence tests without hardware.

Scene synchronization accepts a MoveIt planning scene only when its revision, SHA-256 identities,
cell ID, and component instance IDs are valid. Collision-object IDs must be immutable component IDs
or their declared child IDs. The adapter applies the scene atomically and records the active
revision. `cell.yaml` remains the operational source and USD remains the spatial source; the motion
service consumes a compiled/synchronized projection and does not invent another canonical scene.

The reference configuration declares `home`, `process_safe`, `load_safe`, and `unload_safe` SRDF
states. OMPL and KDL plugin selections live only in configuration. The fake joint trajectory
controller is for simulation/test execution only and is not a hardware adapter or safety function.

## Work sequence
1. Add the ExecPlan and stable interfaces; acceptance: source and packaged definitions match and
   structural interface tests cover timeout, result, trace, plan-only, and scene identity fields.
2. Replace the placeholder reference kinematic model and add conventional MoveIt configuration;
   acceptance: the headless verifier parses the URDF/SRDF/YAML, checks six bounded joints and all
   named safe poses, and verifies planner names are absent from action goals.
3. Add the application service, fake planner, MoveIt/MTC adapter, node, launch and event mapping;
   acceptance: C++ fake-backend tests cover nominal, invalid, unreachable, collision, timeout,
   cancellation, deterministic replay, trace/evidence, scene rejection, and execution failure.
4. Add ROS action/service integration tests and documentation; acceptance: Jazzy builds and tests
   the node against a fake controller/backend and cancellation reaches the execution request.
5. Run every required local/hosted check, inspect the complete diff, commit, publish, wait for green
   CI, merge, and synchronize `main` without starting Task 020.

## Validation
- `make lint`
- `make test`
- `make validate-examples`
- `make motion-service-check`
- `make ros-build`
- `make ros-test`
- `uv run --frozen pytest --basetemp <repository-local-path>` when GNU Make is unavailable
- Hosted GitHub Actions: Python 3.12 validation and ROS 2 Jazzy build/test

Expected evidence: all pure checks pass locally; all C++/ROS/MoveIt gtests pass on Ubuntu Jazzy;
the plan-only fake-controller path requires no hardware; unavailable Isaac/hardware checks remain
explicitly unavailable and are not acceptance evidence for Task 020.

## Risks and rollback
MoveIt/MTC APIs and binary package names can vary by ROS release; pin to Jazzy package contracts and
let rosdep resolve them. Cancellation is a request: if a real controller cannot prove a stop, the
result remains uncertain and recovery is required. Planning-scene digest mismatch fails closed.
Revert the single Task 019 commit to roll back interfaces, package, configuration and docs together.
No schema migration or breaking change is introduced; interfaces are additive.

## Progress
- [x] 2026-08-10 — prerequisite ancestry, clean repository, architecture review, and baseline checks
  completed; task branch created.
- [x] 2026-08-10 — stable interfaces and reference robot configuration completed; headless
  verifier confirms six bounded joints, four complete safe states, canonical scene identities,
  planner-neutral goals, and fake-controller configuration.
- [x] 2026-08-10 — application service, MoveIt/MTC adapter, node, tests and docs completed; local
  Ruff/mypy, 275-test regression, example validation, Task 018 regression, and Task 019 focused
  checks pass.
- [x] 2026-08-10 — local validation, task-scoped commits, ready PR, and final hosted Python/Jazzy
  validation completed.
- [ ] 2026-08-10 — PR merge and synchronized `main` completed.

## Decisions
- 2026-08-10 — Keep planner and controller plugin names exclusively in MoveIt configuration so
  behavior-tree/task logic depends only on CellForge actions.
- 2026-08-10 — Require both canonical artifact hashes on every scene synchronization; a MoveIt
  scene is a derived runtime projection, never a replacement source of truth.
- 2026-08-10 — Treat cancellation/timeout as standard-control outcomes and never describe them as
  safety-rated stopping behavior.
- 2026-08-10 — Model `pick`/`unload` as object acquisition and `load` as object placement inside the
  MTC builder; gripper and fixture commands remain explicit behavior-tree capabilities.
- 2026-08-10 — Hosted Jazzy run 31415071929 resolved every dependency, then exposed mixed CMake
  link signatures before compilation. Use the plain signature consistently with
  `ament_target_dependencies`; keep the fix limited to Task 019 CMake.
- 2026-08-10 — Hosted Jazzy run 31415869764 passed CMake and exposed the Jazzy
  `MoveGroupInterface::Plan` field names (`trajectory`, `planning_time`). Correct only those four
  member accesses and preserve the same result mapping.
- 2026-08-10 — Hosted Jazzy run 31416588224 built the complete workspace and passed the motion
  gtests and clang-format. Clang-tidy alone rejected aggregate initialization that implicitly
  default-constructed generated ROS messages. Make `PlannerResult` an ordinary value type and use
  typed promise values so GCC and Clang share the same construction semantics.
- 2026-08-10 — Hosted Jazzy run 31417961904 again built the complete workspace; the constructor
  correction compiled in the service, while clang-tidy found four adapter call sites still passing
  an anonymous `{}` to the generated message's explicit constructor. Use an explicit
  `RobotTrajectory()` at those sites without changing outcome mapping.
- 2026-08-10 — Hosted Jazzy run 31419075147 compiled all corrections and passed every C++ gtest and
  clang-format check. The motion clang-tidy process emitted no errors but reached CTest's default
  300-second limit; the existing supervisor lint took 272 seconds on the same runner. Use a
  package-local 600-second ament clang-tidy timeout so the required analysis can finish.
- 2026-08-10 — Hosted Jazzy run 31420390501 confirmed the 600-second timeout and completed lint in
  296 seconds. It exposed the last two anonymous trajectory placeholders in the asynchronous
  exception path; make those generated-message values explicit as well.
- 2026-08-10 — Hosted Jazzy run 31421542948 confirmed every generated-message constructor now
  compiles and exposed the repository-wide clang-tidy profile's source-quality findings. Preserve
  that profile and correct the Task 019 sources rather than weakening or bypassing lint checks.

## Results
The additive interfaces, six-axis reference configuration, pure application boundary, MoveIt pose
adapter, staged MTC builder, ROS node/events, fake-controller launch, deterministic evidence, docs,
and tests are implemented. Local Python/configuration validation passes. PR #15 is ready and Python
CI is green. Hosted ROS runs drove scoped CMake signature, Jazzy Plan-field, generated-message
construction, lint-timeout, and repository clang-tidy-profile corrections. Run 31422971739 passes
Python validation and the complete ROS 2 Jazzy build/test job, including motion gtests,
clang-format, and clang-tidy. Isaac Sim remains unavailable.
