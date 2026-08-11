# Task 023 — Execution contracts and trace identity

## Goal

Introduce a trusted internal frozen-job boundary and preserve one immutable execution identity from
gateway admission through supervisor execution, durable trace storage, restart reconciliation, and
operator presentation. Add the contract schemas needed by later runtime and evidence tasks without
implementing Task 024 behavior-tree plugins or any hardware function.

## Scope

Included: ROS interface additions, gateway/supervisor internal action migration, frozen artifact
digest validation, additive event identity, trace database migration, operator/state integration,
five contract schemas, component capability definition references, tests, and documentation.

Excluded: canonical pen leaf nodes, runtime bringup, recovery service implementation, bundle
assembly/signing, real Isaac adapters, platform services, hardware adapters, and functional safety.

## Current state

Public and internal job submission both use `RunJob`. The gateway generates a trace ID and stores it
in `FrozenJob`, but forwards only the original public goal; the supervisor generates a second trace
ID. `JobEvent` and the trace table retain only bundle identity. The state aggregator always clears
active job/trace fields, and the operator bridge expects a behavior-tree event name not published by
the supervisor. The compiler resolves capability contract/version strings but component manifests
do not reference a formal contract definition. All prerequisites through Task 022 and roadmap PR
#19 are merged. Baseline Python, schema, and hosted Jazzy checks are green.

## Design

Keep `/cell/run_job` and `RunJob.action` unchanged. Add private `ExecuteFrozenJob.action` on
`/cell/supervisor/run_job`. Its goal contains trace/job/cell/bundle/source identities, exact recipe
and tree hashes, frozen recipe YAML, public job inputs, execution mode, idempotency key, calibration
IDs/hashes, and timeout. The gateway alone creates this goal from a verified manifest.

The supervisor validates UUID/hash/revision formats, configured cell and bundle equality, recipe
digest, calibration shape, safe versioned task ID, resolved tree containment, and exact tree digest
before tree construction. A mismatch returns a stable `supervisor.frozen.*` failure and emits no
capability command. The verified identity populates blackboard values and every job/state/tree
event. Cancellation and result semantics remain unchanged.

`JobEvent` gains additive source, recipe, task, mode, and calibration fields. The append-only trace
table gains corresponding defaulted columns via idempotent `ALTER TABLE` migration; existing rows,
IDs, ordering, payloads, and timestamps are untouched. Operator trace summaries expose the exact
identity. The state aggregator subscribes to `/cell/supervisor_state`, overlays execution/fault
states and active IDs on device/safety readiness, and never treats that standard-control state as a
safety-rated signal.

Register five additional Draft 2020-12 schemas: capability contract, skill, fault catalog,
calibration, and evidence. Add a required versioned `definition` URI to each component capability
implementation and update the reference components. Registry meta-validation covers these schemas;
example YAML classification remains limited to project documents.

Affected ROS packages move together to version `0.2.0`; the public `RunJob` wire shape does not
change. OpenSSL EVP supplies SHA-256 verification in the C++ supervisor. OpenSSL is Apache-2.0,
maintained by the OpenSSL project, already part of the Ubuntu/ROS platform, and removable if digest
verification later moves to a shared platform cryptography package.

## Work sequence

1. Add schemas/domain references and tests; acceptance: registry and examples validate all ten
   canonical schemas and reject missing/malformed capability definition references.
2. Add and package `ExecuteFrozenJob` plus additive `JobEvent` fields; acceptance: canonical and
   packaged interface copies match and generated-type tests cover the frozen identity.
3. Extend gateway frozen records and forward the new private action; acceptance: pure and Jazzy
   gateway tests prove exact identity, idempotent replay, cancellation, timeout, and restart.
4. Validate frozen identities in the supervisor and publish them on every event; acceptance: Jazzy
   tests prove success plus cell/bundle/recipe/tree mismatch refusal before a skill goal.
5. Migrate trace storage and repair state/operator consumption; acceptance: old-database migration
   preserves rows and live active-job/step/identity state is coherent.
6. Update package versions/docs, run all gates, inspect/stage/commit only Task 023, publish a ready
   PR, wait for every required check, merge, and fast-forward local main.

## Validation

- exact `make lint`, `make test`, and `make validate-examples` command bodies locally;
- `make ros-build` and `make ros-test` on hosted Ubuntu 24.04 / ROS 2 Jazzy;
- focused interface, gateway, supervisor, state/trace, operator, schema, migration, mismatch,
  cancellation, timeout, and restart tests;
- `git diff --check`, cached diff review, clean post-commit and post-merge status.

## Risks and rollback

ROS message additions require coordinated rebuilding of the immutable runtime release, so affected
packages share version 0.2.0. The public action remains stable. SQLite migration is additive and
defaulted; rollback code can read the expanded table because old columns remain unchanged. A task
revert restores the old internal action but must deploy all affected ROS packages together. No
safety function or physical authorization is introduced.

## Progress

- [x] 2026-08-11 — roadmap PR #19 merged and Task 023 prerequisites/history verified.
- [x] 2026-08-11 — pre-edit Python, schema, and hosted Jazzy baseline recorded green.
- [x] 2026-08-11 — ten-schema registry and versioned component capability references complete.
- [x] 2026-08-11 — private frozen-job ROS interface and gateway forwarding complete.
- [x] 2026-08-11 — supervisor digest validation and typed event identity propagation complete.
- [x] 2026-08-11 — lossless trace migration and operator/state merge complete.
- [ ] all local/hosted validation, commit, PR, merge, and main synchronization complete.

## Decisions

- 2026-08-11 — preserve public `RunJob` and introduce a private typed action so untrusted callers
  cannot choose frozen artifact identity.
- 2026-08-11 — verify exact recipe bytes and resolved tree bytes in the supervisor before tree
  construction; trusting identifiers alone would preserve the audited integrity gap.
- 2026-08-11 — store identity in typed event/trace fields rather than relying on optional payload
  JSON, enabling deterministic offline queries and migrations.
- 2026-08-11 — merge supervisor execution state into aggregation; safety health remains sourced
  only from the independent read-only safety-status input.

## Results

Local Ruff and mypy gates pass. The full suite passes 328 tests, with the existing Windows-only
directory-symlink case skipped. All 22 example YAML documents validate against ten canonical and seven component
configuration schemas. Docker/ROS is unavailable on this workstation, so Jazzy build, generated
interface, C++ mismatch/cancellation, and ROS node integration checks remain assigned to hosted CI.
The first hosted build exposed mixed keyword/plain `target_link_libraries` signatures after
`ament_target_dependencies`; the OpenSSL link was changed to the matching plain signature before
rerunning CI. The rerun compiled the complete Jazzy workspace and passed all runtime gtests; its
remaining failures were limited to clang-format ordering/wrapping and clang-tidy findings in the
new OpenSSL digest helper. The helper now uses `std::array`, typed sizes, a named nibble mask, and
the repository's exact formatting.
