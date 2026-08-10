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
