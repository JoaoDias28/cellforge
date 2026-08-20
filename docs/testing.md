# Testing strategy

## 1. Test pyramid

### Pure unit tests

- schema models;
- validators;
- frame/port linking;
- compatibility resolver;
- recipe approval rules;
- bundle hashing;
- fault mapping;
- behavior-tree helper nodes.

### Contract tests

Run the same suite against every adapter implementation:

- readiness;
- valid command;
- invalid command;
- busy rejection;
- timeout;
- cancellation;
- communication loss;
- restart reconciliation;
- stable fault mapping.

### ROS integration tests

- action/service/topic contracts;
- lifecycle/startup order;
- behavior-tree execution;
- state aggregation;
- trace propagation;
- cancellation propagation.

### Scene and simulation tests

- USD loads without errors;
- component instance IDs match `cell.yaml`;
- required frames exist;
- collision geometry present;
- scenario outcomes;
- deterministic seed replay;
- bounded performance.

### Hardware-in-the-loop tests

- real protocol communication;
- I/O handshake;
- robot trajectory execution at commissioning settings;
- machine program selection;
- failure and restart behavior.

### Production acceptance

- cycle capability;
- process quality;
- traceability;
- fault recovery;
- operator workflow;
- independent safety validation evidence.

## 2. CI gates

Pull requests must run:

- formatting and static analysis;
- Python and C++ unit tests;
- schema validation for all examples;
- package/license scan;
- ROS build and tests in supported container;
- headless domain/compiler tests.

Isaac Sim tests may run on a dedicated GPU runner. PRs that affect scene/simulation behavior require that check before release even when normal contributors cannot run it locally.

Task 018 adds `make studio-simulation-check` for deterministic CPU-only lifecycle, seed replay,
fidelity, fault, trace/assertion, and evidence coverage. The separate Isaac Sim 6 headless command
in `docs/simulation.md` remains required integration evidence and must be reported unavailable—not
passing—when no supported Isaac runtime exists.

Task 019 adds `make motion-service-check` for planner-neutral interfaces, canonical planning-scene
identity, reference kinematics/configuration, named safe poses, and fake-controller configuration.
The ROS Jazzy gate additionally compiles MoveIt/MTC and runs the fake-planner C++ suite. Plan-only
success is not hardware execution evidence, and Task 020 physical simulation is outside this gate.

Task 020 adds `make pen-physical-sim-check`. It verifies required scene geometry/physics metadata,
bounded seeded spawning, grasp state, fixture seating, planner-neutral pick/load/process-safe/unload
requests, collision results, stable dropped/seating faults, and an exactly reproducible 100-seed
CPU report. The separate Isaac Sim 6 command in `docs/simulation.md` is required for actual PhysX
evidence and must be reported unavailable when a supported runtime/GPU runner is absent. CPU checks
must never be relabeled as L2 execution, hardware, laser-process, or functional-safety evidence.

Task 024 adds the canonical C++ pen-runtime contract suite. It executes the unchanged canonical XML
through BehaviorTree.CPP and the supervisor preflight validator for all ten Task 013 scenarios,
exercises real typed asynchronous leaves against ROS action servers, verifies cancellation and
process uncertainty, and compares timestamp-free runtime node ordering/final outcomes with the
Python oracle's golden traces. The Python runner is not a production execution path.

## 3. Required reference scenarios

Pen engraving MVP:

1. nominal pass;
2. no pen;
3. pose outside limit;
4. fixture not seated;
5. laser not ready;
6. laser cycle timeout;
7. inspection text mismatch;
8. operator cancel before process starts;
9. communication loss after process start, outcome unknown;
10. unhealthy safety status prevents job acceptance.

Task 013 stores all ten source scenarios under `examples/pen_engraving/scenarios/`. Its L0 runner
must pass them deterministically, allow exact replay by the stored seed, issue no adapter command
when safety status is unhealthy, and issue exactly one process-cycle command when communication is
lost after process start. The latter ends in `OUTCOME_UNKNOWN`; it is never automatically retried.

## 4. Golden traces

For selected scenarios, store normalized expected event sequences. Exclude nondeterministic timestamps while preserving order, state, command IDs, result codes, and required evidence.

The pen L0 golden traces live under `examples/pen_engraving/golden_traces/`. JSON and JUnit reports
are generated outputs and are not source artifacts; golden traces are reviewed source evidence.

## 5. Performance budgets

Budgets are defined per cell and skill. The platform should detect regressions rather than impose one global cycle-time value.

## 6. Schema and example validation

`make validate-examples` validates every canonical schema as JSON Schema Draft 2020-12, converts
the pen example YAML documents to JSON-compatible values, validates them against the schema selected
by document kind and `schema_version`, and then applies the pure Pydantic domain contracts.

The same check is available without Make:

```bash
uv run --frozen python -m cellforge_domain.example_validation --schemas schemas --examples examples/pen_engraving
```

Recipe schema paths, recipe document paths, recipe-to-cell compatibility, and deployment-profile
paths are checked relative to `cell.yaml`. A failure line includes its source file and JSON Pointer,
stable rule/code, and human-readable message. This validation never authorizes physical execution or
implements a safety function.

## 7. Compiler and bundle-manifest tests

Task 006 compiler tests run headlessly and deterministically. They cover:

- byte-identical repeated manifests and recomputation of the SHA-256 bundle ID;
- recipe changes altering both the recipe digest and bundle ID;
- exact component, adapter, runtime-package, recipe, and task freezing;
- simulated-only components, unapproved recipes, and unavailable evidence blocking production;
- malformed project input and invalid source revisions returning structured findings;
- missing behavior-tree references failing instead of silently succeeding;
- immutable manifest output refusing to overwrite an existing file;
- the CLI build success and output-failure paths.

These are compiler/domain tests. They are not hardware, ROS, Isaac Sim, or safety-validation evidence.

## 8. Task 025 integrated runtime acceptance

`make integrated-runtime-check` builds the ROS workspace and runs the `cellforge_bringup`
`launch_testing` suite in Jazzy. The suite launches the real L0 graph and verifies `READY`, loopback
HTTP submission, live step and exact bundle identity, nominal completion, cancellation, injected
fault propagation, semantic acknowledgement, unavailable maintenance service, local SQLite job and
trace persistence, fresh heartbeats/restart readiness, and operation with no platform dependency.

Pure loader/compiler tests separately cover canonical bundle identity, tampering, path containment,
runtime-graph determinism, package/entrypoint validation, and fail-closed L2 selection.

## 9. Task 026 signed assembly acceptance

`make bundle-assembly-check` assembles the reference compiler output twice with one external
ephemeral Ed25519 test key and compares every file byte-for-byte. It verifies the assembled release
against a separately provisioned public-key directory, rejects a checksum-repaired but invalid
signature, and installs two assembled releases through the real bundle-agent flow. The latter test
forces candidate health failure and verifies that the former release and its generated environment
are restored. These checks are deterministic unit/integration evidence, not a real systemd or
hardware qualification.

## 10. Task 036 executable software release qualification acceptance

`make release-qualification-check` runs the real L0 headless scenario runner, the platform
acceptance probe, bundle assembly and agent verification, restart reconciliation, and stale-device
probes. Each result records the command or probe artifact and its SHA-256 digest in an integrity-
protected `SoftwareReleaseQualificationReport`.

The command covers all nine categories: `nominal`, `fault`, `cancel`, `timeout`, `restart`,
`corrupt-bundle`, `offline-platform`, `stale-device`, and `uncertain-process`. The L0 rows are
derived from the generated headless JSON report, including seeds, final status, failures, and
trace event types. Bundle tampering must be rejected by the existing agent verifier, and platform
results must come from observed command output rather than constants.

Task 027 L2 is deliberately external. Supply `--l2-report <path>` to validate an actual Isaac Sim
6/OpenUSD/PhysX report with CUDA identity, the canonical scene digest, 100 unique seeds, replay
integrity, runtime/adapters provenance, and all three required PhysX faults. Without that report,
CI prints `L2 unavailable`, writes `overall_passed: false`, and may complete its L0 evidence probe;
`--require-l2` returns non-zero. CPU/model/mock evidence, missing evidence, tampered evidence, and
fidelity relabeling never become L2 passes.

Simulation qualification remains engineering verification only. It does not qualify real hardware,
physical process quality, or independent functional safety; those boundaries remain external.

## 11. Task 034 hardware adapter and commissioning verification

`python scripts/verify_hardware_adapters.py` executes the acceptance probe for real hardware adapters:

1. **Parity Check:** Verifies zero simulation-specific branches or overrides in `behavior_tree.xml` and `recipe.yaml`.
2. **Generic Contract Suite:** Executes all 6 contract scenarios (nominal, invalid input, fault, busy rejection, timeout, cancellation, restart reconciliation) across all 6 physical device adapters.
3. **On-Cell Commissioning Suite:** Runs 17 individual bench and in-cell commissioning acceptance tests covering nominal and fault paths for robot motion, gripper, fixture clamp/seating, 2D vision, laser marker, and safety status.
4. **Uncertain-Outcome Verification:** Asserts that socket timeouts or communication loss during active laser firing explicitly return `outcome_certain = False` and `laser.process.outcome_unknown`.
5. **Safety Refusal Boundary:** Verifies that unready or faulted safety hardware refuses cell operation while keeping safety enforcement on rated hardware relays.
