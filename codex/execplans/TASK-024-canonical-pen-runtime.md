# Task 024 — Canonical pen BehaviorTree.CPP runtime

## Goal

Execute the one canonical pen behavior tree with the production C++ supervisor and typed ROS
clients, while retaining the Python L0 executor only as a deterministic trace oracle.

## Scope

Included: a `cellforge_pen_bt_nodes` ROS package for every canonical pen leaf; asynchronous typed
action clients with deadlines and cancellation; stable failure and outcome-certainty propagation;
bundle-declared plugin loading; machine-readable node/port manifests; compiler validation of node
types, ports, blackboard mappings, and plugin declarations; canonical runtime scenarios; and
runtime/oracle normalized-trace comparison.

Excluded: Task 025 integrated launch/bringup, hardware adapters, vendor protocols, Isaac Sim work,
bundle signing/assembly, operator recovery expansion, or safety enforcement. Safety state remains a
read-only standard-control refusal input; independent rated hardware remains authoritative.

## Current state

`main` is clean at Task 023 merge `240d02c28dee1e889f46473a77ffc0c0af62ce9b` and contains all
Task 024 prerequisites. `cellforge_supervisor` runs BehaviorTree.CPP with built-in `CellReady` and
`ExecuteSkill` nodes, validates frozen job identity and basic ports, and propagates cancellation.
The canonical pen XML names fourteen unimplemented leaves. Task 013's Python executor executes the
same XML against deterministic L0 adapters and owns ten golden scenarios (one nominal and nine
fault/cancellation cases); it is explicitly test infrastructure, not the production runtime.

Pre-edit evidence on 2026-08-11: Ruff format/check and both strict mypy scopes pass; pytest reports
328 passed and one Windows symlink skip; example validation reports ten canonical schemas, seven
component schemas, and 22 YAML documents. GNU Make and ROS 2 are not installed on this Windows
host, and Docker Desktop's Linux engine is stopped, so literal Make/ROS gates are unavailable
locally. Task 023's hosted Ubuntu/Jazzy build is green; Task 024 hosted CI will be authoritative.

## Design

The deployment profile declares behavior-tree plugins by package, library, and a source node
manifest. Compilation validates and freezes each manifest, adds a digest-bearing plugin reference
to the immutable bundle manifest, and rejects plugin packages absent from the profile's native
packages. The supervisor reads only the active immutable bundle manifest, verifies each frozen node
manifest digest, resolves the declared library beneath the declared ROS package prefix, and loads
that library before accepting work. There is no arbitrary library-path parameter.

The node manifest declares each registration name plus typed input/output ports. The Python
compiler validates the XML against BehaviorTree.CPP control nodes, supervisor built-ins, and only
the declared plugin manifests. It rejects unknown nodes, unknown or missing ports, invalid output
mappings, unresolved input blackboard keys, duplicate node declarations, mismatched package/library
identity, and undeclared plugin packages before writing a bundle.

`cellforge_pen_bt_nodes` uses fast synchronous conditions/transformations and asynchronous
`StatefulActionNode` clients for `LocateObject`, `ExecuteManipulation`, `MoveToPose`,
`ExecuteProcess`, `InspectObject`, and the canonical `ExecuteSkill` bridge where no more specific
interface exists. Every active ROS action receives a unique command ID, trace ID where its contract
supports it, and a positive steady deadline. Halting requests action cancellation. Stable result
codes/messages are preserved on the blackboard. A process result or post-dispatch timeout with
unknown certainty sets an explicit blackboard latch; the supervisor reports `OUTCOME_UNKNOWN` and
never retries or continues to inspection.

The canonical XML remains the sole runtime tree. Runtime integration tests use typed fake action
servers and scripted scenario outcomes to exercise the C++ factory/supervisor path for all ten
canonical scenarios, cancellation, safety refusal, and process uncertainty. A normalized projection
of runtime leaf ordering/outcomes is compared with Task 013's golden oracle traces. Oracle code is
not imported by or linked into a production ROS package.

No new hardware or safety authority is introduced. If an additional production dependency is
required for immutable manifest parsing, its license, maintenance, reason, and removal path will be
documented before completion.

## Work sequence

1. Add deployment/bundle plugin models and node-manifest validation; acceptance: compiler tests
   reject unknown nodes, ports, mappings, undeclared packages, and malformed manifests.
2. Add immutable manifest-driven supervisor plugin loading and uncertainty result mapping;
   acceptance: tests prove only declared/digest-matching package libraries load and no capability
   command is sent after validation refusal.
3. Implement `cellforge_pen_bt_nodes` and its machine-readable manifest; acceptance: package tests
   cover every leaf, typed goals/results, deadlines, stable failures, cancellation, and uncertainty.
4. Run the canonical XML through the C++ runtime scenario harness; acceptance: nominal plus all
   nine fault/cancellation scenarios match required final outcomes, safety refusal dispatches no
   process action, cancellation reaches an active goal, and uncertain processing executes once.
5. Add runtime/oracle normalized-trace comparison and documentation; acceptance: required node
   ordering and final outcomes agree for all ten scenarios without making Python a runtime path.
6. Run all available local and hosted gates, inspect/stage Task 024 only, commit, push, open a ready
   PR, fix scoped CI failures, merge only green/mergeable, and fast-forward local `main`.

## Validation

- `make lint` (or its exact direct command bodies on this Windows host)
- `make test` (with a repository-external writable pytest base on this host)
- `make validate-examples`
- `make ros-build`
- `make ros-test`
- canonical runtime scenario command/test for all ten Task 013 scenario documents
- focused compiler invalid-node/port/mapping/plugin tests
- focused cancellation, safety-refusal, timeout, stable-failure, and uncertainty tests
- runtime/oracle normalized trace comparison
- `git diff --check`, cached diff review, clean post-commit and post-merge status

## Risks and rollback

BehaviorTree.CPP plugin loading and ROS action callbacks are platform-sensitive; tests must compile
on Jazzy and avoid blocking the tick thread. Compiler validation and runtime registration must share
one reviewed manifest without silently diverging. Cancellation is a request, not a safety-rated
stop, and process certainty must remain conservative. Reverting Task 024 removes the additive
plugin declarations/package and restores the Task 023 supervisor; no persistent-data migration or
public action break is planned.

## Progress

- [x] 2026-08-11 — instructions, prerequisite history, architecture, task scope, and baseline read
  and verified; Task 024 branch created.
- [x] 2026-08-11 — compiler plugin contract and validation complete.
- [x] 2026-08-11 — immutable supervisor plugin loading and uncertainty mapping complete.
- [x] 2026-08-11 — canonical pen plugin package and tests complete.
- [x] 2026-08-11 — ten runtime scenarios and oracle trace comparison complete.
- [ ] full local/hosted validation, task commits, ready PR, green merge, and local main sync complete.

## Decisions

- 2026-08-11 — interpret the canonical ten scenarios exactly as Task 013 and `docs/testing.md` do:
  one nominal plus nine fault/cancellation scenarios; retain separate focused assertions for
  cancellation, safety refusal, and uncertainty.
- 2026-08-11 — load plugins only from digest-bearing references in the active bundle manifest;
  arbitrary absolute plugin paths would violate immutable deployment and compiler/runtime parity.
- 2026-08-11 — keep Python as an offline oracle and report generator only; production execution
  remains entirely in BehaviorTree.CPP and ROS C++.

## Results

Implementation and local validation are complete. The compiler freezes digest-bearing plugin
manifests and rejects invalid node/port/blackboard/plugin declarations. The supervisor loads only
bundle-declared package libraries and preserves process uncertainty. The new C++ plugin owns all
fourteen canonical leaves with typed, asynchronous ROS clients, steady deadlines, cancellation,
and deterministic result propagation. No Task 025 bringup, hardware integration, or software
safety enforcement was added.

Windows has no GNU Make, so the non-ROS Make wrappers were unavailable; their exact command bodies
passed: Ruff checked 235 files, mypy checked 80 runtime/test and 15 Studio sources, pytest reported
340 passed and one pre-existing Windows symlink-privilege skip, and example validation covered 10
canonical schemas, 7 component schemas, and 22 YAML documents. In a disposable ROS Jazzy container,
the literal `make ros-build` and `make ros-test` targets passed for all 10 packages with 113 tests,
zero errors, zero failures, and zero skips. The nominal oracle and all ten canonical scenarios
passed; native runtime tests cover compiler rejection, cancellation, safety refusal with zero
process dispatch, uncertain processing with one dispatch, and normalized runtime/oracle trace
agreement. `git diff --check` passed. Publication and hosted CI remain pending.
