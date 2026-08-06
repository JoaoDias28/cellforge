> Follow `AGENTS.md`. Create an ExecPlan when the task spans more than a focused change. Do not implement unrelated later tasks.

# TASK-021 — Bundle install, activation, and rollback

## Goal
Install immutable bundles safely on a target cell computer.

## Deliverables

- bundle layout and checksum verification;
- target compatibility preflight;
- versioned release directories;
- atomic activation;
- systemd integration;
- health check and automatic rollback;
- local status CLI.

## Acceptance

- corrupt bundle is rejected;
- failed health check restores previous release;
- active bundle ID is visible to runtime and trace events;
- secrets are resolved locally and absent from bundle files.
