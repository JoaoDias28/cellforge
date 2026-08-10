# TASK-013 — Headless pen workflow and scenarios

## Goal
Execute the canonical reference pen behavior tree deterministically against the Task 009 L0 mock
adapters without Isaac Sim, and emit replayable trace and test evidence for all scenarios required
by `docs/testing.md`.

## Scope
Included:

- concrete headless implementations for the initial pen behavior-tree conditions and actions;
- explicit XML port mappings for frozen job, recipe, process, inspection, and trace values;
- a strict scenario loader and seed-derived deterministic trace/command identity;
- nominal plus the nine fault/cancellation scenarios enumerated in `docs/testing.md`;
- JSON and JUnit report writers and committed normalized golden traces;
- tests for success, invalid input, cancellation, safety refusal, process uncertainty, reports, and
  deterministic seed replay.

Excluded:

- Isaac Sim, OpenUSD physics, rendered perception, MoveIt, or physical process-quality evidence;
- real hardware, vendor protocols, operator recovery UI, or functional-safety logic;
- automatic retry of a process command or changes to released ROS interface schemas;
- Task 014 or any later numbered task.

## Current state
Tasks 009, 011, and 012 are ancestors of `main`; Tasks 011 and 012 are merged through PRs #2 and
#3. Task 009 supplies deterministic pure mock adapters, Task 011 supplies the production
BehaviorTree.CPP supervisor, and Task 012 freezes validated jobs before supervisor submission. The
reference XML names the intended pen nodes but Task 013 has not implemented them. Only nominal and
laser-timeout example scenarios exist and neither has an executable headless runner or golden
evidence.

Pre-edit baseline on 2026-08-10:

- literal `make lint`, `make test`, `make validate-examples`, `make ros-build`, and `make ros-test`
  are unavailable because GNU Make is not installed on this Windows host;
- exact direct Ruff format/check and strict mypy equivalents pass;
- direct pytest passes all 204 tests;
- direct example validation passes 5 canonical schemas, 6 component schemas, and 11 YAML files;
- ROS 2 Jazzy, colcon, and clang-format are unavailable directly on the host.

## Design
`cellforge_mock_adapters.headless` is deterministic L0 test infrastructure. It parses the canonical
BehaviorTree.CPP XML subset used by the pen workflow (`Sequence`, `RetryUntilSuccessful`, and the
declared pen leaf nodes), resolves explicit blackboard mappings, and dispatches real capability
commands through Task 009 adapters. It is not a replacement production supervisor: production
continues to use Task 011 BehaviorTree.CPP, while this runner provides fast no-ROS/no-Isaac scenario
evidence against the identical adapter contracts.

Each scenario is schema-validated before execution. The scenario seed and node/attempt index derive
UUIDv5 trace and command IDs, making normalized traces byte-stable and failing seeds exactly
replayable. Trace normalization excludes timestamps but preserves sequence, behavior node,
component, command ID, result code, outcome certainty, and evidence payload.

The safety-health condition is evaluated before any adapter command. Process selection and cycle
execution have no retry decorator. An uncertain process result immediately records
`OUTCOME_UNKNOWN`, stops the tree, and requires explicit recovery. The L0 report states that it
proves sequencing and contract behavior only, not physics, mark quality, or functional safety.

No new production dependency is added. The runner uses the repository's existing PyYAML dependency
and Python standard library plus Task 008/009 packages.

## Work sequence
1. Add this ExecPlan and explicit pen XML port mappings; acceptance: the tree has no implicit job,
   recipe, or process inputs.
2. Implement strict scenario loading, initial behavior nodes, deterministic command/trace capture,
   assertion evaluation, and report writers; acceptance: one nominal run passes from source.
3. Add all reference scenario documents and golden normalized traces; acceptance: the suite passes
   and repeated/replayed seeds produce byte-identical event sequences.
4. Add unit/package tests and documentation; acceptance: safety-unhealthy dispatches no process
   command and uncertain process outcome executes the process exactly once.
5. Run all requested and available checks, inspect the complete diff, commit, publish, and follow
   required CI through merge.

## Validation
Requested commands:

- `make lint`
- `make test`
- `make validate-examples`
- `make ros-build`
- `make ros-test`
- `uv run --frozen python -m cellforge_mock_adapters.headless --scenario-root
  examples/pen_engraving/scenarios --tree examples/pen_engraving/behavior_tree.xml --reports-dir
  <temporary-directory> --golden-root examples/pen_engraving/golden_traces`

Where local Make/ROS tooling is unavailable, run the exact direct Makefile equivalents and obtain
authoritative Ubuntu/Jazzy evidence from GitHub Actions before merge.

## Risks and rollback
The main risk is accidental divergence between this lightweight XML executor and BehaviorTree.CPP.
The accepted XML subset is deliberately small and strict, every supported node is explicit, and
ROS package tests statically verify the production tree contract. L0 results cannot be presented as
Isaac, hardware, process-quality, or safety-validation evidence. Rollback is the Task 013 commit;
there is no schema or persistent-data migration.

## Progress
- [x] 2026-08-10 — instructions, architecture, prerequisites, history, and baseline verified
- [x] 2026-08-10 — XML port mappings and headless node implementations complete
- [x] 2026-08-10 — all ten required scenarios, reports, and golden traces complete
- [x] 2026-08-10 — local acceptance/regression checks complete, including disposable Jazzy ROS
  build/test evidence
- [ ] 2026-08-10 — hosted GitHub acceptance checks complete
- [ ] 2026-08-10 — task commit, ready PR, green CI, merge, and local main sync complete

## Decisions
- 2026-08-10 — Keep the runner inside the mock-adapter package so it executes the Task 009 adapter
  implementations directly and introduces no cross-layer package dependency.
- 2026-08-10 — Treat the ten numbered entries in `docs/testing.md` as ten total scenarios: one
  nominal and nine fault/cancellation cases.
- 2026-08-10 — Derive UUIDv5 identities from the scenario seed and command ordinal so deterministic
  replay preserves IDs as required by golden-trace policy.
- 2026-08-10 — Keep safety refusal as standard-control test behavior only; independent rated
  hardware remains authoritative.

## Results
The canonical pen XML now has explicit frozen-job, recipe, program, process-data, inspection, and
output port mappings. The mock-adapter package contains a strict L0 XML executor with concrete
implementations of every declared pen leaf node, deterministic UUIDv5 trace/command identity,
adapter-backed capability dispatch, assertion evaluation, JSON/JUnit report writers, seed replay,
and golden verification. The example contains the ten scenarios numbered in `docs/testing.md` and
ten committed normalized traces.

Final local evidence:

- literal Make commands remain unavailable on Windows because GNU Make is not installed;
- exact direct `make lint` equivalents pass: Ruff reports 172 files formatted, Ruff lint passes,
  and strict mypy reports no issues in 57 source files;
- exact direct `make test` equivalent passes all 212 tests;
- exact direct `make validate-examples` equivalent validates 5 canonical schemas, 6 component
  schemas, and 19 example YAML documents;
- the task-specific headless command passes all ten scenarios and matches every golden trace;
- in a disposable `ros:jazzy-ros-base` container, exact `make ros-build` builds all six packages
  and exact `make ros-test` passes 47 tests with zero errors, failures, or skips, including
  clang-format and clang-tidy.

L0 limitations remain explicit: this evidence does not exercise Isaac Sim, geometry, physics,
rendered perception, mark quality, real hardware, or independent functional safety. GitHub
publication and hosted CI evidence remain pending.
