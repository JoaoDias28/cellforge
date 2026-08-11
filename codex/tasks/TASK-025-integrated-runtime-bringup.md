> Follow `AGENTS.md`. Create an ExecPlan. Do not implement unrelated later tasks.

# TASK-025 — Integrated runtime bringup

## Goal
Compose one complete, offline-capable L0 cell runtime from the implemented services.

## Deliverables
- `cellforge_bringup` package for gateway, supervisor, state, trace, operator, motion, plugins, and selected adapters;
- real package and entrypoint identities in component manifests and deployment profiles;
- fidelity-aware selection between L0 and L2 simulation adapters;
- standard-control `/cell/operator_action` recovery coordinator with semantic catalog validation;
- immutable generation of topics, endpoints, required devices, tree roots, and bundle identity;
- full ROS launch and operator-API integration tests.

## Acceptance
- a clean Jazzy environment launches the reference L0 cell and reaches `READY`;
- the operator API submits the canonical nominal job and observes live step and identity state;
- the completed result and exact trace persist locally;
- required faults, cancellation, restart, and unavailable recovery services fail coherently;
- platform/internet loss does not affect local operation.
