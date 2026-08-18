# Task 031 — Platform registry and artifacts service

## Goal
Provide a central, authenticated engineering metadata and content-addressed artifact service that indexes Git-backed components, projects, recipes, and release bundles, enables immutable artifact publishing and resolution by content digest, enforces role-based OIDC access control while prohibiting development auth in production, and guarantees that total platform outages do not interrupt local production cell execution.

## Scope
Included:
- `cellforge_platform` Python package with a versioned FastAPI application (`/api/v1`).
- Database abstraction with reversible migrations tested against empty and prior schemas (supporting SQLite for tests and PostgreSQL for production).
- PostgreSQL database models for components, projects, recipes, release bundles, artifact blobs, and audit journals.
- Git-backed source indexing and immutable released record storage with SHA-256 digest validation.
- Abstract content-addressed `ArtifactStore` with `FilesystemArtifactStore` and S3-compatible `S3ArtifactStore` implementations.
- Component publishing, semantic-version conflict detection, support levels (`simulated`, `bench_tested`, `production_qualified`, `deprecated`), license metadata inspection, and deprecation lifecycle workflows.
- Release bundle publication with manifest integrity and detached Ed25519 signature verification.
- OIDC JWT token validation with role mapping (`viewer`, `operator`, `maintainer`, `process_engineer`, `automation_engineer`, `administrator`), enforcing fail-closed rejection of development authentication in production environments.
- Component registry search, inspection, resolution, and artifact download APIs.
- Platform client library (`PlatformClient`) allowing CLI, Studio, and CI tools to communicate cleanly with the platform service.
- Explicit verification that no platform endpoint exists for robot joints, equipment commands, or safety control.
- Deterministic unit, integration, migration, and acceptance test suites.

Excluded:
- Implementing hardware control or safety logic in the platform service (safety remains independently hardware-enforced; production cell runtime remains fully offline-capable).
- Multi-role recipe approval workflows and production job/result sync (deferred to Task 032).
- Final release qualification packaging (deferred to Task 033).

## Current state
- Task 002 & Task 005 provide core domain models (`ComponentType`, `CellProject`, `SemanticVersion`, `ComponentTypeIdentifier`) and filesystem component registry resolver (`FilesystemComponentRegistry`, `resolve_cell`).
- Task 006 provides cell compiler and execution-mode contracts.
- Task 021 & Task 026 provide `BundleAgent`, `assemble_bundle`, Ed25519 detached signatures, and target preflight checks.
- Task 023 provides frozen execution identity, SHA-256 trace identity, and digest validations.
- Tasks 028–030 provide spatial, task, recipe, scenario, evidence, and deployment workflows in Cell Studio.
- `pyproject.toml` workspace includes `fastapi`, `httpx`, `uvicorn`, `pydantic`, `cryptography`, and `pyyaml`.

## Design
### Database and Reversible Migrations
- Migration engine `DatabaseManager` tracking schema versions in `schema_migrations`.
- SQL DDL migrations with `up` and `down` scripts:
  - Migration 1 (`001_initial_schema`): creates `components`, `projects`, `recipes`, `bundles`, `artifacts`.
  - Migration 2 (`002_component_deprecations`): adds deprecation metadata columns, indexes, and audit logs.
- Forward and backward migration runner supporting transaction rollback on failure.
- Database repository classes implementing CRUD operations with immutability guarantees:
  - Attempting to publish an existing component version or bundle with a different content hash fails closed with conflict code `conflict.version_already_exists`.

### Content-Addressed Artifact Storage
- `ArtifactStore` protocol:
  - `put(data: bytes, expected_digest: str | None = None) -> str`: hashes data, verifies expected SHA-256 digest, stores content-addressed blob.
  - `get(digest: str) -> bytes`: retrieves blob and verifies SHA-256 digest.
  - `exists(digest: str) -> bool`: checks if digest is present.
  - `delete(digest: str) -> None`: removes blob if unreferenced.
- `FilesystemArtifactStore`: structured tree `<root>/blobs/<sha256[:2]>/<sha256>`.
- `S3ArtifactStore`: S3/MinIO bucket store with SHA-256 object keys and digest validation.

### Authentication, OIDC JWT, and Roles
- `OidcTokenVerifier`: verifies RS256/Ed25519/HS256 tokens against JWKS / public keys.
- Claims parsed: `sub`, `roles` / `groups`, `iss`, `aud`, `exp`.
- Standard roles: `viewer`, `operator`, `maintainer`, `process_engineer`, `automation_engineer`, `administrator`.
- Development auth guard:
  - Dev auth headers (`X-CellForge-Dev-User`, `X-CellForge-Dev-Role`) are active ONLY when `ENVIRONMENT != "production"` and `ALLOW_DEV_AUTH=true`.
  - In `production` environment, any request relying on dev headers is rejected with `401 Unauthorized` (`auth.production_dev_auth_prohibited`).

### FastAPI REST Service (`/api/v1`)
- `/api/v1/components`: list, publish, get by (type, version), deprecate, download.
- `/api/v1/projects`: index, list, get by cell ID.
- `/api/v1/recipes`: publish, list, get by version.
- `/api/v1/bundles`: publish signed bundle, list, inspect, download.
- `/api/v1/artifacts`: upload, download, check by SHA-256 digest.
- `/api/v1/resolve`: server-side component dependency resolution for `cell.yaml`.
- Health check: `GET /health` returning service health, database status, and storage status.

### Offline Resilience Guarantee
- Verification test confirming that the production cell runtime (`cellforge_job_gateway`, `cellforge_supervisor`, `cellforge_bringup`, `BundleAgent`) boots and executes offline without network access to the platform service.

## Work sequence
1. Scaffold package `src/python/cellforge_platform` with `pyproject.toml`, configuration, and domain models.
2. Implement `DatabaseManager` and reversible SQL migrations with up/down tests.
3. Implement `ArtifactStore` protocol, `FilesystemArtifactStore`, and `S3ArtifactStore`.
4. Implement `OidcTokenVerifier`, authentication dependencies, and the production dev-auth guard.
5. Implement FastAPI service endpoints and `PlatformClient`.
6. Implement unit, contract, migration, and offline resilience test suites in `src/python/cellforge_platform/tests/`.
7. Create acceptance probe `scripts/verify_platform_registry_artifacts.py`.
8. Update Makefile and run all repository quality checks: `ruff`, `mypy`, `pytest`, `validate-examples`.
9. Commit, push branch, open PR, verify CI checks pass, and merge to `main`.

## Validation
- `uv run --frozen pytest src/python/cellforge_platform/tests`
- `uv run --frozen python scripts/verify_platform_registry_artifacts.py`
- `uv run --frozen pytest` (full repo suite)
- `uv run --frozen ruff format --check .`
- `uv run --frozen ruff check .`
- `uv run --frozen mypy ...`
- Local Git verification: `git status --short`, `git log -1 --oneline`.

## Risks and rollback
- Risk: Migration scripts might fail to rollback cleanly on non-empty databases.
  - Mitigation: Write deterministic unit tests testing full migration cycle: empty -> up to latest -> down to initial -> down to 0 -> up to latest.
- Risk: Production dev-auth leakage.
  - Mitigation: Enforce strict environment check failing closed on any dev auth attempt when `ENVIRONMENT=production`.
- Risk: Accidental inclusion of control endpoints on platform service.
  - Mitigation: Unit test scanning all registered FastAPI route paths and methods ensuring zero robot/joint/I/O/safety routes exist.
- Rollback: Revert task branch commits without affecting existing tasks.

## Progress
- [x] 2026-08-17 — Checked out `task/031-platform-registry-artifacts` from `main`, verified prerequisite commits (005, 006, 023).
- [x] 2026-08-17 — Implement database manager, repositories, and reversible migrations.
- [x] 2026-08-17 — Implement artifact storage engine (filesystem + S3).
- [x] 2026-08-17 — Implement OIDC JWT auth, role mapping, and production dev-auth guard.
- [x] 2026-08-17 — Implement FastAPI service endpoints and `PlatformClient`.
- [x] 2026-08-17 — Implement unit, contract, migration, and offline resilience test suites.
- [x] 2026-08-17 — Create acceptance probe `scripts/verify_platform_registry_artifacts.py`.
- [x] 2026-08-18 — Run full lint, typing, example validation, and test suites across all 416 items.
- [ ] 2026-08-18 — Commit, push, open PR, verify CI, and merge.

## Decisions
- 2026-08-17 — Package platform service under `src/python/cellforge_platform` to keep platform engineering services cleanly isolated from domain models, CLI, and cell runtime.
- 2026-08-17 — Implement custom reversible migration manager with pure SQL to provide complete control over SQLite and PostgreSQL dialect compatibility without heavy runtime dependencies.
- 2026-08-17 — Enforce immutable released records: once a component version or bundle ID is published, its content-address cannot be changed or overwritten.

## Results
- Package `cellforge-platform` (`src/python/cellforge_platform/`) created and validated.
- 14 dedicated test suites in `src/python/cellforge_platform/tests/` covering migrations, storage backends, OIDC authentication/RBAC, component registry, projects/recipes/bundles lifecycle, server-side dependency resolution, strict safety boundary, and offline runtime resilience.
- Full workspace test suite: 415 passed, 1 skipped (Windows symlink privilege) in 151s.
- Acceptance probe `scripts/verify_platform_registry_artifacts.py`: all 11 stages passed.
- Linting & type checking: `ruff format --check`, `ruff check`, and `mypy` (124 source files) passed with 0 errors.
- Schema & example validation: 10 canonical schemas, 7 component config schemas, 24 example documents validated.
