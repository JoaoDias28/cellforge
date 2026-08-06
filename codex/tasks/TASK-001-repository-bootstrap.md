> Follow `AGENTS.md`. Create an ExecPlan when the task spans more than a focused change. Do not implement unrelated later tasks.

# TASK-001 — Repository bootstrap

## Goal
Create the monorepo build/test structure described by the design pack.

## Deliverables

- top-level `Makefile` with `lint`, `test`, `validate-examples`, `ros-build`, and `ros-test` targets;
- Python workspace using a modern lockable package workflow;
- `src/python/cellforge_domain` package and empty tested import;
- ROS 2 workspace with `cellforge_interfaces` placeholder package;
- formatting/lint configuration for Python and C++;
- GitHub Actions jobs for Python validation and ROS Jazzy build;
- developer setup documentation.

## Constraints

- Do not add Isaac Sim as a CI dependency in this task.
- Keep the root commands usable in a clean Ubuntu 24.04 development environment.
- Pin or lock dependencies reproducibly.

## Acceptance

- `make lint` passes.
- `make test` passes.
- `make validate-examples` exists and may initially report schemas/examples not yet wired, but must not falsely claim validation.
- CI configuration is syntactically valid.
