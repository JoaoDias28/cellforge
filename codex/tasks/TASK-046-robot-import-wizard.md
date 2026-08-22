> Follow `AGENTS.md`. Create the required ExecPlan before implementation. Do not implement Tasks 047–048 in this task.

# TASK-046 — Robot import wizard

## Goal

Provide a guided, deterministic import path for supported robot descriptions in URDF/Xacro,
MJCF, and articulated USD. The wizard must produce a reviewable simulation-only component that
conforms to the reusable robot contract without silently guessing joints, frames, limits, or
licenses.

## Prerequisites

- Task 045 is merged with the reusable robot model and simulation-adapter contract;
- Tasks 014, 015, 027, 041, and 044 are merged with Kit/OpenUSD project services, schema forms,
  simulation evidence, and experiment identity;
- supported Isaac Sim importers, ROS `xacro` tooling, and OpenUSD APIs can be invoked in a
  controlled engineering environment; no custom importer is authorized where a supported tool
  exists.

## Concrete deliverables

- a source-selection and preview wizard for URDF, Xacro, MJCF, and articulated USD;
- importer stages for parse/version, links/joints, root and tool frames, limits, visual/collision
  assets, materials, controller mapping, licenses/provenance, and simulation fidelity;
- use of Isaac Sim URDF/MJCF/USD importer tooling and ROS `xacro` preprocessing where required,
  with tool versions/arguments captured in the import report;
- deterministic component package output with `component.yaml`, referenced assets, model contract,
  configuration schema, provenance/import report, and simulation-only support metadata;
- preview, validation, explicit Save, failure recovery, and tests for malformed, ambiguous,
  unsupported, missing-license, and asset-path cases.

## Public interface and schema decisions

- Add `RobotImportRequest`, `RobotImportPreview`, `RobotImportChoice`, and `SaveRobotImport`
  application-service contracts. A request names source type/path, importer version/profile,
  explicit frame/joint choices, output package path, and simulation target.
- Add `schemas/robot_import_manifest.schema.json` containing source type, source digest,
  importer/tool versions and arguments, normalized model digest, generated asset refs, license
  provenance, choices, warnings, and declared simulation-only support.
- Accepted source types are exactly `urdf`, `xacro`, `mjcf`, and `articulated_usd`. Xacro is
  expanded through the installed ROS `xacro` tool into a temporary deterministic URDF; the
  wizard must not implement a second macro parser. MJCF and USD are handed to the supported
  Isaac/OpenUSD importer APIs.
- Output `component.yaml` references the Task 045 robot model schema and exact visual/collision
  assets. The source and import manifest are provenance/source artifacts; generated USD/model
  outputs are reproducible and content-addressed, not hand-edited canonical alternatives.
- Preview never writes a component package or project scene. Explicit Save validates the package,
  license/provenance, asset containment, model contract, and optional paired project references.
  Automatic names/paths/defaults are used only when unambiguous; ambiguous root/tool/joint or
  collision choices require an explicit choice.

## Canonical artifacts and Save-after-preview

The import output must integrate with `cell.yaml` as the operational graph and USD as the spatial
scene without replacing BehaviorTree.CPP XML, `recipes/`, or `scenarios/` as their canonical
sources. Import previews and generated project references remain in memory until explicit
Save-after-preview validates and persists them.

## Acceptance tests

- Valid URDF, Xacro, MJCF, and articulated-USD fixtures produce deterministic previews with the
  expected joints, frames, limits, collision/visual refs, tool provenance, and model digest.
- Malformed source, unsupported version/feature, macro expansion failure, missing root, duplicate
  joint/frame, invalid limit, missing asset, path escape, ambiguous tool frame, or unavailable
  importer returns a structured failure/unavailable result and cannot Save.
- Preview leaves the source directory, component registry, project `cell.yaml`, USD scene,
  recipes, scenarios, and package outputs unchanged. Explicit Save writes a validated package;
  injected failure leaves no partial package and reports recovery instructions.
- Imported output passes the Task 045 model/component validation and is runnable only through the
  simulation adapter. Its support level is `simulated`; no hardware adapter, production mode, or
  safety claim is generated.
- Same source/tool/profile/choices produce identical normalized manifest and model/asset identity;
  a changed source digest or importer version is visible and cannot be silently reused.
- Add one success and failure test per source family, plus invalid/ambiguous, license, no-write,
  deterministic, and simulation-only tests. Real Isaac importer probes run on the supported Kit
  runner; unavailable tooling is explicit.

## Explicit non-goals

- writing a custom URDF/Xacro/MJCF parser, physics engine, kinematics solver, CAD repairer, or
  visual/material authoring system;
- adding real hardware drivers, controller commissioning, payload/reach certification, or safety
  enforcement;
- mutating a live project automatically or making an imported robot production-eligible;
- importing arbitrary formats beyond the four named source families.

## Relevant documentation

- `SYSTEM_SPEC.md`, sections 3, 6–8, 10–11, 15, 18–21;
- `docs/architecture.md`, sections 2–8, 12–14;
- `docs/cell-studio.md`, sections 1–6 and 11–13;
- `docs/simulation.md`, sections 1–3, 6, 8–14;
- `docs/component-sdk.md`, `docs/testing.md`, and `schemas/component.schema.json`;
- `codex/tasks/TASK-045-reusable-robot-simulation-runtime.md` and `TASK-027-isaac-l2-runtime-integration.md`.

## Required checks

- Add and run `make robot-import-wizard-check` (or the documented underlying locked `uv`
  command) for all four source families, invalid/ambiguous input, determinism, provenance, and
  no-write preview;
- run `make lint`, `make test`, and `make validate-examples`;
- run reusable robot, Studio schema, simulation, and supported Isaac/OpenUSD importer checks;
  report missing Kit/importer tooling as unavailable;
- run `git diff --check` and verify generated assets are contained, reproducible, and simulation-only.

## Safety and fidelity limits

An imported robot is an engineering simulation asset. The wizard cannot connect to a robot
controller, authorize physical motion, emit safety signals, validate a risk assessment, or claim
hardware accuracy. Actual fidelity is the observed importer/adapter/backend result; a high-fidelity
source description does not make the output physically qualified.

Any imported or primitive-built robot introduced by later tasks remains simulation-only, and
functional safety remains independent of CellForge software and simulation.

## Required ExecPlan

Before editing, create `codex/execplans/TASK-046-robot-import-wizard.md` using `PLANS.md`.
Document supported source/tool versions, importer boundary, provenance/schema, deterministic
generation, explicit choices, Save-after-preview and failure recovery, tests, safety/fidelity
limits, and rollback. Update progress per source family and stop before Task 047.
