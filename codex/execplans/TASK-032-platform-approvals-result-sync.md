# Task 032 — Platform approvals, evidence, and result synchronization

## Goal
Govern immutable recipe approvals and content-addressed evidence lifecycle with two-role production authorization, produce signed Ed25519 approval/evidence snapshots for offline compiler verification, implement real compiler evidence-policy evaluation replacing the unconditional placeholder, and provide idempotent synchronization of locally authoritative production jobs, traces, results, and attachments across network outages.

## Scope
Included:
- Database migrations (003 & 004) adding tables for append-only `recipe_approvals`, content-addressed `evidence_records`, and synchronized production entities (`production_jobs`, `production_traces`, `production_results`, `production_attachments`).
- Append-only recipe approval lifecycle with two-role production authorization (requiring 2 distinct users with 2 distinct authorized roles, e.g. `process_engineer` + `automation_engineer` / `administrator` / `safety_engineer`), enforcing strict rejection of self-approval by recipe authors.
- Content-addressed evidence storage and indexing for simulation, calibration, commissioning, production, and safety-review evidence records adhering to `schemas/evidence.schema.json` and backed by `ArtifactStore`.
- Cryptographic Ed25519 signing and verification of approval/evidence snapshots (`EvidenceSnapshot`) for offline compiler verification.
- Real compiler evidence-policy evaluation in `cellforge_bundle.compiler` replacing the unconditional placeholder: validating snapshots, Ed25519 signatures, cell matching, dual-role non-self recipe approvals, freshness (no stale/expired evidence), hardware evidence presence (simulation, calibration, commissioning, safety-review), component/cell matching, and artifact SHA-256 integrity.
- Production synchronization API (`POST /api/v1/sync/batch`) and querying endpoints (`/api/v1/production/...`), guaranteeing idempotency under repeated or out-of-order submissions with zero duplicate records.
- Local runtime synchronization manager (`ProductionSyncManager` / `PlatformClient.sync_batch`) maintaining local records as authoritative until acknowledged by the platform, with graceful offline buffering during platform outages.
- Verification acceptance probe script `scripts/verify_platform_approvals_result_sync.py` and comprehensive test suites across `cellforge_platform`, `cellforge_bundle`, and integration tests.

Excluded:
- Hardware execution or direct equipment control from platform endpoints (safety and control remain strictly local to cell runtime and rated hardware).
- Modifying earlier completed tasks or altering immutable schemas.
- Starting Task 033.

## Current state
- Task 006 provides the deterministic cell compiler in `cellforge_bundle.compiler`, currently with an explicit placeholder failing closed for production evidence.
- Task 023 provides execution contracts, frozen job identities, monotonic trace events in `cellforge_state_trace`, and `SqliteJobStore` in `cellforge_job_gateway`.
- Task 026 provides Ed25519 detached bundle signatures and verification.
- Task 031 provides `cellforge_platform` package with FastAPI `/api/v1`, SQLite/PostgreSQL reversible database migrations (001, 002), `ArtifactStore`, and OIDC RBAC.
- `schemas/evidence.schema.json` defines evidence schema with kinds: `simulation`, `calibration`, `commissioning`, `production`, `safety_review`.
- `schemas/recipe.schema.json` defines recipe document schema with `RecipeStatus` (DRAFT, VALIDATED, TESTED, APPROVED, RETIRED).

## Design
### Database Migrations
- Migration 003 (`003_recipe_approvals_and_evidence`):
  - `recipe_approvals`: append-only ledger tracking `recipe_record_id`, `project_id`, `recipe_id`, `version`, `recipe_sha256`, `role`, `approver_id`, `decision`, `comments`, `signature`, `created_at`.
  - `evidence_records`: indexed metadata for content-addressed evidence records (`id`, `schema_version`, `kind`, `cell_id`, `subject_json`, `artifact_sha256`, `issuer`, `valid_until`, `signature`, `metadata_json`, `created_at`, `created_by`).
- Migration 004 (`004_production_sync_records`):
  - `production_jobs`: idempotent record of jobs executed by cell runtimes (`idempotency_key` PK, `cell_id`, `job_id`, `request_hash`, `status`, `frozen_json`, `result_json`, `synced_at`, `created_at`).
  - `production_traces`: monotonic trace events (`id` PK as `trace_id:sequence`, `trace_id`, `sequence`, `cell_id`, `job_id`, `component_instance_id`, `command_id`, `event_type`, `severity`, `bundle_id`, `source_revision`, `recipe_id`, `recipe_version`, `recipe_sha256`, `task_id`, `task_sha256`, `execution_mode`, `payload_json`, `timestamp`, `synced_at`).
  - `production_results`: final job results (`id` PK, `cell_id`, `job_id`, `trace_id`, `success`, `result_code`, `result_message`, `output_payload_json`, `completed_at`, `synced_at`).
  - `production_attachments`: associated artifacts (`id` PK, `digest`, `cell_id`, `job_id`, `trace_id`, `filename`, `media_type`, `size_bytes`, `synced_at`).

### Two-Role Append-Only Recipe Approval
- Recipe statuses: `DRAFT` -> `VALIDATED` -> `TESTED` -> `APPROVED` -> `RETIRED`.
- Production approval requires 2 distinct approvals from 2 distinct users possessing 2 distinct eligible roles (`process_engineer`, `automation_engineer`, `administrator`, `safety_engineer`).
- Self-approval by the recipe creator/author is rejected and cannot satisfy approval requirements.
- Approvals are cryptographically tied to exact `recipe_sha256`.

### Signed Evidence & Approval Snapshots
- `EvidenceSnapshot` data model with canonical JSON serialization.
- Signed with Ed25519 private key by the platform service (`PlatformSigner`).
- Verifiable offline by the compiler using platform public key (`PlatformVerifier`).

### Compiler Evidence Policy Engine
- Replaces unconditional placeholder in `cellforge_bundle.compiler` stage `CompilerStage.EVIDENCE`.
- In `ExecutionMode.PRODUCTION`:
  - Snapshot is mandatory.
  - Verifies Ed25519 snapshot signature.
  - Validates cell ID matching.
  - Validates recipes: present in snapshot, status `APPROVED`, exact SHA-256 match, >= 2 distinct approvals from distinct users with distinct roles, no self-approval.
  - Validates hardware evidence: required kinds (`simulation`, `calibration`, `commissioning`, `safety_review`) must be present, valid signatures, matching cell ID and component instances/calibrations, not expired (`valid_until`), artifact digests valid.
  - Fails closed with precise finding codes (`compiler.evidence.*`) on any violation.
  - Updates `manifest.evidence` with verified summary.

### Production Synchronization Engine
- Platform endpoint `POST /api/v1/sync/batch` accepting batches of jobs, traces, results, attachments.
- Idempotent upsert logic: repeated calls or out-of-order arrivals create no duplicates.
- Returns explicit acknowledgment of received keys.
- Local `ProductionSyncManager` keeps local runtime records authoritative until acknowledged, buffering during outages and syncing when platform is available.

## Work sequence
1. Update database migrations in `cellforge_platform` (migrations 003 and 004) and repository classes.
2. Implement recipe approval API and evidence management endpoints in `cellforge_platform`.
3. Implement `EvidenceSnapshot` generation, Ed25519 signing, and verification utilities.
4. Implement compiler evidence-policy evaluation in `cellforge_bundle.compiler` and update bundle models/assembler.
5. Implement production synchronization endpoints in `cellforge_platform` and sync client in `cellforge_platform.client`.
6. Implement unit, integration, migration, and compiler acceptance tests.
7. Create acceptance probe `scripts/verify_platform_approvals_result_sync.py`.
8. Run full test suite, linting (`ruff`), type checking (`mypy`), and example validation.
9. Commit, push branch, open PR, verify CI, and merge.

## Validation
- `uv run --frozen pytest --basetemp .pytest-tmp-task032 -o cache_dir=.pytest-cache/task032 src/python/cellforge_platform/tests`
- `uv run --frozen pytest --basetemp .pytest-tmp-task032 -o cache_dir=.pytest-cache/task032 src/python/cellforge_bundle/tests`
- `uv run --frozen python scripts/verify_platform_approvals_result_sync.py`
- `uv run --frozen ruff format --check .`
- `uv run --frozen ruff check .`
- `uv run --frozen mypy ...`
- Full test suite run with clean exit.

## Risks and rollback
- Risk: Compiler fails to catch subtle evidence tampering or stale timestamps.
  - Mitigation: Write targeted test cases for every failure mode (tampered digest, expired timestamp, wrong cell ID, wrong component, self-approval, missing hardware kind, invalid signature).
- Risk: High-frequency trace sync creates database lock contention or duplicates.
  - Mitigation: Use SQLite WAL mode, batch transactions, and strict `INSERT OR IGNORE` / `ON CONFLICT DO NOTHING` idempotency keys.
- Rollback: Revert task branch commits without touching earlier tasks.

## Progress
- [x] 2026-08-18 — Checked out `task/032-platform-approvals-result-sync` from `main`, verified prerequisite commits (006, 023, 031).
- [ ] 2026-08-18 — Implement database migrations 003 and 004 with up/down support.
- [ ] 2026-08-18 — Implement recipe approvals and evidence endpoints with role verification and self-approval rejection.
- [ ] 2026-08-18 — Implement signed Ed25519 snapshot creation and verification.
- [ ] 2026-08-18 — Implement real compiler evidence-policy evaluation replacing the placeholder.
- [ ] 2026-08-18 — Implement idempotent synchronization API and client sync manager.
- [ ] 2026-08-18 — Create test suites and acceptance verification script `scripts/verify_platform_approvals_result_sync.py`.
- [ ] 2026-08-18 — Run linting, typing, examples, tests, commit, push, PR, and merge.

## Decisions
- 2026-08-18 — Recipe approvals are recorded as an append-only ledger in `recipe_approvals` rather than mutating existing rows, preserving complete audit trails of all approvals/rejections.
- 2026-08-18 — Evidence snapshot signing uses detached Ed25519 signatures with canonical JSON serialization, compatible with offline compiler verification without network calls.
- 2026-08-18 — Production sync uses deterministic composite keys (`trace_id:sequence`, `idempotency_key`, `trace_id`) ensuring idempotent deduplication across network interruptions.

## Results
- (To be populated upon completion)
