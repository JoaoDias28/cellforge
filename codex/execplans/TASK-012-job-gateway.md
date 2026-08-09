# TASK-012 — Job gateway and recipe freeze

## Goal
Add the production-cell job gateway that validates exact runtime references, freezes accepted
inputs durably, enforces idempotency and execution-mode policy, and forwards only accepted jobs to
the BehaviorTree supervisor.

## Scope
Included:

- an `ament_python` `cellforge_job_gateway` package and `/cell/run_job` action server;
- immutable bundle, recipe, task, payload, and trace freezing into SQLite;
- exact manifest path/hash, recipe/cell/capability, task, bundle-mode, and approval checks;
- conflicting duplicate rejection, completed-result replay, and fail-closed restart reconciliation;
- cancellation/feedback forwarding to the internal supervisor action endpoint;
- deterministic pure tests plus package/ROS contract checks and runtime documentation.

Excluded:

- the Task 013 pen behavior tree and scenario runner;
- bundle installation/activation (Task 021), operator APIs (Task 022), or enterprise sync;
- device/process logic, recipe approval workflows, or functional-safety enforcement;
- changes to the Task 007 `RunJob` action schema.

## Current state
Task 011 is merged through PR #2 at merge commit `53d583c` and currently owns `/cell/run_job`
directly. Task 006 manifests already freeze recipe/task paths and SHA-256 digests. The Task 007
action contains the required job, exact recipe/task, mode, idempotency, payload, timeout, result,
feedback, and trace fields. No gateway or durable frozen-job store exists.

Pre-edit baseline on 2026-08-09:

- all literal Make targets are unavailable because GNU Make is not installed on this Windows host;
- exact direct Ruff format/check and strict mypy equivalents pass;
- direct pytest passes all 184 tests;
- direct example validation passes 5 canonical schemas, 6 component schemas, and 11 YAML files;
- ROS 2 Jazzy/colcon are unavailable and access to the Docker Linux engine is denied.

## Design
`BundleResolver` loads the active immutable `manifest.json`, checks its declared bundle ID and
mode, resolves recipe and task files beneath the configured bundle root, verifies their declared
SHA-256 digests, and validates exact recipe identity/status/cell/capability compatibility. Simulation
accepts non-retired development recipes, commissioning requires TESTED or APPROVED, and production
requires APPROVED. Requested mode must exactly match the active bundle mode, so a simulation bundle
cannot authorize physical operation.

`SqliteJobStore` uses a unique idempotency key and canonical request hash. A matching completed
duplicate replays its persisted result without reaching the supervisor; any differing request is a
conflict. Nonterminal records found at process startup become `OUTCOME_UNKNOWN` and are never
automatically replayed. SQLite synchronous commits make the frozen record durable before supervisor
submission and the final result durable before the action result is returned.

`JobGatewayNode` serves `/cell/run_job` and forwards accepted frozen goals to
`/cell/supervisor/run_job`, including feedback and cancellation. The supervisor endpoint becomes a
configurable parameter with that internal default. The gateway refuses malformed input and
unavailable supervisor state with stable result codes. This is application-level refusal only;
independent rated hardware remains authoritative for protective functions.

## Work sequence
1. Add this ExecPlan and package metadata; verify the static package contract.
2. Implement canonical requests, bundle/recipe/task validation, durable job records, and restart
   reconciliation with pure tests.
3. Implement the ROS action gateway and move the supervisor to its internal configurable endpoint.
4. Document runtime behavior and the PyYAML runtime dependency/removal path.
5. Run requested and locally available checks, inspect the complete change, commit, publish, and
   follow required CI through merge.

## Validation
Requested commands:

- `make lint`
- `make test`
- `make validate-examples`
- `make ros-build`
- `make ros-test`

Local equivalents when Make is unavailable are the exact underlying `uv` commands from the
Makefile. Hosted CI supplies the authoritative Ubuntu 24.04 / ROS 2 Jazzy build and test evidence.

Acceptance tests cover conflicting and matching duplicates, completed replay, restart uncertainty,
production approval refusal, reference simulation acceptance, malformed payload/input, compatibility
and digest failures, result persistence ordering, and path containment.

## Risks and rollback
The primary risk is action endpoint integration drift between Python `rclpy` and the C++ supervisor.
The interface is unchanged and both endpoints are parameterized; Jazzy CI provides final contract
evidence. Restart recovery intentionally prefers false refusal over accidental physical replay.
Rollback is the Task 012 commit(s), with no migration required for earlier packages; the new SQLite
database is additive runtime state.

## Progress
- [x] 2026-08-09 — prerequisites, PR #2 merge, architecture, Git history, and baseline verified
- [x] 2026-08-09 — durable resolver/idempotency core and tests implemented
- [x] 2026-08-09 — ROS gateway and supervisor endpoint integration implemented
- [x] 2026-08-09 — documentation and all available validation complete
- [ ] 2026-08-09 — task commit, ready PR, green CI, merge, and local main sync complete

## Decisions
- 2026-08-09 — Keep the Task 007 action schema unchanged; the active configured bundle supplies the
  bundle ID that is copied into the frozen record.
- 2026-08-09 — Never resume a nonterminal record after gateway restart because physical outcome may
  be uncertain; require explicit recovery instead of automatic duplicate execution.
- 2026-08-09 — Split the public gateway and internal supervisor action endpoints while keeping the
  supervisor endpoint parameterized for isolated tests and controlled compatibility.
- 2026-08-09 — Include bundle, recipe, and task digests in the idempotency request hash so a retry
  after deployment activation cannot replay a result from different frozen runtime inputs.
- 2026-08-09 — Use a reentrant callback group and multithreaded executor for the Python gateway;
  public action execution must yield while internal action feedback, cancellation, and results run.
- 2026-08-09 — Require a known material classification for commissioning and production as a
  defense-in-depth standard-control rule; independent rated hardware remains authoritative.

## Results
The gateway package now validates and freezes exact active-bundle inputs, enforces simulation,
commissioning, and production recipe policies, persists canonical frozen jobs/results in SQLite,
and forwards accepted jobs across the unchanged `RunJob` contract to the internal supervisor
endpoint. Completed duplicates replay durably, conflicting or cross-bundle duplicates fail, and
restart uncertainty never triggers automatic work.

The exact `make lint`, `make test`, and `make validate-examples` targets pass in an isolated Ubuntu
container: Ruff and strict mypy are clean, all 204 Python tests pass, and 5 schemas, 6 component
schemas, and 11 example YAML documents validate. The exact `make ros-build` target builds all six
packages. The first ROS test run exposed only CRLF-influenced C++ formatting in the two touched
supervisor files; repository clang-format corrected it. The final exact `make ros-test` run passes
all six packages and 47 tests with zero failures, errors, or skips. A Jazzy action integration test
also verifies forwarding, persisted-before-return ordering, replay, conflicting duplicates,
cancellation, and timeout/uncertain-outcome behavior.
