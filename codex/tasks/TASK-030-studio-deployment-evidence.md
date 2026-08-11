> Follow `AGENTS.md`. Create an ExecPlan. Do not implement unrelated later tasks.

# TASK-030 — Studio deployment and evidence workflow

## Goal
Complete the engineering workflow from scenario execution through signed bundle comparison.

## Deliverables
- runtime-backed scenario selection, submission, fault injection, timeline, replay, and evidence;
- bundle assembly, deterministic diff, signature, compatibility, install, and rollback panels;
- application-service boundaries for every UI operation;
- fidelity labeling that cannot present L0 or CPU-only results as L2.

## Acceptance
- Studio opens the pen project, runs L0 and L2 scenarios, and displays exact evidence;
- Studio assembles a signed installable bundle and compares it to the active release;
- backend failure, platform outage, signature failure, and unsupported fidelity are explicit;
- Studio remains absent from production runtime dependencies.
