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
    ProjectRecord,
    RecipeRecord,
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
