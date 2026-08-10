# Task 020 — Simulated pen manipulation

## Goal
Provide an L2 physical-simulation implementation for the reference pen cell with bounded seeded
product spawning, attachment and fixture-seating behavior, collision-aware manipulation requests,
fault detection, and reproducible 100-seed evidence.

## Scope
Included: simplified internal-license scene geometry for the robot, gripper, pen, input carrier,
fixture, laser enclosure, and camera; a ROS/Kit-free deterministic manipulation model; an Isaac Sim
6/PhysX adapter and headless probe; explicit MoveIt/MTC request sequencing; nominal pick, load,
process-safe-pose, process, and unload behavior; dropped-pen and failed-seating faults; collision and
cycle tests; a reproducible 100-seed report; documentation and CI wiring.

Excluded: laser-material interaction, heat transfer, plume/optics, mark quality, rendered
perception, real robot or laser control, production adapters, functional-safety enforcement or
certification, and Task 021 or later tasks.

## Current state
Tasks 013, 018, and 019 are merged ancestors of `main` through PRs #4/#5, #14, and #15. Task 013
provides the canonical pen sequence and deterministic L0 scenarios; Task 018 provides scenario
control, canonical YAML/USD evidence identities, and an Isaac timeline backend; Task 019 provides
planner-neutral MoveIt actions, an MTC pick/load/unload builder, named safe poses, and collision
result mapping. `main` and `origin/main` both pointed to merge `7565f4e` before branching, and the
working tree was clean.

Pre-edit Windows baseline on 2026-08-10: exact direct Makefile equivalents pass Ruff formatting and
lint, strict mypy (65 core and 15 Studio files), all 275 pytest tests, validation of 5 canonical
schemas, 6 component schemas, and 19 YAML examples, plus Task 018 and Task 019 focused checks. GNU
Make, ROS 2 Jazzy/colcon, and Isaac Sim 6 are unavailable locally; hosted CI is authoritative for
ROS and a supported Isaac runner is required for actual PhysX integration evidence.

## Design
`cellforge_simulation.physical` owns deterministic state, bounds, fault mapping, sequence events,
collision envelopes, and Monte Carlo reporting without importing ROS, Kit, or USD. It consumes a
scenario seed and emits explicit planner-neutral manipulation stages matching Task 019 contracts:
pick, load, process-safe pose, and unload. It does not reimplement MoveIt planning; collision
results are inputs/outcomes at this boundary, and MTC remains the staged motion implementation.

The canonical USDA scene gains conservative analytic geometry and physics metadata. Runtime pen
instances are spawned beneath a declared product-spawn scope; they are not operational component
instances and do not create a second `cell.yaml` graph. The Isaac adapter alone maps spawn,
rigid-body attachment/detachment, physics stepping, and seating queries to supported OpenUSD/PhysX
APIs. Existing immutable component instance IDs remain paired between `cell.yaml` and USD.

All randomization is uniform within scenario-declared millimetre/degree bounds and uses a local
`random.Random(seed)`. The 100-seed report records every seed, sampled pose, result, stable fault,
cycle event sequence, and aggregate counts. Re-running the same seed range must produce identical
canonical JSON. Dropped products and failed fixture seating fail explicitly; no placeholder returns
success. Simulation refusal and status reporting are ordinary engineering controls, never rated
safety functions.

## Work sequence
1. Add this ExecPlan and Task 020 L2 scenario definitions; acceptance: sources validate and preserve
   the existing canonical graph/scene identity contract.
2. Add conservative scene geometry plus the pure manipulation/cycle model; acceptance: focused
   tests cover bounded same-seed spawning, nominal stages, invalid input, collision, dropped pen,
   failed seating, and deterministic replay.
3. Add the Isaac/PhysX edge, MoveIt/MTC contract verifier, headless probe, and 100-seed report tool;
   acceptance: CPU checks verify structure and deterministic evidence while the supported Isaac
   command exercises actual stage/physics operations when available.
4. Update documentation, Make/CI targets, and run all requested regression and acceptance checks;
   acceptance: available checks are green and unavailable Isaac/ROS evidence is stated honestly.
5. Inspect the complete diff, commit only Task 020, publish a ready PR, wait for required checks,
   fix only scoped failures, merge when green/mergeable, and synchronize local `main`.

## Validation
- `make lint`, `make test`, `make validate-examples`
- `make studio-simulation-check`, `make motion-service-check`, `make pen-physical-sim-check`
- `make ros-build`, `make ros-test`
- `uv run --frozen python scripts/run_pen_physical_report.py --seeds 100 --output <path>`
- Isaac Sim 6 headless: `isaac-sim.bat --no-window --ext-folder <repo>\src\kit --enable
  cellforge.studio --exec <repo>\scripts\verify_kit_pen_physical.py`
- `git diff --check`, staged checks, post-commit status/log, hosted CI, and mergeability.

## Risks and rollback
The main risk is confusing deterministic CPU modeling with PhysX evidence. Reports name their
backend and fidelity, and only the supported Isaac probe may claim an actual L2 physics run. Simple
placeholder geometry is conservative and documented; it is not dimensional or process
qualification. Attachment API changes are isolated in the Isaac adapter. Reverting the Task 020
commit removes the additive scenarios, model, scene changes, checks, and docs without a schema or
persistent-data migration.

## Progress
- [x] 2026-08-10 — instructions, relevant architecture/ADRs, prerequisites, history, clean state,
  branch, and pre-edit baseline verified
- [x] 2026-08-10 — scene, deterministic model, fault detection, and tests complete
- [x] 2026-08-10 — Isaac edge, MoveIt/MTC verifier, and 100-seed report complete
- [ ] 2026-08-10 — full validation, Git, GitHub, merge, and final verification complete

## Decisions
- 2026-08-10 — Keep runtime pen instances as spatial simulation entities beneath the canonical USD
  scene, not as mutable operational component instances in `cell.yaml`.
- 2026-08-10 — Treat the CPU model as deterministic contract/cycle evidence only; actual L2 physics
  requires the Isaac Sim 6 probe and cannot be inferred from authored physics metadata.
- 2026-08-10 — Reuse Task 019 planner-neutral action and named-pose contracts; do not move workflow
  ownership from the behavior tree into MoveIt/MTC or the simulator.
- 2026-08-10 — Model laser readiness, timing, and sequence only. No simulated result qualifies mark
  quality, laser safety, or physical process parameters.
- 2026-08-10 — Add the optional scenario `simulation.requested_fidelity` field to the canonical
  schema/domain model with an L0 default. Task 018 already parses this field; the additive schema
  change lets Task 020 source scenarios declare L2 without breaking existing L0 documents.

## Results
Implemented conservative analytic scene/physics assets; strict L2 source scenarios; bounded local
seed sampling; explicit grasp, seating, collision, drop, and cycle state; planner-neutral Task 019
commands plus generated ROS action mapping; a thin Isaac Sim 6 OpenUSD/PhysX backend and probe; and
stable 100-seed JSON evidence generation. The additive canonical scenario-fidelity field defaults
to L0, preserving all existing scenario documents.

Final pre-commit local evidence: Ruff formatting/lint passes for 203 files, strict mypy passes 69
core and 15 Studio files, all 294 pytest tests pass, and example validation accepts 5 canonical
schemas, 6 component schemas, and 22 YAML documents. Task 018's 18 focused tests/probe, Task 019's 9
focused tests/probe, and Task 020's 19 tests/probe all pass. The 100-seed report passes 100/100 with
canonical SHA-256 `05af29389c774dfcd37a72461e60e0b3e119ed17dab44b35d26a09f0cf831cfd`.

Literal Make commands are unavailable because GNU Make is absent. ROS 2 Jazzy and colcon are
absent, and the local Docker engine is not running, so local `make ros-build`/`make ros-test` and the
generated-action ROS smoke test are unavailable; hosted Jazzy CI is authoritative. The only local
Isaac installation reports 5.1.0-rc.19, while Task 020 targets Isaac Sim 6, so the documented
headless PhysX probe is unavailable and is not reported as passing. CPU evidence explicitly records
that PhysX did not execute. Publication and merge results remain pending.
