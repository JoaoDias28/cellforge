# Task 036 — Executable release qualification

## Goal

Replace the Task 033 synthetic qualification report with an executable, fail-closed
qualification runner. Every passing scenario must be derived from an observed command or
artifact. L0 evidence is valid for contract/runtime gates; L2 is valid only when an external
Task 027 Isaac Sim 6/OpenUSD/PhysX seed report is present and independently validated.

## Scope

Included: the qualification data model and evidence bindings, the existing L0 headless scenario
runner, real compiler/bundle-agent/platform probes, strict Task 027 report validation, the
qualification acceptance script, the checked-in report, CI/documentation updates, and focused
tests for valid, unavailable, tampered, CPU-relabeled, and genuine L2 evidence.

Excluded: Makefile changes, Task 037/038 demo or component work, hardware adapters, physical
commissioning, functional-safety implementation, and changes to public ROS/schema interfaces.

## Current state

Task 033's `cellforge_bundle.qualification` constructs every scenario, event count, platform
result, and bundle identity as constants. It also labels an absent L2 run as passed. The
repository already provides the deterministic `cellforge_mock_adapters.headless` L0 runner,
Task 026 compiler/assembly/agent contracts, Task 032 platform acceptance probe, and Task 027's
`cellforge.isaac_l2_seed_report` format. The supported Task 027 report contains 100 seeded runs,
actual-PhysX/GPU metadata, runtime/adapters event provenance, replay digest, and three required
PhysX fault outcomes.

## Design

1. Run the real L0 headless CLI in a temporary evidence directory with the canonical scenario
   root, tree, and golden traces. Parse only its generated JSON report; derive scenario status,
   trace count, and event summaries from those observed rows.
2. Execute the existing Task 032 platform acceptance script as a subprocess and retain its
   stdout/stderr and exit code as a content-addressed artifact. Execute compiler/assembly and
   signed agent verification in-process against a temporary release, then tamper a derived file
   and require the existing agent verifier to reject it. Execute the existing state/restart
   contract and stale-device logic for their dedicated scenario evidence.
3. Validate an externally supplied Task 027 seed report. Require exact schema/kind, Isaac Sim 6,
   CUDA GPU, `actual_physx_executed: true`, runtime/adapter event origin, canonical scene digest,
   100 unique seeds, replay digest, and dropped/seating/collision fault results. Reject CPU,
   mock, missing, malformed, tampered, mismatched, or incomplete reports. Never synthesize L2
   rows from L0 output.
4. Extend report fields additively with observed command/artifact references, gate availability,
   L2 validation details, and a deterministic integrity digest. Keep existing constructor fields,
   canonical signing, and JSON defaults compatible for callers that do not use new evidence.
5. Treat L2 unavailability as an explicit incomplete gate. CI may complete the L0 qualification
   probe while reporting `overall_passed: false`; a full-release invocation can require L2 and
   exits non-zero for missing or invalid external evidence.

## Work sequence

1. Add this plan and inspect the existing qualification, L0, Task 027, bundle, and platform
   contracts; acceptance: all owned edits stay within the Task 036 ownership set.
2. Replace hard-coded qualification construction with observed L0/platform/bundle/restart/stale
   evidence and additive report fields; acceptance: focused tests prove no synthetic pass can be
   emitted and every scenario points to an artifact.
3. Add strict Task 027 report validation and script flags for optional versus required L2; acceptance:
   missing, CPU-relabeled, and tampered reports are unavailable/failed while a genuine fixture
   validates only when its identities and outcomes match.
4. Update the checked-in report, CI, deployment/testing documentation, and task notes; acceptance:
   the report records the actual revision/cleanliness and honest unavailable gates.
5. Run focused and full applicable checks, inspect the scoped diff, commit as
   `task(036): make release qualification executable`, publish a ready PR, and wait for required
   checks before any merge attempt.

## Validation

- Focused qualification tests and `scripts/verify_software_release_qualification.py`.
- Valid observed L0 evidence, missing L2, CPU-relabeled/tampered L2, and genuine Task 027 fixture.
- `uv run --frozen pytest` for the full Python suite, Ruff, mypy, and example validation.
- Applicable ROS build/test checks; report Isaac Sim 6 as unavailable if this environment lacks it.
- Inspect report artifacts, SHA-256 references, signature/integrity behavior, and `git diff --check`.

## Risks and rollback

The L0 runner is an oracle and not a production execution path; its report is retained as
contract evidence only. The Task 027 seed report may come from another supported runner, so the
qualification binds it to the local canonical scene digest and records any unavailable source
metadata rather than silently inferring it. No physical hardware or rated safety function is
invoked. Revert the single task commit to restore the Task 033 report API if necessary.

## Progress

- [x] 2026-08-20 — Confirmed clean Task 035 baseline, prerequisite history, and Task 033 hard-coded
  qualification path.
- [x] 2026-08-20 — Implemented executable evidence collection, additive report fields, and
  backward-compatible signing/integrity behavior.
- [x] 2026-08-20 — Validated Task 027 L2 boundaries against missing, CPU-relabeled, tampered,
  format-only, and parent-provided genuine external evidence cases.
- [ ] 2026-08-20 — Run final checks, regenerate the checked-in report, commit, publish, and
  complete the repository lifecycle.

## Decisions

- 2026-08-20 — Keep L2 external and fail-closed: Task 036 cannot create or relabel PhysX evidence.
- 2026-08-20 — Use the existing L0 CLI and Task 032 acceptance probe as observed subprocess gates,
  retaining their emitted artifacts rather than reproducing their expected events in Python.
- 2026-08-20 — Allow CI to report L2 unavailable without claiming full qualification; expose a
  strict mode for release qualification that returns non-zero when L2 is absent or invalid.

## Results

To be completed after implementation and repository verification.
