> Follow `AGENTS.md`. Create and maintain the ExecPlan at `codex/execplans/TASK-035-simulation-readiness-bootstrap.md`. Do not implement Tasks 036–038 in this task.

# TASK-035 — Simulation readiness program bootstrap

## Goal

Establish an honest, deterministic simulation-readiness baseline after the software and
hardware-adapter prototype work. Make the repository ready for parallel executable-qualification
and simulation-demo work without implying that real devices, production hardware, or functional
safety have been qualified.

## Prerequisites

- Task 033 is merged and its software-side artifacts are available for review;
- Task 034 is merged, but its deliverables are treated as hardware-adapter prototypes and generic
  contract harnesses only;
- the independent functional-safety architecture remains outside CellForge software and is not
  replaced by simulation, mocks, or application-level status checks.

## Deliverables

- a task and ExecPlan that define the simulation-readiness follow-on program;
- `CODEX_TASK_INDEX.md` entries for Tasks 035–038 with dependencies that allow Tasks 036 and 037
  to proceed in parallel after Task 035, while requiring both before Task 038;
- README and roadmap status that distinguishes software/simulation readiness, adapter prototypes,
  real-device commissioning, production qualification, and independent safety verification;
- deterministic Studio calibration tests that inject the existing service clock at every validation
  boundary while retaining the expired-calibration rejection assertion;
- no changes to runtime, schema, ROS, bundle, qualification implementation, evidence JSON,
  component support levels, CI, hardware logic, or public Studio interfaces.

## Acceptance

- The six-test spatial-configuration module passes on any host date, including the test that
  asserts `studio.calibration-expired`; no expiry validation is skipped or weakened.
- The full Python test suite is green apart from explicitly documented platform skips.
- `make lint`, `make test`, and `make validate-examples` pass where the environment supports them;
  otherwise their exact underlying commands and environmental blockers are recorded.
- README and ROADMAP do not claim that Task 034 commissioned real equipment or production-qualified
  hardware. They state that functional safety remains independently enforced and verified.
- The task index contains these exact dependency relationships:
  - Task 035 depends on Tasks 033 and 034;
  - Task 036 depends on Task 035;
  - Task 037 depends on Task 035;
  - Task 038 depends on Tasks 036 and 037.
- Tasks 036–038 remain specifications only; their implementation, qualification gates, demo
  commands, new evidence, and additional simulated workflow are not delivered by Task 035.
- The completed change is committed with subject `task(035): bootstrap simulation readiness program`.

## Explicit non-goals

- replacing synthetic or hard-coded release qualification (Task 036);
- implementing a one-command L0 or Isaac Sim L2 demo (Task 037);
- adding another simulated robot-cell workflow or component family (Task 038);
- commissioning physical equipment, promoting component support levels, or making any production
  or functional-safety claim.
