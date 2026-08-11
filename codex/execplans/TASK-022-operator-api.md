# TASK-022 — Local operator API and minimal UI

## Goal
Provide an offline-capable local operator API and minimal browser UI that exposes runtime status,
submits and cancels validated jobs, and requests only approved recovery actions with durable audit
evidence.

## Scope
Included:

- a `cellforge_operator_api` ROS Python package with a loopback FastAPI/uvicorn service;
- authenticated status, active-job, fault, bundle/recipe identity, and trace-summary endpoints;
- role-checked job submit/cancel and approved recovery endpoints;
- a bundle-local recovery catalog whose entries contain semantic actions, never ROS names;
- a narrow compiler rule that validates and content-addresses that catalog into the bundle;
- a fixed ROS bridge limited to `/cell/run_job`, `/cell/state`, `/events/job`, and one typed
  operator-action service;
- a local SQLite audit journal that records requested, denied, completed, failed, timed-out, and
  cancelled operator mutations;
- a dependency-free HTML/CSS/JavaScript operator screen served by the local API;
- deterministic unit, contract, timeout, cancellation, authorization, and failure-path tests.

Excluded:

- Task 023 hardware adapters or any later task;
- platform-server synchronization, cloud authentication, fleet operation, or remote UI hosting;
- recipe/configuration editing, arbitrary ROS topic/service/action access, or raw device commands;
- safety logic, safety reset, interlock bypass, or claims of functional-safety enforcement.

## Current state
The clean starting point is synchronized `main`/`origin/main` at `416f9e0`. Task 010
(`b09ec6e`), Task 012 (`a82fa68`), and Task 021 (`d61fc84`) are ancestors of `main`; Tasks
012 and 021 have merged PR commits, and Task 010 is in the merged prerequisite history before Task
011. The existing runtime has canonical `CellState` and durable `JobEvent` records, a public
`/cell/run_job` gateway, and active bundle identity supplied by the bundle agent. No operator API,
local authorization store, approved recovery contract, or operator UI exists.

Untouched baseline on 2026-08-11: direct Makefile equivalents pass Ruff format/check, strict mypy
for 72 runtime and 15 Kit sources, 308 pytest tests, and validation of 5 schemas, 6 component
schemas, and 22 examples. One existing Windows directory-symlink test is skipped. GNU Make, ROS 2
Jazzy, and colcon are unavailable on this Windows host.

## Design
FastAPI exposes versioned loopback routes and a static local page. Bearer credentials are verified
against SHA-256 token digests in a protected cell-local JSON file outside the immutable bundle.
Roles are ordered viewer, operator, maintainer, and administrator. Tokens and request bodies are
never written to audit records.

`OperatorService` depends on a typed `RuntimePort`, `AuditStore`, `RecoveryCatalog`, and
`Authorizer`. Its mutation surface is deliberately closed: submit a canonical `RunJob` request,
cancel a known job, or execute a recovery entry selected by immutable action ID. Recovery entries
bind a stable fault code, semantic action kind, instructions, confirmation phrase, and minimum
role. They cannot contain service, action, topic, package, or executable names.

The ROS bridge subscribes to canonical cell/job events and calls only compile-time fixed interface
names. The operator-action service accepts the approved semantic action ID and fault context; its
server remains the runtime/supervisor recovery implementation and must independently validate
state. If that fixed service is unavailable, the API returns an explicit failure and never reports
success.

The compiler treats `operator/operator-recovery.json` as an optional fixed project input, validates
its closed semantic fields, and inventories it as `config/operator-recovery.json`. Any change then
changes the bundle ID; arbitrary endpoint/command fields fail compilation.

Every mutation durably records an attempt before reaching ROS and a terminal outcome before the HTTP
response. Audit-write failure before dispatch refuses the operation. Failure after dispatch reports
that audit persistence failed and does not invent an operation outcome. Deadlines request
cancellation and report timeout/outcome uncertainty. Client/task cancellation propagates through a
cancellation event and is itself audited. Read endpoints use only cell-local state and databases;
no platform hostname, connector, or internet dependency exists.

FastAPI (MIT, actively maintained) and uvicorn (BSD-3-Clause, actively maintained) are production
dependencies because they provide the typed ASGI API and local HTTP server. They may be removed by
replacing the thin `api.py`/entry-point layer while preserving the pure service/runtime ports.

## Work sequence
1. Add the ExecPlan, dependency metadata, typed operator models, authorization, recovery catalog,
   and durable audit store; acceptance: invalid catalogs/tokens fail closed and audit survives
   restart.
2. Add the pure operator service and exhaustive tests; acceptance: success, invalid input,
   authorization denial, runtime failure, timeout, cancellation, and audit failure have stable
   outcomes.
3. Add FastAPI routes and the local UI; acceptance: every deliverable endpoint has contract tests,
   mutations are auditable, and the page uses only same-origin local calls.
4. Add the fixed ROS bridge and operator-action service interface; acceptance: static/Jazzy tests
   prove no arbitrary ROS name can enter through API input or catalog data.
5. Update runtime, security, observability, architecture, package, and dependency documentation;
   add a Task 022 integration target; run all checks and complete the Git/GitHub lifecycle.

## Validation
Run:

```text
make lint
make test
make validate-examples
make operator-api-check
make ros-build
make ros-test
```

When GNU Make or local ROS 2 Jazzy is unavailable, run the exact uv recipes locally and use hosted
Ubuntu/Jazzy CI as integration evidence. Focused tests cover endpoint success, malformed JSON and
catalogs, missing/invalid credentials, operator-versus-maintainer recovery policy, unavailable
runtime services, audit failures, deadlines, cancellation propagation, restart durability, and
offline operation.

## Risks and rollback
The primary risk is mixing an ASGI event loop with the ROS executor; the bridge keeps ROS spinning
in its own thread and crosses the boundary with bounded futures. Status can become stale, which is
reported explicitly and never interpreted as safe/ready. Token files depend on correct local OS
permissions. Rollback is the Task 022 commit; the additive audit SQLite database and recovery
catalog need no migration for earlier packages.

## Progress
- [x] 2026-08-11 — required documents, prerequisite ancestry, clean Git state, and baseline verified.
- [x] 2026-08-11 — core authorization, recovery catalog, audit, and operator service complete.
- [x] 2026-08-11 — API, minimal UI, fixed ROS bridge, and bundle compiler integration complete.
- [x] 2026-08-11 — documentation and all available local checks complete.
- [x] 2026-08-11 — task commit `656fa00`, ready PR #18, and required hosted CI checks complete.
- [ ] 2026-08-11 — merge and local main synchronization complete.

## Decisions
- 2026-08-11 — Keep recovery configuration semantic and immutable; never accept ROS graph names or
  executable commands from HTTP or bundle data.
- 2026-08-11 — Store only token digests outside the bundle and compare them in constant time.
- 2026-08-11 — Audit mutation attempts before dispatch and terminal outcomes before response so an
  unavailable audit store fails closed.
- 2026-08-11 — Treat displayed safety state as read-only standard-control information; no API role
  or recovery action can bypass independent rated hardware.

## Results
The loopback operator service now provides role-authenticated local status, active job, faults,
bundle/recipe identity, trace summaries, job submit/cancel, and approved recovery endpoints plus a
same-origin UI. Mutation attempts and outcomes are durably audited. Recovery policy is semantic,
role-gated, runtime-revalidated, and frozen into the bundle content address; no HTTP or catalog field
can select a ROS endpoint. The ROS bridge uses only four fixed canonical contracts and reports
service absence or uncertain outcomes explicitly.

Local direct Makefile equivalents pass Ruff format/check, strict mypy for 79 runtime/test and 15 Kit
sources, all 324 runnable pytest tests, validation of 5 canonical schemas/7 auxiliary schemas/22
example YAML documents, the 19-test Task 022 contract suite, and the Task 021 bundle-agent regression
check. One pre-existing real directory-symlink test is skipped on Windows because elevated symlink
privilege is unavailable. Literal GNU Make, ROS 2 Jazzy, and colcon remain unavailable locally;
the hosted replacement run passed Python 3.12 validation in 40 seconds and the complete ROS 2 Jazzy
build/test job in 11 minutes. The first hosted ROS attempt was cancelled after a pre-existing
`cellforge_job_gateway` test process stopped producing output for about an hour; its clean rerun
passed without code changes. PR #18 is ready and green; merge and final main synchronization remain
pending.
