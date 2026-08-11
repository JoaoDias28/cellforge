# Task 025 — Integrated offline runtime bringup

## Goal

Launch the complete reference pen cell as one offline ROS 2 Jazzy L0 runtime that reaches `READY`,
accepts the canonical job through the loopback operator API, preserves live frozen identity and
step state, and durably records the terminal result and trace.

## Scope

Included: a `cellforge_bringup` package; immutable compiler-generated runtime graph metadata;
real package/executable identities for the reference L0 adapters and services; explicit L0/L2
fidelity selection with fail-closed unavailable L2 behavior; a deterministic L0 motion backend;
read-only mock safety status; the fixed `/cell/operator_action` semantic recovery coordinator;
launch/operator integration coverage for readiness, nominal operation, faults, cancellation,
restart reconciliation, persistence, identity, unavailable recovery, and offline operation.

Excluded: Task 026 signed/installable bundle assembly, Task 027 Isaac Sim L2 implementation,
hardware/vendor adapters, platform synchronization, production approval, and any functional-safety
logic. Safety health remains a read-only standard-control prerequisite; rated hardware remains
authoritative.

## Current state

`main` was clean at exact prerequisite merge `f1d6c34fe6bcabf3cd53d9da1351990f5a05ea24` and the
Task 025 branch was created from that commit. Task 024 supplies the canonical C++ pen plugin and
immutable plugin loading, but deliberately excludes integrated launch. Existing gateway,
supervisor, state/trace, operator API, bundle agent, motion service, and contract mocks are tested
individually. The reference deployment still names nonexistent per-device simulation packages,
the mock launch does not match the canonical `/device/<instance>/<capability>` endpoints, no node
serves `/cell/operator_action`, and no one composes or configures the full runtime.

Pre-edit evidence on 2026-08-11: direct Make-equivalent Ruff, strict mypy, pytest, and example
validation passed (340 passed, one pre-existing Windows symlink-privilege skip; 10 canonical
schemas, 7 component schemas, 22 YAML documents). GNU Make and native ROS 2 are absent on the
Windows host. Docker Desktop and the local `ros:jazzy-ros-base` image are available for exact ROS
gates after implementation.

## Design

The deployment profile declares the requested simulation fidelity plus concrete service and
adapter package/executable identities. Compilation verifies those identities against selected
component adapters and freezes a canonical runtime graph containing the bundle-bound cell ID,
fidelity, fixed topics/actions/services, required component instances, tree root, adapter config,
recovery catalog, and executable declarations. The graph contributes to the bundle ID and is read
only from the active manifest at launch. No ROS name, executable, or device command comes from an
operator request.

`cellforge_bringup` independently validates canonical manifest hashing, bundle containment,
required runtime keys, exact supported endpoint names, package identities, and requested fidelity
before returning launch actions. L0 selects `cellforge_motion`'s deterministic contract planner
and `cellforge_mock_adapters`; an L2 request is refused as unavailable until Task 027 supplies a
genuine adapter set. This is an honest fidelity boundary, not an L2 placeholder.

The runtime coordinator publishes the configured read-only mock safety status, synchronizes the L0
motion scene using frozen cell/USD identities, and serves `/cell/operator_action`. It loads the same
immutable semantic catalog as the operator API, matches action ID/kind/fault ID to current cell
state, and returns stable certain refusal codes for stale, inapplicable, unsupported, or invalid
requests. It cannot clear/bypass safety state and cannot invent recovery success when another
service is unavailable.

The integrated launch starts contract adapters, motion, coordinator, state aggregator, durable
recorder, supervisor/plugin, gateway, and loopback operator API with databases and credentials from
cell-local mutable storage outside the bundle. ROS launch tests construct a temporary immutable
test bundle, run the real graph, drive HTTP and typed ROS interfaces, and inspect SQLite results.

No new production dependency is planned. `launch_testing` is test-only and supplied/maintained by
the ROS 2 Jazzy distribution; it can be removed with the launch integration tests without changing
the runtime.

## Work sequence

1. Extend deployment/domain/compiler contracts with deterministic runtime graph generation and
   real L0 identities; acceptance: repeated compiles are byte-identical and invalid fidelity,
   endpoint, package, or entrypoint declarations fail closed.
2. Add deterministic L0 motion and read-only safety/status adapter edges; acceptance: contract
   tests cover nominal, cancellation, timeout/fault, restart certainty, scene identity, and L2
   refusal without claiming physics or safety enforcement.
3. Add `cellforge_bringup` manifest loader, recovery coordinator, and integrated launch;
   acceptance: immutable bundle validation configures every service and reaches `READY` offline.
4. Add full launch/operator acceptance tests; acceptance: nominal HTTP job shows live step/identity,
   exact terminal result/trace persist, and fault, cancellation, restart, unavailable recovery,
   persistence, identity mismatch, and platform-loss paths return stable outcomes.
5. Update architecture/runtime/deployment/testing documentation and this plan with actual results.
6. Run all local/container/hosted gates, inspect and commit Task 025 only, push, open a ready PR,
   fix only scoped failures, merge only green/mergeable, and fast-forward local `main`.

## Validation

- `make lint`
- `make test`
- `make validate-examples`
- `make ros-build`
- `make ros-test`
- `make integrated-runtime-check`
- focused compiler/runtime-graph determinism and refusal tests
- launch readiness and nominal loopback operator API test
- launch fault, cancellation, recovery-unavailable, restart/persistence, exact-identity, and offline test
- `git diff --check`, cached diff review, clean post-commit and post-merge status

## Risks and rollback

Startup order and mixed rclpy/rclcpp/FastAPI concurrency can expose discovery races; readiness and
tests use bounded waits and stable failure codes. Duplicate camera capability nodes share one
component identity, so aggregation must remain instance-based. Cancellation is only a standard
control request and outcome certainty stays conservative. Reverting Task 025 removes the additive
bringup/runtime metadata and L0 planner while leaving every Task 024 package usable independently;
there is no persistent schema migration beyond existing SQLite forward-compatible tables.

## Progress

- [x] 2026-08-11 — instructions, exact prerequisite merge/history, architecture, task scope, clean
  baseline, branch, and pre-edit checks verified.
- [x] 2026-08-11: immutable runtime graph and real identities complete.
- [x] 2026-08-11: L0 motion/safety edges and fidelity refusal complete.
- [x] 2026-08-11: bringup/recovery coordinator and launch complete.
- [x] 2026-08-11: integrated acceptance coverage and documentation complete.
- [ ] full validation complete; commits, ready PR, green merge, and local main sync pending.

## Decisions

- 2026-08-11 — represent L2 as explicitly unavailable rather than retaining nonexistent adapter
  package names or relabeling L0/CPU behavior; Task 027 owns genuine Isaac Sim L2 runtime work.
- 2026-08-11 — freeze the complete runtime graph into the canonical manifest so startup does not
  infer mutable ROS names or package choices from the live graph.
- 2026-08-11 — keep cell-local databases/auth outside the immutable bundle and keep all platform or
  internet connectivity outside the launch dependency graph.
- 2026-08-11: encode hyphens as underscores only at ROS graph-name boundaries while preserving
  immutable component IDs in manifests, messages, traces, and recovery fault identities.
- 2026-08-11: refresh adapter heartbeat timestamps without changing semantic state; republishing a
  stale snapshot timestamp correctly caused fail-closed readiness loss.
- 2026-08-11: fix direct Task 024 prerequisites exposed by the real graph: safe-pose naming, generic
  select-program payload decoding, terminal active-job clearing, service readiness, and the
  cancellation/result race.

## Results

The reference runtime now starts 14 local processes from the verified bundle graph and reaches
`READY` in clean ROS 2 Jazzy. The loopback API completes the canonical job with observable live step
and exact identity, persists job/trace SQLite records, propagates cancellation without crashing,
restores readiness with fresh heartbeats, raises the injected laser timeout, acknowledges it without
mutating device state, and returns a certain unavailable result for the missing maintenance service.
L2, identity mismatch, and critical-file tampering fail before launch.

Validation on 2026-08-11: exact `make lint`, `make test` (345 passed), `make validate-examples`
(10 canonical schemas, 7 component schemas, 22 YAML documents), `make integrated-runtime-check`
(20 pure tests plus 1 full launch test), and clean `make ros-build` (11 packages) passed in the
disposable Jazzy container. The final `make ros-test` result is 121 tests with zero errors, failures,
or skips. ROS emitted only the upstream Jazzy `tl_expected` deprecation warning from MoveIt
dependencies.
