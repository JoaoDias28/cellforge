> Follow `AGENTS.md`. Create an ExecPlan. Do not implement unrelated later tasks.

# TASK-033 — Software release qualification

## Goal
Prove the complete software platform in clean engineering, platform, and cell environments.

## Deliverables
- automated Studio-to-L0/L2-to-evidence-to-signed-bundle-to-runtime qualification workflow;
- nominal, fault, cancel, timeout, restart, corrupt-bundle, offline-platform, stale-device, and uncertain-process qualification scenarios;
- proof that one tree and recipe run in L0 and L2 without simulator-specific workflow branches;
- signed qualification report with revisions, identities, versions, seeds, and limitations;
- final architecture, operator, recovery, deployment, roadmap, and README updates.

## Acceptance
- every software-side MVP criterion passes in clean supported environments;
- all required CI, ROS Jazzy, Isaac Sim 6, Studio, deployment, and platform gates are green;
- no fictional runtime packages, synthetic success events, or silent placeholders remain;
- the working tree and default branch are clean and contain every prerequisite merge;
- Task 034 is explicitly marked eligible without claiming any hardware qualification.
