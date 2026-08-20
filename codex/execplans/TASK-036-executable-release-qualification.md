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
- [x] 2026-08-20 — Ran final focused/full Python, Ruff, mypy, example-validation, and qualification
  checks; regenerated the checked-in report from committed revision `44747ca1ae659727172324d857b73f307eb36150`.
- [ ] 2026-08-20 — Publish the implementation and report commits, wait for required checks, merge,
  and complete the repository lifecycle.

## Decisions

- 2026-08-20 — Keep L2 external and fail-closed: Task 036 cannot create or relabel PhysX evidence.
- 2026-08-20 — Use the existing L0 CLI and Task 032 acceptance probe as observed subprocess gates,
  retaining their emitted artifacts rather than reproducing their expected events in Python.
- 2026-08-20 — Allow CI to report L2 unavailable without claiming full qualification; expose a
  strict mode for release qualification that returns non-zero when L2 is absent or invalid.

## Results

- Implementation commit: `44747ca1ae659727172324d857b73f307eb36150` (`task(036): make release
  qualification executable`). Report/plan evidence commit: `d860c28ae1bf0c8f9b8ec6e690cf604a9859cfc2`
  (`task(036): record executable qualification evidence`).
- Focused qualification tests: `11 passed` with the parent-provided genuine Task 027 report
  supplied through `CELLFORGE_TASK027_REPORT`.
- Full Python suite: `453 passed, 2 skipped, 1 warning`; skips were the Windows symlink privilege
  case and the intentionally unset external-L2 environment case in the no-Isaac run.
- Ruff format/check and strict mypy: passed for the changed implementation, tests, and runner.
- Example validation: `Validated 10 canonical schemas, 7 component config schemas, and 25 example
  YAML documents.`
- Qualification command with no L2: all 14 observed scenario rows passed their expected L0/probe
  gates, L2 reported `unavailable`, `overall_passed` was `false`; default mode returned 0 for CI
  evidence collection and `--require-l2` returned 1.
- Clean final-tree qualification with the genuine L2 report: revision `d860c28ae1bf0c8f9b8ec6e690cf604a9859cfc2`,
  `git_clean: true`, L2 passed, `QUALIFICATION OVERALL: TRUE`, exit 0. Clean final-tree
  qualification without L2 reported `overall_passed: false` and explicit unavailable status.
- Genuine external L2 report: SHA-256
  `ceac3fbc38d4ba8f412751fd90e89bd525b3f01a43430ee972e5a7b7c244c`; validator observed Isaac 6,
  RTX 4080/CUDA, 100 seeds, and all three required PhysX faults. The L2 gate passed; the full
  report remained false in the dirty implementation worktree until the clean-source check.
- Checked-in report: `examples/pen_engraving/reports/software_release_qualification_report.json`.
  It records revision `44747ca1ae659727172324d857b73f307eb36150`, `git_clean: true`, a valid
  SHA-256 integrity seal, explicit L2 `unavailable`, and `overall_passed: false`; it is included
  in the evidence commit above.
