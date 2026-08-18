"""Reversible database migrations and schema version manager."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True, slots=True)
class Migration:
    """A single versioned reversible migration."""

    version: int
    name: str
    up_sql: str
    down_sql: str


MIGRATIONS: tuple[Migration, ...] = (
    Migration(
        version=1,
        name="001_initial_schema",
        up_sql="""
        CREATE TABLE IF NOT EXISTS components (
            id TEXT PRIMARY KEY,
            component_type TEXT NOT NULL,
            version TEXT NOT NULL,
            name TEXT NOT NULL,
            kind TEXT NOT NULL,
            support_level TEXT NOT NULL,
            license TEXT,
            manifest_json TEXT NOT NULL,
            manifest_sha256 TEXT NOT NULL,
            package_blob_digest TEXT,
            git_repo TEXT,
            git_commit TEXT,
            is_deprecated INTEGER NOT NULL DEFAULT 0,
            deprecation_reason TEXT,
            created_at TEXT NOT NULL,
            created_by TEXT,
            UNIQUE(component_type, version)
        );
        CREATE INDEX IF NOT EXISTS idx_components_type ON components(component_type);
        CREATE INDEX IF NOT EXISTS idx_components_kind ON components(kind);
        CREATE INDEX IF NOT EXISTS idx_components_support ON components(support_level);

        CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY,
            cell_id TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            description TEXT,
            git_repo TEXT,
            git_revision TEXT,
            cell_yaml_sha256 TEXT NOT NULL,
            scene_sha256 TEXT NOT NULL,
            metadata_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            created_by TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_projects_cell ON projects(cell_id);

        CREATE TABLE IF NOT EXISTS recipes (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            recipe_id TEXT NOT NULL,
            version INTEGER NOT NULL,
            name TEXT NOT NULL,
            status TEXT NOT NULL,
            schema_sha256 TEXT NOT NULL,
            recipe_sha256 TEXT NOT NULL,
            recipe_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            created_by TEXT,
            UNIQUE(project_id, recipe_id, version)
        );
        CREATE INDEX IF NOT EXISTS idx_recipes_proj_rec ON recipes(project_id, recipe_id);

        CREATE TABLE IF NOT EXISTS bundles (
            id TEXT PRIMARY KEY,
            bundle_id TEXT NOT NULL UNIQUE,
            project_id TEXT,
            target_profile TEXT NOT NULL,
            execution_mode TEXT NOT NULL,
            source_revision TEXT NOT NULL,
            manifest_json TEXT NOT NULL,
            signature_json TEXT NOT NULL,
            key_id TEXT,
            blob_digest TEXT,
            created_at TEXT NOT NULL,
            created_by TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_bundles_target ON bundles(target_profile);
        CREATE INDEX IF NOT EXISTS idx_bundles_mode ON bundles(execution_mode);

        CREATE TABLE IF NOT EXISTS artifacts (
            digest TEXT PRIMARY KEY,
            size_bytes INTEGER NOT NULL,
            media_type TEXT NOT NULL,
            storage_path TEXT,
            created_at TEXT NOT NULL,
            created_by TEXT
        );

        CREATE TABLE IF NOT EXISTS audit_journal (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            details_json TEXT NOT NULL,
            performed_by TEXT,
            timestamp TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_audit_entity ON audit_journal(entity_type, entity_id);
        """,
        down_sql="""
        DROP TABLE IF EXISTS audit_journal;
        DROP TABLE IF EXISTS artifacts;
        DROP TABLE IF EXISTS bundles;
        DROP TABLE IF EXISTS recipes;
        DROP TABLE IF EXISTS projects;
        DROP TABLE IF EXISTS components;
        """,
    ),
    Migration(
        version=2,
        name="002_component_licenses_and_indexes",
        up_sql="""
        CREATE TABLE IF NOT EXISTS component_licenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            component_id TEXT NOT NULL,
            license_type TEXT NOT NULL,
            is_approved INTEGER NOT NULL DEFAULT 1,
            reviewed_by TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (component_id) REFERENCES components(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_comp_lic_type ON component_licenses(license_type);
        CREATE INDEX IF NOT EXISTS idx_components_created ON components(created_at);
        """,
        down_sql="""
        DROP INDEX IF EXISTS idx_components_created;
        DROP TABLE IF EXISTS component_licenses;
        """,
    ),
    Migration(
        version=3,
        name="003_recipe_approvals_and_evidence",
        up_sql="""
        CREATE TABLE IF NOT EXISTS recipe_approvals (
            id TEXT PRIMARY KEY,
            recipe_record_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            recipe_id TEXT NOT NULL,
            version INTEGER NOT NULL,
            recipe_sha256 TEXT NOT NULL,
            role TEXT NOT NULL,
            approver_id TEXT NOT NULL,
            decision TEXT NOT NULL,
            comments TEXT,
            signature TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (recipe_record_id) REFERENCES recipes(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_rec_app_proj_rec
            ON recipe_approvals(project_id, recipe_id, version);
        CREATE INDEX IF NOT EXISTS idx_rec_app_sha ON recipe_approvals(recipe_sha256);
        CREATE INDEX IF NOT EXISTS idx_rec_app_approver ON recipe_approvals(approver_id);


        CREATE TABLE IF NOT EXISTS evidence_records (
            id TEXT PRIMARY KEY,
            schema_version TEXT NOT NULL,
            kind TEXT NOT NULL,
            cell_id TEXT NOT NULL,
            subject_json TEXT NOT NULL,
            artifact_sha256 TEXT NOT NULL,
            issuer TEXT NOT NULL,
            valid_until TEXT,
            signature TEXT,
            metadata_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            created_by TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_evidence_cell ON evidence_records(cell_id);
        CREATE INDEX IF NOT EXISTS idx_evidence_kind ON evidence_records(kind);
        CREATE INDEX IF NOT EXISTS idx_evidence_artifact ON evidence_records(artifact_sha256);
        """,
        down_sql="""
        DROP INDEX IF EXISTS idx_evidence_artifact;
        DROP INDEX IF EXISTS idx_evidence_kind;
        DROP INDEX IF EXISTS idx_evidence_cell;
        DROP TABLE IF EXISTS evidence_records;
        DROP INDEX IF EXISTS idx_rec_app_approver;
        DROP INDEX IF EXISTS idx_rec_app_sha;
        DROP INDEX IF EXISTS idx_rec_app_proj_rec;
        DROP TABLE IF EXISTS recipe_approvals;
        """,
    ),
    Migration(
        version=4,
        name="004_production_sync_records",
        up_sql="""
        CREATE TABLE IF NOT EXISTS production_jobs (
            idempotency_key TEXT PRIMARY KEY,
            cell_id TEXT NOT NULL,
            job_id TEXT NOT NULL,
            request_hash TEXT NOT NULL,
            status TEXT NOT NULL,
            frozen_json TEXT NOT NULL,
            result_json TEXT,
            synced_at TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_prod_jobs_cell ON production_jobs(cell_id);
        CREATE INDEX IF NOT EXISTS idx_prod_jobs_job ON production_jobs(job_id);

        CREATE TABLE IF NOT EXISTS production_traces (
            id TEXT PRIMARY KEY,
            trace_id TEXT NOT NULL,
            sequence INTEGER NOT NULL,
            cell_id TEXT NOT NULL,
            job_id TEXT NOT NULL,
            component_instance_id TEXT NOT NULL,
            command_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            severity TEXT NOT NULL,
            bundle_id TEXT,
            source_revision TEXT,
            recipe_id TEXT,
            recipe_version INTEGER,
            recipe_sha256 TEXT,
            task_id TEXT,
            task_sha256 TEXT,
            execution_mode TEXT,
            payload_json TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            synced_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_prod_traces_trace_seq
            ON production_traces(trace_id, sequence);
        CREATE INDEX IF NOT EXISTS idx_prod_traces_cell ON production_traces(cell_id);

        CREATE INDEX IF NOT EXISTS idx_prod_traces_job ON production_traces(job_id);

        CREATE TABLE IF NOT EXISTS production_results (
            id TEXT PRIMARY KEY,
            cell_id TEXT NOT NULL,
            job_id TEXT NOT NULL,
            trace_id TEXT NOT NULL,
            success INTEGER NOT NULL,
            result_code TEXT NOT NULL,
            result_message TEXT NOT NULL,
            output_payload_json TEXT NOT NULL,
            completed_at TEXT NOT NULL,
            synced_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_prod_results_cell ON production_results(cell_id);
        CREATE INDEX IF NOT EXISTS idx_prod_results_job ON production_results(job_id);
        CREATE INDEX IF NOT EXISTS idx_prod_results_trace ON production_results(trace_id);

        CREATE TABLE IF NOT EXISTS production_attachments (
            id TEXT PRIMARY KEY,
            digest TEXT NOT NULL,
            cell_id TEXT NOT NULL,
            job_id TEXT,
            trace_id TEXT NOT NULL,
            filename TEXT NOT NULL,
            media_type TEXT NOT NULL,
            size_bytes INTEGER NOT NULL,
            synced_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_prod_attachments_trace ON production_attachments(trace_id);
        CREATE INDEX IF NOT EXISTS idx_prod_attachments_cell ON production_attachments(cell_id);
        CREATE INDEX IF NOT EXISTS idx_prod_attachments_digest ON production_attachments(digest);
        """,
        down_sql="""
        DROP INDEX IF EXISTS idx_prod_attachments_digest;
        DROP INDEX IF EXISTS idx_prod_attachments_cell;
        DROP INDEX IF EXISTS idx_prod_attachments_trace;
        DROP TABLE IF EXISTS production_attachments;
        DROP INDEX IF EXISTS idx_prod_results_trace;
        DROP INDEX IF EXISTS idx_prod_results_job;
        DROP INDEX IF EXISTS idx_prod_results_cell;
        DROP TABLE IF EXISTS production_results;
        DROP INDEX IF EXISTS idx_prod_traces_job;
        DROP INDEX IF EXISTS idx_prod_traces_cell;
        DROP INDEX IF EXISTS idx_prod_traces_trace_seq;
        DROP TABLE IF EXISTS production_traces;
        DROP INDEX IF EXISTS idx_prod_jobs_job;
        DROP INDEX IF EXISTS idx_prod_jobs_cell;
        DROP TABLE IF EXISTS production_jobs;
        """,
    ),
)


class DatabaseManager:
    """Manages database schema creation, forward migration, and rollback."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.conn = connection
        self._ensure_migrations_table()

    def _ensure_migrations_table(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                applied_at TEXT NOT NULL
            );
            """
        )
        self.conn.commit()

    def current_version(self) -> int:
        """Return the highest applied schema migration version, or 0 if uninitialized."""
        cursor = self.conn.execute("SELECT MAX(version) FROM schema_migrations;")
        row = cursor.fetchone()
        if row is None or row[0] is None:
            return 0
        return int(row[0])

    def applied_versions(self) -> list[int]:
        """Return all applied migration versions in ascending order."""
        cursor = self.conn.execute("SELECT version FROM schema_migrations ORDER BY version ASC;")
        return [int(row[0]) for row in cursor.fetchall()]

    def migrate_up(self, target_version: int | None = None) -> list[int]:
        """Apply pending migrations up to target_version (or latest if None)."""
        current = self.current_version()
        applied: list[int] = []

        for mig in sorted(MIGRATIONS, key=lambda m: m.version):
            if mig.version <= current:
                continue
            if target_version is not None and mig.version > target_version:
                break

            self.conn.executescript(mig.up_sql)
            now = datetime.now(UTC).isoformat()
            self.conn.execute(
                "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?);",
                (mig.version, mig.name, now),
            )
            self.conn.commit()
            applied.append(mig.version)

        return applied

    def migrate_down(self, target_version: int = 0) -> list[int]:
        """Roll back applied migrations down to target_version."""
        current = self.current_version()
        rolled_back: list[int] = []

        for mig in sorted(MIGRATIONS, key=lambda m: m.version, reverse=True):
            if mig.version > current:
                continue
            if mig.version <= target_version:
                break

            self.conn.executescript(mig.down_sql)
            self.conn.execute(
                "DELETE FROM schema_migrations WHERE version = ?;",
                (mig.version,),
            )
            self.conn.commit()
            rolled_back.append(mig.version)

        return rolled_back
