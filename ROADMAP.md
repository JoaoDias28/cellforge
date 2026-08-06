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

## Phase 5 — Pen engraving hardware integration

Outcome: commissioned first physical cell.

- selected robot hardware adapter;
- camera/vision implementation;
- fixture I/O adapter;
- laser adapter using documented automation interface;
- independent safety system integration/status;
- calibration workflows;
- commissioning and production acceptance evidence.

Exit: approved production acceptance criteria met. Simulation alone cannot satisfy this phase.

## Phase 6 — Reusable low-code engineering

Outcome: new cells can be assembled from components and skills.

- connection graph editor;
- behavior-tree visual editor integration;
- schema-driven recipe editor;
- component SDK templates;
- deployment manager and rollback UI;
- operator UI;
- support-level/evidence promotion workflow.

## Phase 7 — Advanced perception and optimization

Add only for justified applications:

- ONNX model registry and governance;
- Isaac ROS acceleration;
- synthetic data workflows;
- 3D pose estimation;
- automated cell-layout search;
- cycle-time optimization;
- multi-cell scheduling.
