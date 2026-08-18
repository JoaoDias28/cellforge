"""Tests for reversible database schema migrations."""

from __future__ import annotations

import sqlite3

from cellforge_platform.database.migrations import DatabaseManager


def test_migrations_from_empty_to_latest_and_rollback() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row

    mgr = DatabaseManager(conn)
    assert mgr.current_version() == 0
    assert mgr.applied_versions() == []

    # Migrate up to version 1
    applied = mgr.migrate_up(target_version=1)
    assert applied == [1]
    assert mgr.current_version() == 1
    assert mgr.applied_versions() == [1]

    # Verify tables exist in v1
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")
    tables_v1 = {row["name"] for row in cursor.fetchall()}
    assert {
        "components",
        "projects",
        "recipes",
        "bundles",
        "artifacts",
        "audit_journal",
        "schema_migrations",
    }.issubset(tables_v1)

    # Migrate up to version 2 (latest)
    applied_v2 = mgr.migrate_up()
    assert applied_v2 == [2]
    assert mgr.current_version() == 2
    assert mgr.applied_versions() == [1, 2]

    # Verify tables in v2
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")
    tables_v2 = {row["name"] for row in cursor.fetchall()}
    assert "component_licenses" in tables_v2

    # Insert test data into tables
    conn.execute(
        """
        INSERT INTO components (
            id, component_type, version, name, kind, support_level,
            manifest_json, manifest_sha256, created_at
        ) VALUES (
            'c1', 'vendor.robot', '1.0.0', 'Test Robot', 'robot',
            'production_qualified', '{}', 'abc', '2026-01-01T00:00:00Z'
        );
        """
    )
    conn.execute(
        """
        INSERT INTO component_licenses (component_id, license_type, is_approved, created_at)
        VALUES ('c1', 'Apache-2.0', 1, '2026-01-01T00:00:00Z');
        """
    )
    conn.commit()

    # Roll back to version 1
    rolled_back_to_1 = mgr.migrate_down(target_version=1)
    assert rolled_back_to_1 == [2]
    assert mgr.current_version() == 1
    assert mgr.applied_versions() == [1]

    # Verify component data remains preserved in v1
    cursor = conn.execute("SELECT id, component_type FROM components WHERE id = 'c1';")
    row = cursor.fetchone()
    assert row is not None
    assert row["component_type"] == "vendor.robot"

    # Verify component_licenses table was dropped in down migration
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='component_licenses';"
    )
    assert cursor.fetchone() is None

    # Roll back all the way to 0
    rolled_back_to_0 = mgr.migrate_down(target_version=0)
    assert rolled_back_to_0 == [1]
    assert mgr.current_version() == 0
    assert mgr.applied_versions() == []

    # Re-apply all migrations from 0 to latest
    reapplied = mgr.migrate_up()
    assert reapplied == [1, 2]
    assert mgr.current_version() == 2
    assert mgr.applied_versions() == [1, 2]
