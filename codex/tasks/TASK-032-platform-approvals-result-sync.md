> Follow `AGENTS.md`. Create an ExecPlan. Do not implement unrelated later tasks.

# TASK-032 — Platform approvals, evidence, and result synchronization

## Goal
Govern immutable approvals/evidence and synchronize locally authoritative production records.

## Deliverables
- append-only recipe lifecycle with two-role production approval;
- content-addressed simulation, calibration, commissioning, production, and safety-review evidence;
- signed Ed25519 approval/evidence snapshots for offline compiler verification;
- real compiler evidence-policy evaluation replacing the unconditional placeholder;
- idempotent jobs, traces, results, and attachment synchronization after outages.

## Acceptance
- tampered, stale, unsigned, wrong-cell, wrong-component, and self-approved evidence is rejected;
- missing hardware evidence produces precise findings and cannot authorize production;
- repeated/out-of-order synchronization creates no duplicate production records;
- local runtime records remain authoritative until acknowledged by the platform.
