> Follow `AGENTS.md`. Create an ExecPlan when the task spans more than a focused change. Do not implement unrelated later tasks.

# TASK-014 — Isaac Sim / Kit extension shell

## Goal
Create the Cell Studio extension shell without implementing full editing.

## Deliverables

- extension metadata and startup/shutdown lifecycle;
- dockable project, validation, and log panels;
- service boundary to pure Python application layer;
- headless import/unit tests for non-UI logic;
- documented Isaac Sim launch command.

## Constraints

- use supported Isaac Sim 6 extension APIs;
- do not duplicate domain validation in UI callbacks.

## Acceptance

- extension loads and unloads without errors in supported Isaac Sim environment;
- missing backend/project produces a useful empty state;
- no project files are modified merely by opening the extension.
