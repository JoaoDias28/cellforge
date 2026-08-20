> Follow `AGENTS.md`. Create an ExecPlan when this task becomes eligible. This task requires Tasks 036 and 037; do not start it before both are merged.

# TASK-038 — Simulation component expansion

## Goal

Expand CellForge beyond the reference pen cell with at least one useful simulated robot-cell
workflow, proving that reusable component and capability contracts support a second process without
copying a pen-specific architecture.

## Prerequisites

- Task 036 is merged with executable qualification evidence;
- Task 037 is merged with the documented observable L0 and supported L2 demo paths;
- the selected workflow has an explicit simulation fidelity target and no implication of physical
  commissioning or production qualification.

## Deliverables

- at least one non-pen workflow, such as pick-and-place, kitting, palletizing, or inspection,
  selected for concrete engineering usefulness;
- reusable component manifests, capability contracts, frames, ports, configuration, simulation
  adapters, and fault catalogs for the selected workflow;
- a canonical cell/project, behavior tree, recipe, and scenarios that run through shared contracts;
- L0 scenarios and, where supported by the selected components, an honest L1/L2 simulation path
  with observable evidence, deterministic seeds, nominal behavior, and failure recovery;
- documentation of the workflow, reused interfaces, modeled limitations, and how to add another
  workflow without simulator-specific branches or direct vendor imports.

## Acceptance

- The additional workflow completes a useful nominal simulation and at least one defined fault and
  recovery path in L0 with reproducible evidence.
- The behavior tree and recipe depend on declared capabilities and ports, not simulator identity,
  vendor-specific imports, or a forked pen-only runtime path.
- Required component IDs, frames, configuration, scene references, and evidence validate together;
  selected fidelity is never higher than the weakest required adapter.
- The workflow is included in the executable qualification and demo surfaces from Tasks 036 and
  037, or the limitation and separate supported path are recorded explicitly.
- Simulation artifacts remain engineering evidence only; no support-level promotion, real-device
  commissioning, production qualification, or functional-safety claim is made.

## Explicit non-goals

- redesigning the canonical runtime, schema, ROS, bundle, or Studio public interfaces without an
  approved compatibility plan;
- adding real hardware drivers or commissioning procedures;
- implementing functional-safety enforcement in application or simulation code.
