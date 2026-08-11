> Follow `AGENTS.md`. Create an ExecPlan. Do not implement unrelated later tasks.

# TASK-023 — Execution contracts and trace identity

## Goal
Carry one immutable execution identity from job admission through supervision, trace storage, and operator status, while formalizing the contracts needed by later runtime and evidence work.

## Deliverables
- private `ExecuteFrozenJob.action`; public `RunJob.action` remains backward compatible;
- one gateway-generated trace ID plus bundle/source, recipe, task, execution-mode, and calibration identity propagated to the supervisor and every canonical job event;
- additive `JobEvent` identity fields and a lossless trace-database migration;
- capability, skill, fault-catalog, calibration, and evidence JSON schemas;
- component capability references to versioned contract definitions;
- state aggregation of supervisor execution state and corrected operator event handling;
- coordinated package-version and interface documentation updates.

## Acceptance
- admission, frozen record, supervisor, events, operator status, restart reconciliation, and final result use the same trace ID;
- exact bundle, source, recipe, and task identities are queryable from the durable trace;
- old trace databases migrate without losing or rewriting events;
- invalid or mismatched frozen identity fails closed before tree execution;
- all existing public `RunJob` callers remain source compatible.
