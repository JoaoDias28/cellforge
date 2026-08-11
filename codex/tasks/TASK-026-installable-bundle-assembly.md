> Follow `AGENTS.md`. Create an ExecPlan. Do not implement unrelated later tasks.

# TASK-026 — Installable signed bundle assembly

## Goal
Produce a complete, reproducible release directory accepted by the existing bundle agent.

## Deliverables
- backward-compatible manifest-only build plus `cellforge bundle assemble`;
- complete inventory materialization, checksums, agent/launch config, plugin manifests, evidence summary, and executable `scripts/start-runtime`;
- Ed25519 bundle signature with private keys outside source/bundles and local trusted public keys;
- agent verification of signature, package availability, entrypoints, target facts, and checksums;
- actual compiler-output install, activation, health, boot preparation, and rollback tests.

## Acceptance
- identical inputs produce byte-identical bundle contents and identity;
- the reference bundle verifies, installs, starts, and reports its exact bundle ID healthy;
- tampering, missing packages, wrong targets, invalid signatures, and bad entrypoints are rejected;
- failed health restores the previous known-good release and secrets/environment state;
- existing manifest-only CLI callers continue to work.
