> Follow `AGENTS.md`. Create an ExecPlan when the task spans more than a focused change. Do not implement unrelated later tasks.

# TASK-004 — CellForge CLI

## Goal
Build the headless command-line entry point.

## Commands

- `cellforge project init <path>`
- `cellforge validate <project>`
- `cellforge inspect <project>`
- `cellforge schema list`
- `cellforge example copy pen-engraving <path>`

## Deliverables

- typed CLI with stable exit codes;
- human and JSON output modes;
- project template generation;
- tests using temporary directories.

## Acceptance

- copying and validating the pen example succeeds;
- invalid projects return nonzero status and structured errors;
- commands do not require Isaac Sim or ROS.
