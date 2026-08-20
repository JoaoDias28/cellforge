# Roadmap

The roadmap is organized to produce useful, testable infrastructure before investing heavily in the graphical editor.

## Phase 0 — Repository and contracts

Outcome: reproducible monorepo, schemas, examples, CI, and Codex working rules.

- repository scaffold;
- Python domain package;
- JSON schemas and example validation;
- ROS interface package;
- ADRs and version policy;
- basic CI.

Exit: `make lint test validate-examples ros-build ros-test` passes.

## Phase 1 — Headless platform compiler

Outcome: `cellforge` CLI can create, validate, inspect, and compile a cell project.

- component registry loader;
- cell and component domain models;
- port/frame/capability linker;
- behavior-tree static validator;
- recipe compatibility validator;
- deployment manifest generator;
- structured validation report.

Exit: pen example compiles to a deterministic bundle manifest without Isaac Sim.

## Phase 2 — ROS runtime with mocks

Outcome: full pen workflow executes with contract mocks.

- job gateway;
- state aggregator;
- BehaviorTree.CPP supervisor;
- device/skill SDK;
- mock robot, gripper, fixture, laser, camera, and inspection adapters;
- trace recorder;
- scenario tests.

Exit: nominal and required fault scenarios pass headlessly.

## Phase 3 — Cell Studio MVP

Outcome: engineer can create and edit the reference cell graphically.

- Kit extension shell;
- project open/save;
- component browser;
- add/place/remove component;
- mechanical mount snapping;
- property inspector;
- validation panel;
- simulation launch/control.

Exit: studio round-trips the pen cell without corrupting source and runs nominal simulation.

## Phase 4 — Motion and physical simulation

Outcome: collision-aware simulated pick/load/unload.

- supported robot asset and driver mapping;
- MoveIt configuration;
- motion service;
- MTC pick/load task;
- Isaac Sim robot and gripper adapter;
- product physics and fixture model;
- deterministic scenario runner.

Exit: repeated simulated cycles meet scenario and collision requirements.

## Phase 5 — Pre-hardware software baseline (BASELINE; executable gate pending)

Outcome: the engineering-to-runtime workflow and L0/L2 simulation implementations are assembled,
but the release claim still requires independently executed gates and honest evidence.

- unified frozen-job and trace identity (Task 023);
- canonical BehaviorTree.CPP pen execution (Task 024);
- integrated offline runtime bringup (Task 025);
- signed installable bundle assembly (Task 026);
- genuine Isaac Sim 6 L2 execution (Task 027);
- complete Studio spatial, task, recipe, deployment, and evidence workflows (Tasks 028, 029, 030);
- platform registry, artifacts, approvals, evidence, and result synchronization (Tasks 031, 032);
- software-side qualification workflow and report scaffold (Task 033).

Exit: Task 036 replaces synthetic or hard-coded qualification success with actually executed gates
and evidence. CPU-only, mock-only, and synthetic-event checks cannot satisfy the Isaac Sim 6 L2 gate.

## Phase 6 — Simulation readiness program (IN PROGRESS)

Outcome: establish a deterministic, observable simulation baseline and extend it beyond the reference
pen workflow without claiming physical qualification.

- Task 035: simulation-readiness status, dependency graph, and deterministic green baseline;
- Task 036: executable release qualification with actually run gates and honest evidence;
- Task 037: documented one-command L0 demo and supported Isaac Sim L2 demo path with observable artifacts;
- Task 038: at least one additional useful simulated robot-cell workflow using reusable contracts.

Exit: Tasks 036 and 037 provide executable qualification and observable demo evidence; Task 038
adds a reusable non-pen workflow. Simulation evidence remains engineering evidence only, and
functional safety remains independently enforced and verified outside CellForge software.

## Phase 7 — Hardware integration readiness (PROTOTYPES ONLY)

Outcome: hardware-adapter prototypes and generic contract harnesses are available for future
commissioning planning. Task 034 does not claim real-device commissioning, production qualification,
or safety validation.

- adapter-shaped packages and vendor-interface boundaries from Task 034;
- generic contract, calibration, and failure-path harnesses;
- explicit prerequisites for selected hardware, approved commissioning controls, and independent
  safety evidence before any physical execution.

Exit: a future hardware-integration task must provide real-equipment evidence under approved
commissioning controls and record functional-safety verification separately.

## Phase 8 — Reusable low-code engineering

Outcome: new cells can be assembled from components and skills.

- connection graph editor;
- behavior-tree visual editor integration;
- schema-driven recipe editor;
- component SDK templates;
- deployment manager and rollback UI;
- operator UI;
- support-level/evidence promotion workflow.

## Phase 9 — Advanced perception and optimization

Add only for justified applications:

- ONNX model registry and governance;
- Isaac ROS acceleration;
- synthetic data workflows;
- 3D pose estimation;
- automated cell-layout search;
- cycle-time optimization;
- multi-cell scheduling.
