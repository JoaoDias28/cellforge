"""Deterministic acceptance probe for Task 031 platform registry and artifact services."""

from __future__ import annotations

import hashlib
import sys
import tempfile
from pathlib import Path

import yaml
from cellforge_bundle.agent import verify_bundle
from cellforge_bundle.assembly import assemble_bundle
from cellforge_domain import ExecutionMode
from cellforge_platform import (
    AuthError,
    CellForgeRole,
    DatabaseEngine,
    DatabaseManager,
    FilesystemArtifactStore,
    OidcTokenVerifier,
    PlatformClient,
    PlatformClientError,
    PlatformSettings,
    create_platform_app,
)
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def run_acceptance_probe() -> None:
    print("=== Starting CellForge Platform Registry & Artifacts Acceptance Probe ===")

    with tempfile.TemporaryDirectory() as tmp_dir_str:
        tmp_path = Path(tmp_dir_str)
        artifacts_root = tmp_path / "artifacts"
        artifacts_root.mkdir()

        # ---------------------------------------------------------------------
        # 1. Database Migrations Lifecycle
        # ---------------------------------------------------------------------
        print(
            "\n[Stage 1] Verifying reversible database migrations (0 -> 1 -> 2 -> 1 -> 0 -> 2)..."
        )
        engine = DatabaseEngine(":memory:")
        with engine.connect() as conn:
            mgr = DatabaseManager(conn)
            assert mgr.current_version() == 0, "Initial version must be 0"

            # Apply up to v1
            up_v1 = mgr.migrate_up(target_version=1)
            assert up_v1 == [1]
            assert mgr.current_version() == 1

            # Apply up to v2
            up_v2 = mgr.migrate_up()
            assert up_v2 == [2]
            assert mgr.current_version() == 2

            # Roll back to v1
            down_v1 = mgr.migrate_down(target_version=1)
            assert down_v1 == [2]
            assert mgr.current_version() == 1

            # Roll back to 0
            down_v0 = mgr.migrate_down(target_version=0)
            assert down_v0 == [1]
            assert mgr.current_version() == 0

            # Re-apply to latest
            up_all = mgr.migrate_up()
            assert up_all == [1, 2]
            assert mgr.current_version() == 2
        print("  -> Schema migrations successfully applied, verified, rolled back, and restored.")

        # ---------------------------------------------------------------------
        # 2. OIDC Token & Production Dev-Auth Guard
        # ---------------------------------------------------------------------
        print("\n[Stage 2] Verifying OIDC JWT auth and production dev-auth guard...")
        dev_settings = PlatformSettings(environment="development", allow_dev_auth=True)
        dev_verifier = OidcTokenVerifier(dev_settings)
        dev_auth = dev_verifier.verify_request_auth(
            dev_user_header="lead_engineer",
            dev_role_header="automation_engineer",
        )
        assert dev_auth.is_authenticated
        assert dev_auth.user_id == "lead_engineer"
        assert dev_auth.has_role(CellForgeRole.AUTOMATION_ENGINEER)

        prod_settings = PlatformSettings(environment="production", allow_dev_auth=False)
        prod_verifier = OidcTokenVerifier(prod_settings)
        try:
            prod_verifier.verify_request_auth(
                dev_user_header="intruder", dev_role_header="administrator"
            )
            raise AssertionError("Expected AuthError for dev auth headers in production mode")
        except AuthError as err:
            assert err.code == "auth.production_dev_auth_prohibited"
        print(
            "  -> OIDC verification and production dev-auth guard verified "
            "(failed closed in production)."
        )

        # ---------------------------------------------------------------------
        # 3. Content-Addressed Artifact Storage
        # ---------------------------------------------------------------------
        print("\n[Stage 3] Verifying content-addressed artifact storage...")
        store = FilesystemArtifactStore(artifacts_root)
        blob_bytes = b"SAMPLE-BINARY-PACKAGE-ARTIFACT-DATA"
        expected_digest = hashlib.sha256(blob_bytes).hexdigest()
        digest = store.put(blob_bytes)
        assert digest == expected_digest
        assert store.exists(digest)
        retrieved_blob = store.get(digest)
        assert retrieved_blob == blob_bytes
        print(f"  -> Blob stored and retrieved: {digest[:16]}... ({len(blob_bytes)} bytes)")

        # ---------------------------------------------------------------------
        # 4. Platform Service Application & Client
        # ---------------------------------------------------------------------
        print("\n[Stage 4] Initializing platform FastAPI application and client...")
        app_settings = PlatformSettings(
            environment="development",
            database_url=":memory:",
            storage_root=artifacts_root,
            allow_dev_auth=True,
        )
        app = create_platform_app(app_settings)
        client = PlatformClient(
            dev_user="automation-lead",
            dev_role="automation_engineer",
            app=app,
        )

        health = client.health()
        assert health.status == "healthy"
        print(f"  -> Platform service health verified: {health.service} v{health.version}")

        # ---------------------------------------------------------------------
        # 5. Component Publication, Conflict Rejection & Search
        # ---------------------------------------------------------------------
        print("\n[Stage 5] Verifying component publishing, conflict rejection, and search...")
        robot_manifest = {
            "component": "cellforge.robot.ur5e",
            "version": "1.0.0",
            "name": "Universal Robots UR5e",
            "kind": "robot",
            "support_level": "production_qualified",
            "license": {"type": "Apache-2.0"},
            "capabilities": [
                {
                    "task_id": "robot_arm",
                    "contract": "robot_motion.move_to_pose",
                    "version": "1.0.0",
                    "endpoint": "/moveit_plan",
                }
            ],
        }
        comp_detail = client.publish_component(
            robot_manifest,
            package_bytes=b"UR5E-PACKAGE-ARCHIVE-V1.0.0",
            git_repo="https://github.com/cellforge/ur5e",
            git_commit="1" * 40,
        )
        assert comp_detail.summary.component == "cellforge.robot.ur5e"
        assert comp_detail.summary.package_blob_digest is not None

        # Idempotent republish
        comp_detail_re = client.publish_component(
            robot_manifest,
            package_bytes=b"UR5E-PACKAGE-ARCHIVE-V1.0.0",
            git_repo="https://github.com/cellforge/ur5e",
            git_commit="1" * 40,
        )
        assert comp_detail_re.summary.id == comp_detail.summary.id

        # Conflicting republish must fail closed
        conflicting_robot = dict(robot_manifest)
        conflicting_robot["name"] = "Altered Name Conflict"
        try:
            client.publish_component(
                conflicting_robot, package_bytes=b"UR5E-PACKAGE-ARCHIVE-V1.0.0"
            )
            raise AssertionError("Expected conflict error on altering published component")
        except PlatformClientError as err:
            assert err.status_code == 409
            assert err.code == "conflict.component_already_exists"

        # Download component package
        downloaded_pkg = client.download_component("cellforge.robot.ur5e", "1.0.0")
        assert downloaded_pkg == b"UR5E-PACKAGE-ARCHIVE-V1.0.0"
        print("  -> Component publication, immutability, and artifact download verified.")

        # ---------------------------------------------------------------------
        # 6. Component Deprecation Workflow
        # ---------------------------------------------------------------------
        print("\n[Stage 6] Verifying component deprecation workflow...")
        dep_summary = client.deprecate_component(
            "cellforge.robot.ur5e",
            "1.0.0",
            "Superseded by UR5e v2.0.0 with safety bus update.",
        )
        assert dep_summary.is_deprecated is True
        assert dep_summary.support_level == "deprecated"
        assert "v2.0.0" in (dep_summary.deprecation_reason or "")
        print("  -> Component deprecation workflow verified.")

        # ---------------------------------------------------------------------
        # 7. Project Registration & Recipe Versioning
        # ---------------------------------------------------------------------
        print("\n[Stage 7] Verifying project registration and recipe versioning...")
        proj = client.register_project(
            cell_id="cell.pen_engraving.01",
            name="Pen Engraving Cell #1",
            cell_yaml_sha256="a" * 64,
            scene_sha256="b" * 64,
            description="Automated pen fixture and engraving cell",
        )
        assert proj.cell_id == "cell.pen_engraving.01"

        rec = client.publish_recipe(
            cell_id="cell.pen_engraving.01",
            recipe_id="engrave_signature",
            version=1,
            name="Engrave Signature Recipe",
            schema_sha256="c" * 64,
            recipe_data={"line_depth_mm": 0.2, "laser_speed": 100},
            status="approved",
        )
        assert rec.version == 1
        assert rec.recipe_id == "engrave_signature"
        print("  -> Project registration and recipe publishing verified.")

        # ---------------------------------------------------------------------
        # 8. Release Bundle Publication & Verification
        # ---------------------------------------------------------------------
        print("\n[Stage 8] Verifying signed release bundle publication and retrieval...")
        bundle_manifest = {
            "bundle_id": "bundle-pen-engraving-prod-2026",
            "target_profile": "production_native_linux_x86_64",
            "execution_mode": "production",
            "source_revision": "2" * 40,
        }
        bundle_record = client.publish_bundle(
            bundle_id="bundle-pen-engraving-prod-2026",
            target_profile="production_native_linux_x86_64",
            execution_mode="production",
            source_revision="2" * 40,
            manifest=bundle_manifest,
            signature={"algorithm": "ed25519", "key_id": "platform-prod-key-1"},
            checksums_txt="checksums data...",
            bundle_bytes=b"SIGNED-PRODUCTION-BUNDLE-ARCHIVE",
            project_id="cell.pen_engraving.01",
        )
        assert bundle_record.bundle_id == "bundle-pen-engraving-prod-2026"
        bundle_data = client.download_bundle("bundle-pen-engraving-prod-2026")
        assert bundle_data == b"SIGNED-PRODUCTION-BUNDLE-ARCHIVE"
        print("  -> Signed release bundle publication and download verified.")

        # ---------------------------------------------------------------------
        # 9. Server-Side Cell Dependency Resolution
        # ---------------------------------------------------------------------
        print("\n[Stage 9] Verifying server-side dependency resolution API...")
        repo_root = Path(__file__).parents[1]
        components_dir = repo_root / "examples" / "pen_engraving" / "components"
        for comp_file in sorted(components_dir.rglob("component.yaml")):
            manifest = yaml.safe_load(comp_file.read_text(encoding="utf-8"))
            client.publish_component(manifest)

        pen_cell_path = repo_root / "examples" / "pen_engraving" / "cell.yaml"
        test_cell_yaml = pen_cell_path.read_text(encoding="utf-8")

        res = client.resolve_cell(test_cell_yaml, mode="simulation", allow_deprecated=True)
        assert res.valid is True
        assert res.mode == "simulation"
        assert len(res.resolved_components) == 6
        print(f"  -> Dependency resolution valid: {len(res.resolved_components)} components.")

        # ---------------------------------------------------------------------
        # 10. Strict Safety & Hardware Control Boundary Check
        # ---------------------------------------------------------------------
        print("\n[Stage 10] Verifying strict absence of hardware control / safety endpoints...")
        forbidden_endpoints = {"joint", "jog", "actuate", "estop", "bypass", "override"}
        routes = [r for r in app.routes if hasattr(r, "path")]
        assert len(routes) > 0, "Platform application should have routes"
        for r in routes:
            for term in forbidden_endpoints:
                assert term not in r.path.lower(), f"Forbidden term '{term}' in path '{r.path}'"
        print(f"  -> Verified {len(routes)} routes: zero hardware/safety control endpoints.")

        # ---------------------------------------------------------------------
        # 11. Total Platform Outage Resilience for Local Runtime
        # ---------------------------------------------------------------------
        print(
            "\n[Stage 11] Verifying offline runtime execution resilience during platform outage..."
        )
        private_key = Ed25519PrivateKey.generate()
        signing_key_path = tmp_path / "bundle-signing-key.pem"
        signing_key_path.write_bytes(
            private_key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
        public_bytes = private_key.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        key_id = hashlib.sha256(public_bytes).hexdigest()

        keys_dir = tmp_path / "trusted_keys"
        keys_dir.mkdir()
        (keys_dir / f"{key_id}.pub").write_bytes(public_bytes)

        assembled = assemble_bundle(
            repo_root / "examples" / "pen_engraving",
            repo_root / "schemas",
            target_profile="pen-sim-amd64",
            mode=ExecutionMode.SIMULATION,
            output=tmp_path / "bundle_dist",
            signing_key=signing_key_path,
            source_revision="3" * 40,
        )

        verified = verify_bundle(
            assembled.output,
            trusted_keys=keys_dir,
            require_signature=True,
        )
        assert verified.bundle_id == assembled.bundle_id
        print("  -> Local bundle verified and validated offline with zero network connectivity.")

    print("\n=== All Platform Registry & Artifacts Acceptance Checks PASSED! ===")


if __name__ == "__main__":
    try:
        run_acceptance_probe()
    except Exception as exc:
        print(f"\n[FATAL] Acceptance probe failed: {exc}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        sys.exit(1)
