# TASK-011 — BehaviorTree.CPP supervisor

## Goal
Add the centralized ROS 2 supervisor that validates and executes exact behavior-tree versions,
invokes capability providers asynchronously, propagates cancellation, and emits traceable state
and node-transition events.

## Scope
Included:

- a C++20 `cellforge_supervisor` ROS package using BehaviorTree.CPP 4;
- a `RunJob` action server and top-level supervisor/job state transitions;
- registered `CellReady` and asynchronous `ExecuteSkill` tree nodes;
- exact task-ID-to-XML resolution beneath a configured immutable tree root;
- XML, registered-node, required-port, and blackboard-input preflight validation;
- action timeout, retry compatibility through standard BT decorators, and cancellation forwarding;
- canonical `JobEvent` emission for job, state, command, and tree-node transitions;
- deterministic C++ unit tests and a Jazzy ROS integration test.

Explicitly excluded:

- job/recipe freezing and production authorization (Task 012);
- the pen process tree and scenario runner (Task 013);
- MoveIt planning, vendor device logic, operator recovery UI, or functional-safety logic;
- changing the Task 007 ROS interface schemas.

## Current state
Task 010 is merged on `main` at `4f0b760` through PR #1. `RunJob`, `ExecuteSkill`, `CellState`,
and `JobEvent` are available from `cellforge_interfaces`; Task 010 records `/events/job` durably.
The repository has four ROS packages but no supervisor package. BehaviorTree.CPP is an accepted
architecture dependency in ADR 0004 and is available as the ROS Jazzy package
`behaviortree_cpp`.

Pre-edit baseline on 2026-08-08:

- `make lint`, `make test`, `make validate-examples`, `make ros-build`, and `make ros-test` are
  unavailable because GNU Make is not installed on this Windows host;
- direct Ruff format/check and strict mypy pass;
- direct pytest passes all 181 tests when directed to an accessible temporary directory;
- direct example validation passes 5 canonical schemas, 6 component schemas, and 11 YAML files;
- ROS 2 Jazzy, colcon, and a C++ compiler are unavailable locally.

## Design
`SupervisorNode` owns a `RunJob` action server, a BehaviorTree factory, event/state publishers, and
one worker thread for the active job. Goal acceptance only validates basic identity and single-job
exclusion. The worker resolves the exact `task_id` to `<tree_root>/<task_id>.xml`, rejects path
traversal, seeds the blackboard with frozen job fields and the ROS node, creates the tree, and runs
preflight before changing state to `RUNNING`.

`CellReady` is a fast condition over a required blackboard boolean. `ExecuteSkill` is a
`BT::StatefulActionNode`: `onStart()` sends a ROS action goal without waiting; executor callbacks
capture goal/result state; `onRunning()` observes only mutex-protected local state and the steady
deadline; `onHalted()` sends asynchronous cancellation. Standard BehaviorTree.CPP `Retry` and
`Timeout` decorators provide tree-authored retry/timeout composition while the action also enforces
the canonical goal timeout.

Preflight rejects unknown XML nodes during factory construction. It then inspects every node
manifest/config: required input ports must be explicitly mapped, blackboard references must already
exist or be produced by a tree output port, and literal inputs must parse when the node first reads
them. This keeps missing external inputs from reaching physical-capability calls.

Supervisor state uses canonical names and remains standard-control state only: `IDLE -> RUNNING ->
IDLE` on success/cancellation and `IDLE -> RUNNING -> RECOVERABLE_FAULT` on execution failure.
Validation rejection stays `IDLE`. No safety-rated function or interlock is implemented.

## Work sequence
1. Add the ExecPlan and package metadata/CMake contract; validate package structure statically.
2. Implement registered condition/action nodes and pure tree preflight/path-resolution helpers.
3. Implement the supervisor action server, execution worker, state publication, and events.
4. Add unit/integration tests for success, invalid XML/ports, non-blocking dispatch, timeout,
   retry, and cancellation.
5. Document runtime behavior and the production dependency record.
6. Run all available direct and requested Make/ROS checks, inspect the complete diff, and commit.

## Validation
Requested commands:

- `make lint`
- `make test`
- `make validate-examples`
- `make ros-build`
- `make ros-test`

Local equivalents where Make is unavailable:

- `uv run --frozen ruff format --check .`
- `uv run --frozen ruff check .`
- root strict-mypy command from `Makefile`
- `uv run --frozen pytest --basetemp <accessible-path> -p no:cacheprovider`
- `uv run --frozen python -m cellforge_domain.example_validation ...`

Jazzy acceptance evidence is `colcon build` plus package gtests/ROS tests. If still unavailable
locally, the limitation is reported without treating static/Python tests as ROS integration proof.

## Risks and rollback
The main risk is API drift between the locally unbuildable C++ code and Jazzy's packaged
BehaviorTree.CPP 4.6.2. Code targets that exact public API and CI resolves the declared rosdep.
Cancellation is a request, not proof that physical work stopped; the supervisor reports its own job
as cancelled while the adapter contract remains responsible for outcome certainty. Rollback is a
single Task 011 commit reverting the additive package/docs/tests; there is no schema or data
migration.

## Progress
- [x] 2026-08-08 — prerequisite, architecture, Git history, and regression baseline verified
- [x] 2026-08-08 — package and behavior-tree nodes implemented
- [x] 2026-08-08 — supervisor, validation, and event/state integration implemented
- [x] 2026-08-08 — locally available acceptance/regression checks complete
- [x] 2026-08-08 — complete Task 011 change reviewed and staged for the required commit
- [x] 2026-08-08 — PR #2 Python validation passed; the first Jazzy run exposed and the branch
  corrected a mixed CMake link-signature error before merge

## Decisions
- 2026-08-08 — Use only `behaviortree_cpp` plus ROS core packages; do not add the optional
  BehaviorTree.ROS2 wrapper dependency because the initial wrapper surface is small and CellForge
  needs its own stable result/event semantics.
- 2026-08-08 — Treat `RunJob.task_id` as an exact versioned tree identifier resolved beneath an
  immutable configured tree root; Task 012 remains responsible for freezing/authorizing it.
- 2026-08-08 — A software readiness condition may refuse execution but is not a safety function;
  independent rated hardware remains authoritative.
- 2026-08-08 — Action-server discovery is part of the asynchronous state machine: ticks poll
  `action_server_is_ready()` and never call a blocking discovery/future wait.
- 2026-08-08 — Preserve safety and required-device fields separately when republishing supervisor
  state; the combined readiness boolean must not misrepresent either input.
- 2026-08-08 — Use the plain `target_link_libraries` signature for the supervisor executable
  because Jazzy's `ament_target_dependencies` uses that signature for the same target; mixing it
  with the keyword `PRIVATE` signature fails during CMake configuration.

## Results
Implementation is complete. The package includes the supervisor executable, loadable node plugin,
preflight/path validator, versioned mock tree, and three Jazzy gtest targets covering preflight,
async success/retry/timeout/cancellation, transition events, and the complete `RunJob` action path.
Local Ruff, strict mypy, 184 Python tests, example validation, XML parsing, and clang-format pass.
GNU Make, ROS 2 Jazzy, and colcon are unavailable on this Windows host, so the exact five Make
targets and the three compiled Jazzy gtest targets could not execute locally. PR #2 is the
authoritative Ubuntu Jazzy rerun record. Its first run passed Python validation and reached the new
package before CMake rejected mixed keyword/plain link signatures; the branch now uses the plain
signature consistently with `ament_target_dependencies`.
