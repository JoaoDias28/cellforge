# Task 018 — Isaac simulation bridge and scenario control

## Goal
Provide deterministic start, reset, pause, step, scenario setup, simulated-adapter registration,
fault injection, trace assertion, and evidence capture services that Cell Studio and headless ROS 2
clients can use with Isaac Sim 6. The implementation must make fidelity limits explicit and keep
functional safety outside CellForge software.

## Scope
Included: an adapter-neutral pure simulation application service; strict scenario and control
models; deterministic bounded randomization; canonical component/capability adapter registration;
fault scheduling; trace collection and assertion evaluation; atomic JSON evidence; thin ROS 2
services/node and Isaac Sim 6 timeline/physics backend; a Studio simulation panel; a GPU-independent
headless acceptance probe; ROS and Kit integration probes; documentation and tests.

Excluded: MoveIt/MTC (Task 019), physical pen manipulation and process-quality simulation (Task
020), production control, hardware drivers, safety enforcement/certification, and any claim that an
L0/L1 result proves L2 physics, L3 perception, process quality, or hardware behavior.

## Current state
Tasks 009 (`29bfa6e`), 014 (`2ac6621`), and 015 (`3bd9752`) are merged ancestors of clean `main`.
Task 009 supplies six deterministic L0 mocks behind the canonical Task 007/008 adapter contracts.
Task 014 supplies a thin Kit shell over pure application services, and Task 015 enforces paired
`cell.yaml`/USD identity. Task 013 supplies strict pen scenario YAML and deterministic normalized
traces but explicitly leaves Isaac control to this task. The pre-edit locked baseline passes Ruff,
strict mypy (57 core and 11 Studio source files), all 249 pytest tests, example validation, extension
metadata verification, and the Task 015 probe. GNU Make, ROS 2 Jazzy/colcon, and Isaac Sim 6 are not
installed on this Windows host. GitHub CLI is installed but its saved token is invalid.

## Design
`cellforge_simulation` is an ament-Python package with a ROS/Kit-free core. `models.py` parses the
existing scenario shape strictly, validates non-negative seeds, bounded uniform distributions,
fault targets/codes, fidelity levels, and assertions. `service.py` owns the lifecycle state machine
and depends only on a `SimulationBackend` port. Reset is required before every new configured run,
re-applies the exact seed and deterministic sampled state, clears prior trace/fault state, and
refuses commands in invalid states. Adapter registration uses immutable `cell.yaml` instance IDs,
canonical capability IDs and declared fidelity; duplicate or conflicting registrations fail.

The service records normalized control, setup, fault, adapter, and external job events. Scenario
completion evaluates required/forbidden events plus expected status. Evidence is canonical JSON
written atomically and includes the source digests, seed, samples, adapter declarations, requested
and achieved fidelity, explicit limitations, assertions, trace, and safety disclaimer. Requested
fidelity above the weakest registered required adapter fails with a stable unsupported-fidelity
result; it never silently downgrades.

The ROS 2 node exposes typed configure/control/register/fault/finalize services and consumes
`JobEvent` trace messages. It does not invent a second device command contract: registered adapters
continue to expose the same canonical capability actions/services used by hardware. The Isaac edge
maps the backend port to supported Isaac Sim 6 timeline and World reset/step APIs. The Studio panel
uses a pure `SimulationApplication` state model and a deferred backend adapter, keeping Kit/ROS
calls out of widget callbacks and allowing a clear unavailable state.

The reference Task 018 scenario requests only L0 contract fidelity. Task 020 will own L2 physical
pen simulation; this task explicitly rejects L2/L3 claims when those adapters are not registered.
Safety status may appear in setup/trace as read-only evidence, but no service commands or overrides
functional safety.

## Work sequence
1. Add the ExecPlan and pure models/service/backend contract; acceptance: focused tests cover
   invalid input, lifecycle, deterministic reset/replay, adapter registration, unsupported fidelity,
   faults, trace assertions, evidence and write failure.
2. Add typed ROS interfaces and a thin ROS node/launch path; acceptance: source-contract and Jazzy
   smoke tests cover request mapping, trace intake and response codes.
3. Add the Isaac Sim 6 backend, Studio application/panel wiring, and Kit/headless probes;
   acceptance: non-Kit tests prove UI-neutral behavior and manifest checks discover the bridge.
4. Document architecture, fidelity, commands and safety boundary; add Make targets and run the
   complete applicable regression/acceptance suite.
5. Inspect the full diff, commit only Task 018, publish a ready PR, wait for required checks, fix
   only scoped failures, merge when green/mergeable, and synchronize local `main`.

## Validation
- `make lint`, `make test`, `make validate-examples`
- `make ros-build`, `make ros-test`
- `make studio-simulation-check`
- `uv run --frozen pytest tests/test_simulation_control.py src/kit/cellforge.studio/tests`
- `uv run --frozen python scripts/verify_studio_simulation.py`
- Isaac Sim 6 headless: `isaac-sim.bat --no-window --ext-folder <repo>\src\kit --enable
  cellforge.studio --exec <repo>\scripts\verify_kit_simulation.py`
- `git diff --check`, staged checks, post-commit status/log, GitHub CI and mergeability.

## Risks and rollback
Isaac/Kit and ROS APIs cannot be executed locally, so their edges remain thin and are paired with
deterministic pure tests plus hosted Jazzy checks; the Isaac command remains unavailable unless a
real Isaac Sim 6 installation is found. Scenario reset ordering is a reproducibility risk, so the
service fails closed unless configuration is followed by a successful clean reset. Evidence write
failure must fail the run rather than report success without evidence. Reverting the Task 018
commit removes the new package/interfaces/panel without changing project schemas or canonical
artifacts.

## Progress
- [x] 2026-08-10 — Read required specifications, tasks, prerequisite ExecPlans, architecture,
  Studio, simulation, ROS, evidence/testing, and ADR documents; verified prerequisite ancestry,
  clean worktree, task branch, and green available baseline.
- [x] 2026-08-10 — Implement pure simulation control, models, evidence, and deterministic tests.
- [x] 2026-08-10 — Implement ROS/Isaac/Studio thin edges and integration probes.
- [ ] 2026-08-10 — Complete regression, Git, GitHub, merge, and final verification lifecycle.

## Decisions
- 2026-08-10 — Put lifecycle, validation, randomization, assertions, and evidence in one pure
  application service; ROS, Isaac Sim, and Studio are ports, not owners of business rules.
- 2026-08-10 — Treat fidelity as a hard capability claim. The requested level must be supported by
  every required adapter or the scenario is rejected with limitations recorded.
- 2026-08-10 — Preserve existing scenario seeds and source files; generated samples use a local
  `random.Random(seed)` instance and sorted keys so replay does not depend on global RNG state.
- 2026-08-10 — Read-only safety status may be recorded, but Task 018 adds no safety command,
  bypass, enforcement, certification, or authorization mechanism.
- 2026-08-10 — Host the ROS bridge inside Kit and spin it from the main-thread update stream, so
  external clients never call Isaac timeline/World/USD APIs from an external process or UI widget.
- 2026-08-10 — Derive required adapter instance IDs from canonical `cell.yaml`, require the chosen
  scenario to be declared inside that project, and freeze both `cell.yaml` and referenced USD
  hashes into evidence.
- 2026-08-10 — Allow multiple registered endpoints for one component instance (the reference
  camera exposes locate and inspect separately), while computing fidelity from the weakest
  required endpoint and validating faults against endpoint catalogs.

## Results
Implemented the pure lifecycle/scenario/evidence service; typed configure/control/register/fault/
finalize ROS interfaces; a Jazzy bridge and complete L0 launch; in-Kit Isaac Sim timeline/World/USD
backend hosted on the main-thread update stream; the ROS-backed Studio simulation panel; mock-node
self-registration and one-shot targeted fault injection; canonical project/scenario resolution;
normalized trace assertions; atomic evidence with source hashes, seed, samples, actual fidelity and
limitations; deterministic CPU and Isaac integration probes; documentation and CI coverage.

Final available checks: Ruff format/check pass for 315 files; strict mypy passes for 64 core/ROS
sources and 15 Studio sources; all 269 pytest tests pass; all 5 canonical schemas, 6 component
config schemas, and 19 example YAML documents validate; 18 focused Task 018 tests and 41 Studio
tests pass; Task 018 deterministic simulation, extension manifest, Task 015 scene, Task 016
placement, and Task 017 connection probes pass. GNU Make is unavailable, so its exact locked `uv`
command bodies were run. ROS 2 Jazzy/colcon are unavailable locally; the package-level generated
service/node smoke test is present for hosted Jazzy CI. Isaac Sim 6 is unavailable: PATH and Python
contain no Isaac executable/package, while `C:\isaacsim\VERSION` is `5.1.0-rc.19`; the documented
Isaac Sim 6 ROS/Kit probe was therefore not executed against an unsupported version. Publication is
currently blocked unless the invalid saved GitHub CLI token is reauthenticated.
