> Follow `AGENTS.md`. Create an ExecPlan when the task spans more than a focused change. Do not implement unrelated later tasks.

# TASK-005 — Component registry and capability resolver

## Goal
Load component packages and resolve cell capability/port dependencies.

## Deliverables

- filesystem component registry;
- duplicate/version conflict detection;
- port endpoint linking;
- mechanical port type compatibility check;
- capability contract/version resolution;
- support-level and execution-mode checks;
- dependency graph report.

## Acceptance

- the pen example resolves required capabilities in simulation mode;
- missing ports, incompatible mechanical ports, unsupported modes, and missing capabilities produce stable validation codes;
- resolver output is deterministic.
