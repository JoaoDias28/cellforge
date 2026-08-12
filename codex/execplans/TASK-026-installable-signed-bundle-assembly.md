# Task 026 — Installable signed bundle assembly

## Goal
Produce a deterministic, complete release directory that the existing bundle agent can verify, install, activate, and roll back, with an Ed25519 signature that binds the immutable bundle identity.

## Scope
Included: additive `cellforge bundle assemble` support; release inventory materialization; canonical checksums, agent and launch configuration, plugin manifests, evidence summary, executable runtime launcher, signing and trust verification; and end-to-end agent coverage.

Excluded: remote artifact publication, fleet management, genuine Isaac L2 integration (Task 027), Studio deployment workflows, production approval workflows, and safety enforcement. Private key material remains outside source trees and bundle directories.

## Current state
Task 025 is merged at `a7dd0821e0a86c9b4424c99d234b480ca07316df` on `main`. Task 006 supplies deterministic manifest-only compilation; Task 021 verifies/installs checksummed release directories but does not sign them; Task 025 supplies the frozen runtime graph and L0 bringup. The actual repository task filename is `TASK-026-installable-bundle-assembly.md`; the user-provided filename includes an extra `signed` word but describes this exact task.

## Design
Assembly consumes a verified compiler manifest and only declared immutable source inputs, generating a normalized release tree. The derived release files are deterministically serialized and included in the checksum inventory. A detached signature plus a public-key identifier is verified by the agent against locally provisioned trusted public keys; neither private keys nor secret values enter a bundle. Existing manifest-only compilation remains unchanged. The agent rejects invalid signatures before copying, stopping services, or switching releases.

## Work sequence
1. Inspect compiler, CLI, agent, launch, and Task 025 runtime contracts; acceptance: documented source-to-release inventory and signature boundary.
2. Implement deterministic assembly and CLI while preserving current manifest-only callers; acceptance: repeated assembly is byte-identical and has the same bundle ID.
3. Extend agent signature/package/entrypoint checks and add focused rejection tests; acceptance: invalid signature, target, package, checksum, and entrypoint fail before activation.
4. Exercise install, health, boot preparation, and rollback using an assembled reference release; acceptance: health echoes the exact ID and failed candidate restores the prior release/environment.
5. Update focused documentation and this plan; run required host/container/CI checks; complete Task 026 Git and PR lifecycle only.

## Validation
- `make lint`, `make test`, `make validate-examples`, `make ros-build`, and `make ros-test` (or exact documented equivalents when tools are unavailable).
- Task 026 focused assembler and agent tests for reproducibility, signing, tampering, package/target/entrypoint rejection, installation, health, boot preparation, and rollback.
- `git diff --check`, staged diff review, post-commit, hosted-CI, merge, and fast-forward verification.

## Risks and rollback
Derived release content can create an identity cycle, so the canonical Task 006 manifest stays the identity source and generated inventory is verified independently. Signature verification must fail closed when trust material is absent or malformed. Rollback remains Task 021’s activation recovery mechanism; reverting Task 026 restores manifest-only compilation and leaves previously installed Task 021 releases usable.

## Progress
- [x] 2026-08-12 — validated clean Task 025 merge baseline, task mapping, and unavailable host Make baseline.
- [x] 2026-08-12 — define assembly inputs and signing contract.
- [x] 2026-08-12 — implement assembler, CLI, and agent verification.
- [x] 2026-08-12 — add acceptance coverage and documentation.
- [ ] 2026-08-12 — complete validation, commit, PR, merge, and main synchronization.

## Decisions
- 2026-08-12 — retain Task 006 manifest-only build as a backward-compatible path; assembly is an explicit CLI operation.
- 2026-08-12 — private signing keys and trusted public keys are local deployment material, never source-controlled bundle content.

## Results
`cellforge bundle assemble` now materializes compiler-frozen inputs, deterministic launch/agent/
evidence/runtime files, sorted checksums, and a detached Ed25519 signature. The agent requires a
local trusted raw public key for installation, validates frozen package entrypoints against local
target facts, and retains its existing staged health/rollback behavior. The manifest-only compiler
path is unchanged. Host-equivalent lint, strict typing, the full pytest suite (348 passed, one
Windows symlink-permission skip), example validation, and focused assembly acceptance passed.
Literal Make is unavailable on the Windows host; Docker Desktop's Linux engine is stopped, so local
Jazzy ROS build/test evidence remains unavailable pending hosted CI.
