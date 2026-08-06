> Follow `AGENTS.md`. Create an ExecPlan when the task spans more than a focused change. Do not implement unrelated later tasks.

# TASK-017 — Connection authoring and validation UI

## Goal
Create typed mechanical, software, I/O, and modeled-safety connections.

## Deliverables

- port browser/graph;
- compatible mechanical snap preview;
- logical edge creation;
- distinct safety presentation and disclaimer;
- validator integration;
- source persistence.

## Acceptance

- incompatible ports cannot be silently connected;
- mechanical connection updates the spatial relationship and cell graph coherently;
- safety edges are marked modeled-only and never generate ordinary executable wiring.
