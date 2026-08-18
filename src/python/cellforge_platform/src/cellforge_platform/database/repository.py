"""Data access repositories with immutability and conflict validation."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from cellforge_platform.models import (
    BundleRecord,
    ComponentDetail,
    ComponentSummary,
    EvidenceRecord,
    EvidenceRecordCreate,
    ProductionAttachmentRecord,
    ProductionJobRecord,
    ProductionResultRecord,
    ProductionTraceRecord,
    ProjectRecord,
    RecipeApprovalRecord,
    RecipeApprovalSummary,
    RecipeRecord,
    SyncBatchResponse,
)


class DatabaseError(Exception):
    """Base exception for database operations."""


class ConflictError(DatabaseError):
    """Raised when an immutable entity publication conflicts with existing version."""


class NotFoundError(DatabaseError):
    """Raised when an entity is not found."""


class ComponentRepository:
    """Repository for registered component packages."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def publish(
        self,
        *,
        component_type: str,
        version: str,
        name: str,
        kind: str,
        support_level: str,
        license_str: str | None,
        manifest_json: str,
        manifest_sha256: str,
        package_blob_digest: str | None = None,
        git_repo: str | None = None,
        git_commit: str | None = None,
        created_by: str | None = None,
    ) -> ComponentDetail:
        # Check if already exists
        existing = self.get(component_type, version)
        if existing is not None:
            if (
                existing.summary.manifest_sha256 == manifest_sha256
                and existing.summary.package_blob_digest == package_blob_digest
            ):
                return existing
            raise ConflictError(
                f"Component '{component_type}' version '{version}' is already published "
                f"with digest '{existing.summary.manifest_sha256}' "
                f"(attempted: '{manifest_sha256}'). Released components are immutable."
            )

        comp_id = str(uuid4())
        now = datetime.now(UTC).isoformat()
        self.conn.execute(
            """
            INSERT INTO components (
                id, component_type, version, name, kind, support_level, license,
                manifest_json, manifest_sha256, package_blob_digest, git_repo, git_commit,
                is_deprecated, deprecation_reason, created_at, created_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, NULL, ?, ?);
            """,
            (
                comp_id,
                component_type,
                version,
                name,
                kind,
                support_level,
                license_str,
                manifest_json,
                manifest_sha256,
                package_blob_digest,
                git_repo,
                git_commit,
                now,
                created_by,
            ),
        )
        self.conn.commit()

        return self.get(component_type, version)  # type: ignore[return-value]

    def get(self, component_type: str, version: str) -> ComponentDetail | None:
        cursor = self.conn.execute(
            """
            SELECT id, component_type, version, name, kind, support_level, license,
                   manifest_json, manifest_sha256, package_blob_digest, git_repo, git_commit,
                   is_deprecated, deprecation_reason, created_at, created_by
            FROM components
            WHERE component_type = ? AND version = ?;
            """,
            (component_type, version),
        )
        row = cursor.fetchone()
        if row is None:
            return None

        summary = ComponentSummary(
            id=row["id"],
            component=row["component_type"],
            version=row["version"],
            name=row["name"],
            kind=row["kind"],
            support_level=row["support_level"],
            license=row["license"],
            is_deprecated=bool(row["is_deprecated"]),
            deprecation_reason=row["deprecation_reason"],
            manifest_sha256=row["manifest_sha256"],
            package_blob_digest=row["package_blob_digest"],
            created_at=row["created_at"],
            created_by=row["created_by"],
        )
        manifest_data = json.loads(row["manifest_json"])
        return ComponentDetail(
            summary=summary,
            manifest=manifest_data,
            git_repo=row["git_repo"],
            git_commit=row["git_commit"],
        )

    def list(
        self,
        *,
        kind: str | None = None,
        support_level: str | None = None,
        query: str | None = None,
        include_deprecated: bool = True,
    ) -> list[ComponentSummary]:
        clauses: list[str] = []
        params: list[Any] = []

        if not include_deprecated:
            clauses.append("is_deprecated = 0")
        if kind is not None:
            clauses.append("kind = ?")
            params.append(kind)
        if support_level is not None:
            clauses.append("support_level = ?")
            params.append(support_level)
        if query is not None:
            clauses.append("(component_type LIKE ? OR name LIKE ?)")
            params.extend([f"%{query}%", f"%{query}%"])

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"""
            SELECT id, component_type, version, name, kind, support_level, license,
                   is_deprecated, deprecation_reason, manifest_sha256, package_blob_digest,
                   created_at, created_by
            FROM components
            {where}
            ORDER BY component_type ASC, version DESC;
        """
        cursor = self.conn.execute(sql, tuple(params))
        results: list[ComponentSummary] = []
        for row in cursor.fetchall():
            results.append(
                ComponentSummary(
                    id=row["id"],
                    component=row["component_type"],
                    version=row["version"],
                    name=row["name"],
                    kind=row["kind"],
                    support_level=row["support_level"],
                    license=row["license"],
                    is_deprecated=bool(row["is_deprecated"]),
                    deprecation_reason=row["deprecation_reason"],
                    manifest_sha256=row["manifest_sha256"],
                    package_blob_digest=row["package_blob_digest"],
                    created_at=row["created_at"],
                    created_by=row["created_by"],
                )
            )
        return results

    def deprecate(
        self,
        component_type: str,
        version: str,
        reason: str,
        *,
        deprecated_by: str | None = None,
    ) -> ComponentSummary | None:
        existing = self.get(component_type, version)
        if existing is None:
            return None

        self.conn.execute(
            """
            UPDATE components
            SET is_deprecated = 1, deprecation_reason = ?, support_level = 'deprecated'
            WHERE component_type = ? AND version = ?;
            """,
            (reason, component_type, version),
        )
        self.conn.commit()
        updated = self.get(component_type, version)
        return updated.summary if updated is not None else None


class ProjectRepository:
    """Repository for registered cell projects."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def register(
        self,
        *,
        cell_id: str,
        name: str,
        description: str | None = None,
        git_repo: str | None = None,
        git_revision: str | None = None,
        cell_yaml_sha256: str,
        scene_sha256: str,
        metadata_json: str = "{}",
        created_by: str | None = None,
    ) -> ProjectRecord:
        existing = self.get(cell_id)
        proj_id = existing.id if existing is not None else str(uuid4())
        now = datetime.now(UTC).isoformat()

        if existing is not None:
            self.conn.execute(
                """
                UPDATE projects
                SET name = ?, description = ?, git_repo = ?, git_revision = ?,
                    cell_yaml_sha256 = ?, scene_sha256 = ?, metadata_json = ?
                WHERE cell_id = ?;
                """,
                (
                    name,
                    description,
                    git_repo,
                    git_revision,
                    cell_yaml_sha256,
                    scene_sha256,
                    metadata_json,
                    cell_id,
                ),
            )
        else:
            self.conn.execute(
                """
                INSERT INTO projects (
                    id, cell_id, name, description, git_repo, git_revision,
                    cell_yaml_sha256, scene_sha256, metadata_json, created_at, created_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    proj_id,
                    cell_id,
                    name,
                    description,
                    git_repo,
                    git_revision,
                    cell_yaml_sha256,
                    scene_sha256,
                    metadata_json,
                    now,
                    created_by,
                ),
            )
        self.conn.commit()
        return self.get(cell_id)  # type: ignore[return-value]

    def get(self, cell_id: str) -> ProjectRecord | None:
        cursor = self.conn.execute(
            """
            SELECT id, cell_id, name, description, git_repo, git_revision,
                   cell_yaml_sha256, scene_sha256, metadata_json, created_at, created_by
            FROM projects
            WHERE cell_id = ?;
            """,
            (cell_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return ProjectRecord(
            id=row["id"],
            cell_id=row["cell_id"],
            name=row["name"],
            description=row["description"],
            git_repo=row["git_repo"],
            git_revision=row["git_revision"],
            cell_yaml_sha256=row["cell_yaml_sha256"],
            scene_sha256=row["scene_sha256"],
            metadata=json.loads(row["metadata_json"]),
            created_at=row["created_at"],
            created_by=row["created_by"],
        )

    def list(self) -> list[ProjectRecord]:
        cursor = self.conn.execute(
            """
            SELECT id, cell_id, name, description, git_repo, git_revision,
                   cell_yaml_sha256, scene_sha256, metadata_json, created_at, created_by
            FROM projects
            ORDER BY name ASC;
            """
        )
        records: list[ProjectRecord] = []
        for row in cursor.fetchall():
            records.append(
                ProjectRecord(
                    id=row["id"],
                    cell_id=row["cell_id"],
                    name=row["name"],
                    description=row["description"],
                    git_repo=row["git_repo"],
                    git_revision=row["git_revision"],
                    cell_yaml_sha256=row["cell_yaml_sha256"],
                    scene_sha256=row["scene_sha256"],
                    metadata=json.loads(row["metadata_json"]),
                    created_at=row["created_at"],
                    created_by=row["created_by"],
                )
            )
        return records


class RecipeRepository:
    """Repository for recipe versions."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def publish(
        self,
        *,
        project_id: str,
        recipe_id: str,
        version: int,
        name: str,
        status: str,
        schema_sha256: str,
        recipe_sha256: str,
        recipe_json: str,
        created_by: str | None = None,
    ) -> RecipeRecord:
        existing = self.get(project_id, recipe_id, version)
        if existing is not None:
            if existing.recipe_sha256 == recipe_sha256:
                return existing
            raise ConflictError(
                f"Recipe '{recipe_id}' version '{version}' already exists in project "
                f"'{project_id}'. Published recipes are immutable."
            )

        rec_id = str(uuid4())
        now = datetime.now(UTC).isoformat()
        self.conn.execute(
            """
            INSERT INTO recipes (
                id, project_id, recipe_id, version, name, status,
                schema_sha256, recipe_sha256, recipe_json, created_at, created_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                rec_id,
                project_id,
                recipe_id,
                version,
                name,
                status,
                schema_sha256,
                recipe_sha256,
                recipe_json,
                now,
                created_by,
            ),
        )
        self.conn.commit()
        return self.get(project_id, recipe_id, version)  # type: ignore[return-value]

    def get(self, project_id: str, recipe_id: str, version: int) -> RecipeRecord | None:
        cursor = self.conn.execute(
            """
            SELECT id, project_id, recipe_id, version, name, status,
                   schema_sha256, recipe_sha256, recipe_json, created_at, created_by
            FROM recipes
            WHERE project_id = ? AND recipe_id = ? AND version = ?;
            """,
            (project_id, recipe_id, version),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return RecipeRecord(
            id=row["id"],
            project_id=row["project_id"],
            recipe_id=row["recipe_id"],
            version=row["version"],
            name=row["name"],
            status=row["status"],
            schema_sha256=row["schema_sha256"],
            recipe_sha256=row["recipe_sha256"],
            recipe_data=json.loads(row["recipe_json"]),
            created_at=row["created_at"],
            created_by=row["created_by"],
        )

    def list(self, project_id: str, recipe_id: str | None = None) -> list[RecipeRecord]:
        if recipe_id is not None:
            cursor = self.conn.execute(
                """
                SELECT id, project_id, recipe_id, version, name, status,
                       schema_sha256, recipe_sha256, recipe_json, created_at, created_by
                FROM recipes
                WHERE project_id = ? AND recipe_id = ?
                ORDER BY version DESC;
                """,
                (project_id, recipe_id),
            )
        else:
            cursor = self.conn.execute(
                """
                SELECT id, project_id, recipe_id, version, name, status,
                       schema_sha256, recipe_sha256, recipe_json, created_at, created_by
                FROM recipes
                WHERE project_id = ?
                ORDER BY recipe_id ASC, version DESC;
                """,
                (project_id,),
            )
        records: list[RecipeRecord] = []
        for row in cursor.fetchall():
            records.append(
                RecipeRecord(
                    id=row["id"],
                    project_id=row["project_id"],
                    recipe_id=row["recipe_id"],
                    version=row["version"],
                    name=row["name"],
                    status=row["status"],
                    schema_sha256=row["schema_sha256"],
                    recipe_sha256=row["recipe_sha256"],
                    recipe_data=json.loads(row["recipe_json"]),
                    created_at=row["created_at"],
                    created_by=row["created_by"],
                )
            )
        return records


class BundleRepository:
    """Repository for registered signed deployment bundles."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def publish(
        self,
        *,
        bundle_id: str,
        target_profile: str,
        execution_mode: str,
        source_revision: str,
        manifest_json: str,
        signature_json: str,
        project_id: str | None = None,
        key_id: str | None = None,
        blob_digest: str | None = None,
        created_by: str | None = None,
    ) -> BundleRecord:
        existing = self.get(bundle_id)
        if existing is not None:
            if existing.source_revision == source_revision:
                return existing
            raise ConflictError(
                f"Bundle '{bundle_id}' is already registered with revision "
                f"'{existing.source_revision}' (attempted: '{source_revision}'). "
                f"Bundles are content-addressed and immutable."
            )

        b_id = str(uuid4())
        now = datetime.now(UTC).isoformat()
        self.conn.execute(
            """
            INSERT INTO bundles (
                id, bundle_id, project_id, target_profile, execution_mode,
                source_revision, manifest_json, signature_json, key_id, blob_digest,
                created_at, created_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                b_id,
                bundle_id,
                project_id,
                target_profile,
                execution_mode,
                source_revision,
                manifest_json,
                signature_json,
                key_id,
                blob_digest,
                now,
                created_by,
            ),
        )
        self.conn.commit()
        return self.get(bundle_id)  # type: ignore[return-value]

    def get(self, bundle_id: str) -> BundleRecord | None:
        cursor = self.conn.execute(
            """
            SELECT id, bundle_id, project_id, target_profile, execution_mode,
                   source_revision, manifest_json, signature_json, key_id, blob_digest,
                   created_at, created_by
            FROM bundles
            WHERE bundle_id = ?;
            """,
            (bundle_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return BundleRecord(
            id=row["id"],
            bundle_id=row["bundle_id"],
            project_id=row["project_id"],
            target_profile=row["target_profile"],
            execution_mode=row["execution_mode"],
            source_revision=row["source_revision"],
            manifest=json.loads(row["manifest_json"]),
            signature=json.loads(row["signature_json"]),
            key_id=row["key_id"],
            blob_digest=row["blob_digest"],
            created_at=row["created_at"],
            created_by=row["created_by"],
        )

    def list(
        self,
        *,
        target_profile: str | None = None,
        execution_mode: str | None = None,
    ) -> list[BundleRecord]:
        clauses: list[str] = []
        params: list[Any] = []
        if target_profile is not None:
            clauses.append("target_profile = ?")
            params.append(target_profile)
        if execution_mode is not None:
            clauses.append("execution_mode = ?")
            params.append(execution_mode)

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"""
            SELECT id, bundle_id, project_id, target_profile, execution_mode,
                   source_revision, manifest_json, signature_json, key_id, blob_digest,
                   created_at, created_by
            FROM bundles
            {where}
            ORDER BY created_at DESC;
        """
        cursor = self.conn.execute(sql, tuple(params))
        records: list[BundleRecord] = []
        for row in cursor.fetchall():
            records.append(
                BundleRecord(
                    id=row["id"],
                    bundle_id=row["bundle_id"],
                    project_id=row["project_id"],
                    target_profile=row["target_profile"],
                    execution_mode=row["execution_mode"],
                    source_revision=row["source_revision"],
                    manifest=json.loads(row["manifest_json"]),
                    signature=json.loads(row["signature_json"]),
                    key_id=row["key_id"],
                    blob_digest=row["blob_digest"],
                    created_at=row["created_at"],
                    created_by=row["created_by"],
                )
            )
        return records


class ArtifactRepository:
    """Repository for tracking content-addressed artifact blob metadata."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def register(
        self,
        *,
        digest: str,
        size_bytes: int,
        media_type: str,
        storage_path: str | None = None,
        created_by: str | None = None,
    ) -> None:
        now = datetime.now(UTC).isoformat()
        self.conn.execute(
            """
            INSERT OR IGNORE INTO artifacts (
                digest, size_bytes, media_type, storage_path, created_at, created_by
            ) VALUES (?, ?, ?, ?, ?, ?);
            """,
            (digest.lower().strip(), size_bytes, media_type, storage_path, now, created_by),
        )
        self.conn.commit()

    def get(self, digest: str) -> dict[str, Any] | None:
        cursor = self.conn.execute(
            """
            SELECT digest, size_bytes, media_type, storage_path, created_at, created_by
            FROM artifacts
            WHERE digest = ?;
            """,
            (digest.lower().strip(),),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return dict(row)


class AuditRepository:
    """Repository for immutable audit event logs."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def record(
        self,
        *,
        event_type: str,
        entity_type: str,
        entity_id: str,
        details: dict[str, Any],
        performed_by: str | None = None,
    ) -> None:
        now = datetime.now(UTC).isoformat()
        self.conn.execute(
            """
            INSERT INTO audit_journal (
                event_type, entity_type, entity_id, details_json, performed_by, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?);
            """,
            (event_type, entity_type, entity_id, json.dumps(details), performed_by, now),
        )
        self.conn.commit()


AUTHORIZED_APPROVAL_ROLES: frozenset[str] = frozenset(
    {"process_engineer", "automation_engineer", "administrator", "safety_engineer"}
)


class RecipeApprovalRepository:
    """Repository for append-only recipe approval ledger and two-role production authorization."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def record_approval(
        self,
        *,
        project_id: str,
        recipe_id: str,
        version: int,
        role: str,
        approver_id: str,
        decision: str = "approved",
        comments: str | None = None,
        signature: str | None = None,
    ) -> tuple[RecipeApprovalRecord, RecipeApprovalSummary]:
        # Fetch recipe record
        cursor = self.conn.execute(
            """
            SELECT id, project_id, recipe_id, version, name, status,
                   schema_sha256, recipe_sha256, recipe_json, created_at, created_by
            FROM recipes
            WHERE project_id = ? AND recipe_id = ? AND version = ?;
            """,
            (project_id, recipe_id, version),
        )
        row = cursor.fetchone()
        if row is None:
            raise NotFoundError(
                f"Recipe '{recipe_id}' version '{version}' not found in project '{project_id}'."
            )

        recipe_record_id = row["id"]
        recipe_sha256 = row["recipe_sha256"]
        recipe_status = row["status"]

        approval_id = str(uuid4())

        now = datetime.now(UTC).isoformat()

        self.conn.execute(
            """
            INSERT INTO recipe_approvals (
                id, recipe_record_id, project_id, recipe_id, version, recipe_sha256,
                role, approver_id, decision, comments, signature, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                approval_id,
                recipe_record_id,
                project_id,
                recipe_id,
                version,
                recipe_sha256,
                role,
                approver_id,
                decision,
                comments,
                signature,
                now,
            ),
        )
        self.conn.commit()

        approval_record = RecipeApprovalRecord(
            id=approval_id,
            recipe_record_id=recipe_record_id,
            project_id=project_id,
            recipe_id=recipe_id,
            version=version,
            recipe_sha256=recipe_sha256,
            role=role,
            approver_id=approver_id,
            decision=decision,
            comments=comments,
            signature=signature,
            created_at=now,
        )

        summary = self.get_approval_summary(project_id, recipe_id, version)
        if summary.is_approved_for_production and recipe_status != "APPROVED":
            self.conn.execute(
                "UPDATE recipes SET status = 'APPROVED' WHERE id = ?;",
                (recipe_record_id,),
            )
            self.conn.commit()
            summary = self.get_approval_summary(project_id, recipe_id, version)

        return approval_record, summary

    def list_approvals(
        self, project_id: str, recipe_id: str, version: int
    ) -> list[RecipeApprovalRecord]:
        cursor = self.conn.execute(
            """
            SELECT id, recipe_record_id, project_id, recipe_id, version, recipe_sha256,
                   role, approver_id, decision, comments, signature, created_at
            FROM recipe_approvals
            WHERE project_id = ? AND recipe_id = ? AND version = ?
            ORDER BY created_at ASC;
            """,
            (project_id, recipe_id, version),
        )
        records: list[RecipeApprovalRecord] = []
        for row in cursor.fetchall():
            records.append(
                RecipeApprovalRecord(
                    id=row["id"],
                    recipe_record_id=row["recipe_record_id"],
                    project_id=row["project_id"],
                    recipe_id=row["recipe_id"],
                    version=row["version"],
                    recipe_sha256=row["recipe_sha256"],
                    role=row["role"],
                    approver_id=row["approver_id"],
                    decision=row["decision"],
                    comments=row["comments"],
                    signature=row["signature"],
                    created_at=row["created_at"],
                )
            )
        return records

    def get_approval_summary(
        self, project_id: str, recipe_id: str, version: int
    ) -> RecipeApprovalSummary:
        cursor = self.conn.execute(
            """
            SELECT id, name, status, recipe_sha256, created_by
            FROM recipes
            WHERE project_id = ? AND recipe_id = ? AND version = ?;
            """,
            (project_id, recipe_id, version),
        )
        row = cursor.fetchone()
        if row is None:
            raise NotFoundError(
                f"Recipe '{recipe_id}' version '{version}' not found in project '{project_id}'."
            )

        approvals = self.list_approvals(project_id, recipe_id, version)
        created_by = row["created_by"]

        # Evaluate dual-role production approval:
        # 1. Decision must be 'approved'
        # 2. Role must be in authorized set
        # 3. No self-approval: approver_id cannot be the recipe author (created_by)
        # 4. Must have >= 2 distinct approvers with >= 2 distinct roles
        valid_role_approvers: dict[str, str] = {}  # approver_id -> role
        distinct_roles: set[str] = set()

        for app in approvals:
            if app.decision.lower() == "approved" and app.role in AUTHORIZED_APPROVAL_ROLES:
                if created_by and app.approver_id == created_by:
                    # Self-approval by author is rejected from counting towards
                    # dual-role certification
                    continue

                if app.approver_id not in valid_role_approvers:
                    valid_role_approvers[app.approver_id] = app.role
                    distinct_roles.add(app.role)

        is_approved_for_prod = len(valid_role_approvers) >= 2 and len(distinct_roles) >= 2

        return RecipeApprovalSummary(
            recipe_id=recipe_id,
            version=version,
            name=row["name"],
            status=row["status"],
            recipe_sha256=row["recipe_sha256"],
            created_by=created_by,
            approvals=approvals,
            is_approved_for_production=is_approved_for_prod,
        )


class EvidenceRepository:
    """Repository for content-addressed evidence records."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def create(self, record: EvidenceRecordCreate, created_by: str | None = None) -> EvidenceRecord:
        existing = self.get(record.evidence_id)
        if existing is not None:
            if existing.artifact_sha256 == record.artifact_sha256 and existing.kind == record.kind:
                return existing
            raise ConflictError(
                f"Evidence record '{record.evidence_id}' already exists with different content."
            )

        now = datetime.now(UTC).isoformat()
        self.conn.execute(
            """
            INSERT INTO evidence_records (
                id, schema_version, kind, cell_id, subject_json, artifact_sha256,
                issuer, valid_until, signature, metadata_json, created_at, created_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                record.evidence_id,
                record.schema_version,
                record.kind,
                record.cell_id,
                json.dumps(record.subject, sort_keys=True),
                record.artifact_sha256.lower().strip(),
                record.issuer,
                record.valid_until,
                record.signature,
                json.dumps(record.metadata, sort_keys=True),
                now,
                created_by,
            ),
        )
        self.conn.commit()
        return self.get(record.evidence_id)  # type: ignore[return-value]

    def get(self, evidence_id: str) -> EvidenceRecord | None:
        cursor = self.conn.execute(
            """
            SELECT id, schema_version, kind, cell_id, subject_json, artifact_sha256,
                   issuer, valid_until, signature, metadata_json, created_at, created_by
            FROM evidence_records
            WHERE id = ?;
            """,
            (evidence_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return EvidenceRecord(
            id=row["id"],
            schema_version=row["schema_version"],
            kind=row["kind"],
            cell_id=row["cell_id"],
            subject=json.loads(row["subject_json"]),
            artifact_sha256=row["artifact_sha256"],
            issuer=row["issuer"],
            valid_until=row["valid_until"],
            signature=row["signature"],
            metadata=json.loads(row["metadata_json"]),
            created_at=row["created_at"],
            created_by=row["created_by"],
        )

    def list(
        self,
        *,
        cell_id: str | None = None,
        kind: str | None = None,
        artifact_sha256: str | None = None,
    ) -> list[EvidenceRecord]:
        clauses: list[str] = []
        params: list[Any] = []
        if cell_id is not None:
            clauses.append("cell_id = ?")
            params.append(cell_id)
        if kind is not None:
            clauses.append("kind = ?")
            params.append(kind)
        if artifact_sha256 is not None:
            clauses.append("artifact_sha256 = ?")
            params.append(artifact_sha256.lower().strip())

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"""
            SELECT id, schema_version, kind, cell_id, subject_json, artifact_sha256,
                   issuer, valid_until, signature, metadata_json, created_at, created_by
            FROM evidence_records
            {where}
            ORDER BY created_at DESC;
        """
        cursor = self.conn.execute(sql, tuple(params))
        records: list[EvidenceRecord] = []
        for row in cursor.fetchall():
            records.append(
                EvidenceRecord(
                    id=row["id"],
                    schema_version=row["schema_version"],
                    kind=row["kind"],
                    cell_id=row["cell_id"],
                    subject=json.loads(row["subject_json"]),
                    artifact_sha256=row["artifact_sha256"],
                    issuer=row["issuer"],
                    valid_until=row["valid_until"],
                    signature=row["signature"],
                    metadata=json.loads(row["metadata_json"]),
                    created_at=row["created_at"],
                    created_by=row["created_by"],
                )
            )
        return records


class ProductionSyncRepository:
    """Repository for idempotent synchronization of locally authoritative production records."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def sync_batch(
        self,
        *,
        cell_id: str,
        jobs: list[ProductionJobRecord],
        traces: list[ProductionTraceRecord],
        results: list[ProductionResultRecord],
        attachments: list[ProductionAttachmentRecord],
    ) -> SyncBatchResponse:
        now = datetime.now(UTC).isoformat()
        ack_jobs: list[str] = []
        ack_traces: list[str] = []
        ack_results: list[str] = []
        ack_attachments: list[str] = []

        # 1. Sync Jobs
        for job in jobs:
            self.conn.execute(
                """
                INSERT INTO production_jobs (
                    idempotency_key, cell_id, job_id, request_hash, status,
                    frozen_json, result_json, synced_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (idempotency_key) DO UPDATE SET
                    status = excluded.status,
                    result_json = coalesce(excluded.result_json, production_jobs.result_json),
                    synced_at = excluded.synced_at;
                """,
                (
                    job.idempotency_key,
                    job.cell_id,
                    job.job_id,
                    job.request_hash,
                    job.status,
                    job.frozen_json,
                    job.result_json,
                    now,
                    job.created_at,
                ),
            )
            ack_jobs.append(job.idempotency_key)

        # 2. Sync Traces
        for trace in traces:
            trace_key = f"{trace.trace_id}:{trace.sequence}"
            self.conn.execute(
                """
                INSERT INTO production_traces (
                    id, trace_id, sequence, cell_id, job_id, component_instance_id,
                    command_id, event_type, severity, bundle_id, source_revision,
                    recipe_id, recipe_version, recipe_sha256, task_id, task_sha256,
                    execution_mode, payload_json, timestamp, synced_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (id) DO NOTHING;
                """,
                (
                    trace_key,
                    trace.trace_id,
                    trace.sequence,
                    trace.cell_id,
                    trace.job_id,
                    trace.component_instance_id,
                    trace.command_id,
                    trace.event_type,
                    trace.severity,
                    trace.bundle_id,
                    trace.source_revision,
                    trace.recipe_id,
                    trace.recipe_version,
                    trace.recipe_sha256,
                    trace.task_id,
                    trace.task_sha256,
                    trace.execution_mode,
                    json.dumps(trace.payload, sort_keys=True),
                    trace.timestamp,
                    now,
                ),
            )
            ack_traces.append(trace.trace_id)

        # 3. Sync Results
        for result in results:
            result_key = f"{result.cell_id}:{result.job_id}:{result.trace_id}"
            self.conn.execute(
                """
                INSERT INTO production_results (
                    id, cell_id, job_id, trace_id, success, result_code,
                    result_message, output_payload_json, completed_at, synced_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (id) DO NOTHING;
                """,
                (
                    result_key,
                    result.cell_id,
                    result.job_id,
                    result.trace_id,
                    1 if result.success else 0,
                    result.result_code,
                    result.result_message,
                    result.output_payload_json,
                    result.completed_at,
                    now,
                ),
            )
            ack_results.append(result.trace_id)

        # 4. Sync Attachments
        for att in attachments:
            att_key = f"{att.digest}:{att.trace_id}:{att.filename}"
            self.conn.execute(
                """
                INSERT INTO production_attachments (
                    id, digest, cell_id, job_id, trace_id, filename,
                    media_type, size_bytes, synced_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (id) DO NOTHING;
                """,
                (
                    att_key,
                    att.digest.lower().strip(),
                    att.cell_id,
                    att.job_id,
                    att.trace_id,
                    att.filename,
                    att.media_type,
                    att.size_bytes,
                    now,
                ),
            )
            ack_attachments.append(att_key)

        self.conn.commit()

        return SyncBatchResponse(
            acknowledged_job_keys=list(dict.fromkeys(ack_jobs)),
            acknowledged_trace_ids=list(dict.fromkeys(ack_traces)),
            acknowledged_result_ids=list(dict.fromkeys(ack_results)),
            acknowledged_attachment_ids=list(dict.fromkeys(ack_attachments)),
            server_timestamp=now,
        )

    def list_jobs(
        self, *, cell_id: str | None = None, job_id: str | None = None
    ) -> list[ProductionJobRecord]:
        clauses: list[str] = []
        params: list[Any] = []
        if cell_id is not None:
            clauses.append("cell_id = ?")
            params.append(cell_id)
        if job_id is not None:
            clauses.append("job_id = ?")
            params.append(job_id)

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"""
            SELECT idempotency_key, cell_id, job_id, request_hash, status,
                   frozen_json, result_json, created_at
            FROM production_jobs
            {where}
            ORDER BY created_at DESC;
        """
        cursor = self.conn.execute(sql, tuple(params))
        jobs: list[ProductionJobRecord] = []
        for row in cursor.fetchall():
            jobs.append(
                ProductionJobRecord(
                    idempotency_key=row["idempotency_key"],
                    cell_id=row["cell_id"],
                    job_id=row["job_id"],
                    request_hash=row["request_hash"],
                    status=row["status"],
                    frozen_json=row["frozen_json"],
                    result_json=row["result_json"],
                    created_at=row["created_at"],
                )
            )
        return jobs

    def list_traces(
        self, *, trace_id: str | None = None, cell_id: str | None = None
    ) -> list[ProductionTraceRecord]:
        clauses: list[str] = []
        params: list[Any] = []
        if trace_id is not None:
            clauses.append("trace_id = ?")
            params.append(trace_id)
        if cell_id is not None:
            clauses.append("cell_id = ?")
            params.append(cell_id)

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"""
            SELECT trace_id, sequence, cell_id, job_id, component_instance_id, command_id,
                   event_type, severity, bundle_id, source_revision, recipe_id,
                   recipe_version, recipe_sha256, task_id, task_sha256, execution_mode,
                   payload_json, timestamp
            FROM production_traces
            {where}
            ORDER BY sequence ASC;
        """
        cursor = self.conn.execute(sql, tuple(params))
        traces: list[ProductionTraceRecord] = []
        for row in cursor.fetchall():
            traces.append(
                ProductionTraceRecord(
                    trace_id=row["trace_id"],
                    sequence=row["sequence"],
                    cell_id=row["cell_id"],
                    job_id=row["job_id"],
                    component_instance_id=row["component_instance_id"],
                    command_id=row["command_id"],
                    event_type=row["event_type"],
                    severity=row["severity"],
                    bundle_id=row["bundle_id"] or "",
                    source_revision=row["source_revision"] or "",
                    recipe_id=row["recipe_id"] or "",
                    recipe_version=row["recipe_version"] or 0,
                    recipe_sha256=row["recipe_sha256"] or "",
                    task_id=row["task_id"] or "",
                    task_sha256=row["task_sha256"] or "",
                    execution_mode=row["execution_mode"] or "",
                    payload=json.loads(row["payload_json"]),
                    timestamp=row["timestamp"],
                )
            )
        return traces

    def list_results(
        self, *, cell_id: str | None = None, trace_id: str | None = None
    ) -> list[ProductionResultRecord]:
        clauses: list[str] = []
        params: list[Any] = []
        if cell_id is not None:
            clauses.append("cell_id = ?")
            params.append(cell_id)
        if trace_id is not None:
            clauses.append("trace_id = ?")
            params.append(trace_id)

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"""
            SELECT cell_id, job_id, trace_id, success, result_code,
                   result_message, output_payload_json, completed_at
            FROM production_results
            {where}
            ORDER BY completed_at DESC;
        """
        cursor = self.conn.execute(sql, tuple(params))
        results: list[ProductionResultRecord] = []
        for row in cursor.fetchall():
            results.append(
                ProductionResultRecord(
                    cell_id=row["cell_id"],
                    job_id=row["job_id"],
                    trace_id=row["trace_id"],
                    success=bool(row["success"]),
                    result_code=row["result_code"],
                    result_message=row["result_message"],
                    output_payload_json=row["output_payload_json"],
                    completed_at=row["completed_at"],
                )
            )
        return results

    def list_attachments(
        self, *, cell_id: str | None = None, trace_id: str | None = None
    ) -> list[ProductionAttachmentRecord]:
        clauses: list[str] = []
        params: list[Any] = []
        if cell_id is not None:
            clauses.append("cell_id = ?")
            params.append(cell_id)
        if trace_id is not None:
            clauses.append("trace_id = ?")
            params.append(trace_id)

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"""
            SELECT digest, cell_id, job_id, trace_id, filename, media_type, size_bytes
            FROM production_attachments
            {where}
            ORDER BY synced_at DESC;
        """
        cursor = self.conn.execute(sql, tuple(params))
        attachments: list[ProductionAttachmentRecord] = []
        for row in cursor.fetchall():
            attachments.append(
                ProductionAttachmentRecord(
                    digest=row["digest"],
                    cell_id=row["cell_id"],
                    job_id=row["job_id"],
                    trace_id=row["trace_id"],
                    filename=row["filename"],
                    media_type=row["media_type"],
                    size_bytes=row["size_bytes"],
                )
            )
        return attachments
