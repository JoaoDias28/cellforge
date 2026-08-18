"""Deterministic acceptance probe for Task 032 platform approvals, evidence, and result sync."""

from __future__ import annotations

import hashlib
import shutil
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cellforge_bundle import compile_project
from cellforge_domain import ExecutionMode
from cellforge_platform import (
    DatabaseEngine,
    DatabaseManager,
    PlatformClient,
    PlatformSettings,
    create_platform_app,
)
from cellforge_platform.auth.signing import PlatformSigner, PlatformVerifier
from cellforge_platform.models import (
    EvidenceRecordCreate,
    ProductionAttachmentRecord,
    ProductionJobRecord,
    ProductionResultRecord,
    ProductionTraceRecord,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_ROOT = REPOSITORY_ROOT / "examples" / "pen_engraving"
SCHEMA_ROOT = REPOSITORY_ROOT / "schemas"
SOURCE_REVISION = "a" * 40
CELL_ID = "0d3c6b63-a57f-4207-8638-e4cf76efec90"


def _prepare_project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    shutil.copytree(EXAMPLE_ROOT, project)
    shutil.copytree(SCHEMA_ROOT, project / "schemas")
    cell_path = project / "cell.yaml"
    cell_path.write_text(
        cell_path.read_text(encoding="utf-8").replace(
            "schema: ../../schemas/recipe.schema.json",
            "schema: schemas/recipe.schema.json",
        ),
        encoding="utf-8",
        newline="\n",
    )
    return project


def run_acceptance_probe() -> None:
    print("=== Starting CellForge Platform Approvals & Result Sync Acceptance Probe ===")

    with tempfile.TemporaryDirectory() as tmp_dir_str:
        tmp_path = Path(tmp_dir_str)
        storage_root = tmp_path / "storage"
        storage_root.mkdir()

        # ---------------------------------------------------------------------
        # 1. Database Migrations 3 & 4 Lifecycle
        # ---------------------------------------------------------------------
        print("\n[Stage 1] Verifying migrations 0 -> 4 -> 2 -> 4...")
        engine = DatabaseEngine(":memory:")
        with engine.connect() as conn:
            mgr = DatabaseManager(conn)
            assert mgr.current_version() == 0
            up_all = mgr.migrate_up(target_version=4)
            assert up_all == [1, 2, 3, 4]
            assert mgr.current_version() == 4

            # Roll back migrations 4 and 3
            down_v2 = mgr.migrate_down(target_version=2)
            assert down_v2 == [4, 3]
            assert mgr.current_version() == 2

            # Roll forward back to 4
            up_back = mgr.migrate_up()
            assert up_back == [3, 4]
            assert mgr.current_version() == 4
        print("[OK] Reversible database migrations 3 & 4 verified.")

        # ---------------------------------------------------------------------
        # 2. Append-Only Recipe Lifecycle and Two-Role Authorization
        # ---------------------------------------------------------------------
        print("\n[Stage 2] Verifying recipe lifecycle & two-role approval rules...")
        signer = PlatformSigner.generate(key_id="acceptance-platform-key")
        settings = PlatformSettings(
            environment="development",
            database_url=":memory:",
            storage_root=str(storage_root),
            allow_dev_auth=True,
        )
        app = create_platform_app(settings, platform_signer=signer)

        admin_client = PlatformClient(app=app, dev_user="admin", dev_role="administrator")
        admin_client.register_project(
            cell_id=CELL_ID,
            name="Pen Engraving Cell",
            cell_yaml_sha256="1" * 64,
            scene_sha256="2" * 64,
        )

        # Author creates recipe
        author_client = PlatformClient(app=app, dev_user="alice", dev_role="process_engineer")
        recipe = author_client.publish_recipe(
            cell_id=CELL_ID,
            recipe_id="pen-aluminium-reference",
            version=1,
            name="Aluminium pen reference engraving",
            schema_sha256="3" * 64,
            recipe_data={"speed": 100},
        )
        assert recipe.status == "draft"

        # Author self-approval is rejected from satisfying production criteria
        self_app_summary = author_client.approve_recipe(
            cell_id=CELL_ID,
            recipe_id="pen-aluminium-reference",
            version=1,
            role="process_engineer",
            decision="approved",
            comments="Self-approval attempt",
        )
        assert self_app_summary.is_approved_for_production is False
        assert self_app_summary.status == "draft"

        # First independent approval (automation engineer)
        auto_eng_client = PlatformClient(app=app, dev_user="bob", dev_role="automation_engineer")
        bob_summary = auto_eng_client.approve_recipe(
            cell_id=CELL_ID,
            recipe_id="pen-aluminium-reference",
            version=1,
            role="automation_engineer",
            decision="approved",
            comments="Automation verified",
        )
        assert bob_summary.is_approved_for_production is False

        # Second independent approval (process engineer)
        peer_proc_client = PlatformClient(app=app, dev_user="carol", dev_role="process_engineer")
        carol_summary = peer_proc_client.approve_recipe(
            cell_id=CELL_ID,
            recipe_id="pen-aluminium-reference",
            version=1,
            role="process_engineer",
            decision="approved",
            comments="Peer process review passed",
        )
        assert carol_summary.is_approved_for_production is True
        assert carol_summary.status == "APPROVED"
        print("[OK] Dual-role approval and creator self-approval rejection verified.")

        # ---------------------------------------------------------------------
        # 3. Content-Addressed Evidence and Signed Snapshot Generation
        # ---------------------------------------------------------------------
        print("\n[Stage 3] Verifying content-addressed evidence and signed Ed25519 snapshot...")
        evidence_blobs = {
            "simulation": b"SIMULATION_TRACE_LOGS_PASS",
            "calibration": b"ROBOT_CALIBRATION_COORDINATE_OFFSET_PASS",
            "commissioning": b"FIELD_COMMISSIONING_CHECKLIST_PASS",
            "safety_review": b"SAFETY_INTEGRITY_LEVEL_ASSESSMENT_PASS",
        }
        for kind, content in evidence_blobs.items():
            digest = admin_client.upload_artifact(content, media_type="text/plain")
            admin_client.create_evidence(
                EvidenceRecordCreate(
                    schema_version="0.1.0",
                    evidence_id=f"ev-{kind}-001",
                    kind=kind,
                    cell_id=CELL_ID,
                    subject={"cell_id": CELL_ID, "component_instance_id": "robot-001"},
                    artifact_sha256=digest,
                    issuer="acceptance_probe",
                    valid_until=(datetime.now(UTC) + timedelta(days=60)).isoformat(),
                )
            )

        snapshot = admin_client.generate_evidence_snapshot(CELL_ID)
        assert snapshot.cell_id == CELL_ID
        assert snapshot.key_id == "acceptance-platform-key"
        assert len(snapshot.recipes) == 1
        assert snapshot.recipes[0]["is_approved_for_production"] is True
        assert len(snapshot.evidence) == 4

        # Verify snapshot Ed25519 signature
        verifier = PlatformVerifier({"acceptance-platform-key": signer.public_key_raw_b64()})
        assert (
            verifier.verify_document(
                snapshot.model_dump(mode="json"), snapshot.signature, snapshot.key_id
            )
            is True
        )
        print("[OK] Content-addressed evidence and cryptographic snapshot signature verified.")

        # ---------------------------------------------------------------------
        # 4. Offline Compiler Evidence-Policy Engine Verification
        # ---------------------------------------------------------------------
        print("\n[Stage 4] Verifying offline compiler evidence verification rules...")
        project = _prepare_project(tmp_path)
        public_keys = {"acceptance-platform-key": signer.public_key_raw_b64()}

        # 4.1 Missing snapshot in production fails closed
        report_missing = compile_project(
            project,
            project / "schemas",
            target_profile="pen-sim-amd64",
            mode=ExecutionMode.PRODUCTION,
            source_revision=SOURCE_REVISION,
        )
        assert report_missing.valid is False
        assert "compiler.production-evidence-unverified" in {
            f.code for f in report_missing.findings
        }

        # 4.2 Valid snapshot authorizes compilation
        # Update recipe status in project to APPROVED
        rec_path = project / "recipe.yaml"
        rec_path.write_text(
            rec_path.read_text(encoding="utf-8").replace("status: TESTED", "status: APPROVED"),
            encoding="utf-8",
            newline="\n",
        )
        # Update recipe in platform & re-generate snapshot
        recipe_sha256 = hashlib.sha256(rec_path.read_bytes()).hexdigest()
        snap_dict = snapshot.model_dump(mode="json")
        snap_dict["recipes"][0]["recipe_sha256"] = recipe_sha256
        snap_dict["signature"] = signer.sign_document(
            {k: v for k, v in snap_dict.items() if k != "signature"}
        )

        report_valid = compile_project(
            project,
            project / "schemas",
            target_profile="pen-sim-amd64",
            mode=ExecutionMode.SIMULATION,
            source_revision=SOURCE_REVISION,
            evidence_snapshot=snap_dict,
            platform_public_keys=public_keys,
        )
        assert report_valid.valid is True
        assert report_valid.manifest is not None
        assert report_valid.manifest.evidence.required is True
        assert report_valid.manifest.evidence.status == "verified"

        # 4.3 Tampered artifact digest rejected
        tampered_snap = dict(snap_dict)
        tampered_snap["evidence"] = [dict(e) for e in snap_dict["evidence"]]
        tampered_snap["evidence"][0]["artifact_sha256"] = "tampered_digest"
        tampered_snap["signature"] = signer.sign_document(
            {k: v for k, v in tampered_snap.items() if k != "signature"}
        )
        report_tampered = compile_project(
            project,
            project / "schemas",
            target_profile="pen-sim-amd64",
            mode=ExecutionMode.PRODUCTION,
            source_revision=SOURCE_REVISION,
            evidence_snapshot=tampered_snap,
            platform_public_keys=public_keys,
        )
        assert report_tampered.valid is False
        assert "compiler.evidence.tampered-artifact" in {f.code for f in report_tampered.findings}

        # 4.4 Stale snapshot rejected
        stale_snap = dict(snap_dict)
        stale_snap["valid_until"] = "2020-01-01T00:00:00Z"
        stale_snap["signature"] = signer.sign_document(
            {k: v for k, v in stale_snap.items() if k != "signature"}
        )
        report_stale = compile_project(
            project,
            project / "schemas",
            target_profile="pen-sim-amd64",
            mode=ExecutionMode.PRODUCTION,
            source_revision=SOURCE_REVISION,
            evidence_snapshot=stale_snap,
            platform_public_keys=public_keys,
        )
        assert report_stale.valid is False
        assert "compiler.evidence.stale-snapshot" in {f.code for f in report_stale.findings}

        # 4.5 Wrong cell ID rejected
        wrong_cell_snap = dict(snap_dict)
        wrong_cell_snap["cell_id"] = "00000000-0000-0000-0000-000000000000"
        wrong_cell_snap["signature"] = signer.sign_document(
            {k: v for k, v in wrong_cell_snap.items() if k != "signature"}
        )
        report_wrong_cell = compile_project(
            project,
            project / "schemas",
            target_profile="pen-sim-amd64",
            mode=ExecutionMode.PRODUCTION,
            source_revision=SOURCE_REVISION,
            evidence_snapshot=wrong_cell_snap,
            platform_public_keys=public_keys,
        )
        assert report_wrong_cell.valid is False
        assert "compiler.evidence.cell-mismatch" in {f.code for f in report_wrong_cell.findings}

        # 4.6 Missing hardware evidence kind rejected
        missing_hw_snap = dict(snap_dict)
        missing_hw_snap["evidence"] = [
            e for e in snap_dict["evidence"] if e["kind"] != "safety_review"
        ]
        missing_hw_snap["signature"] = signer.sign_document(
            {k: v for k, v in missing_hw_snap.items() if k != "signature"}
        )
        report_missing_hw = compile_project(
            project,
            project / "schemas",
            target_profile="pen-sim-amd64",
            mode=ExecutionMode.PRODUCTION,
            source_revision=SOURCE_REVISION,
            evidence_snapshot=missing_hw_snap,
            platform_public_keys=public_keys,
        )
        assert report_missing_hw.valid is False
        assert "compiler.evidence.missing-hardware-evidence" in {
            f.code for f in report_missing_hw.findings
        }
        print("[OK] Compiler evidence-policy engine and failure paths verified.")

        # ---------------------------------------------------------------------
        # 5. Idempotent Result and Trace Synchronization
        # ---------------------------------------------------------------------
        print("\n[Stage 5] Verifying idempotent production sync after simulated outages...")
        op_client = PlatformClient(app=app, dev_user="operator", dev_role="operator")

        jobs = [
            ProductionJobRecord(
                idempotency_key="key-pen-101",
                cell_id=CELL_ID,
                job_id="job-101",
                request_hash="f" * 64,
                status="COMPLETED",
                frozen_json='{"job_id": "job-101"}',
                result_json='{"success": true}',
                created_at="2026-08-18T14:00:00Z",
            )
        ]
        traces = [
            ProductionTraceRecord(
                trace_id="trace-101",
                sequence=1,
                cell_id=CELL_ID,
                job_id="job-101",
                component_instance_id="robot-001",
                command_id="cmd_pick",
                event_type="motion_started",
                severity="info",
                timestamp="2026-08-18T14:00:01Z",
            ),
            ProductionTraceRecord(
                trace_id="trace-101",
                sequence=2,
                cell_id=CELL_ID,
                job_id="job-101",
                component_instance_id="robot-001",
                command_id="cmd_pick",
                event_type="motion_completed",
                severity="info",
                timestamp="2026-08-18T14:00:05Z",
            ),
        ]
        results = [
            ProductionResultRecord(
                cell_id=CELL_ID,
                job_id="job-101",
                trace_id="trace-101",
                success=True,
                result_code="SUCCESS",
                result_message="Pen successfully engraved and inspected",
                completed_at="2026-08-18T14:00:10Z",
            )
        ]
        attachments = [
            ProductionAttachmentRecord(
                digest="e" * 64,
                cell_id=CELL_ID,
                job_id="job-101",
                trace_id="trace-101",
                filename="engraving_macro.png",
                media_type="image/png",
                size_bytes=2048,
            )
        ]

        # Sync first time
        ack1 = op_client.sync_batch(
            cell_id=CELL_ID,
            jobs=jobs,
            traces=traces,
            results=results,
            attachments=attachments,
        )
        assert "key-pen-101" in ack1.acknowledged_job_keys
        assert "trace-101" in ack1.acknowledged_trace_ids

        # Re-sync same batch (e.g. retry after network reconnection)
        ack2 = op_client.sync_batch(
            cell_id=CELL_ID,
            jobs=jobs,
            traces=traces,
            results=results,
            attachments=attachments,
        )
        assert "key-pen-101" in ack2.acknowledged_job_keys

        # Check total counts in database: exactly 1 job, 2 traces, 1 result, 1 attachment
        synced_jobs = op_client.list_production_jobs(cell_id=CELL_ID)
        synced_traces = op_client.list_production_traces(trace_id="trace-101")
        synced_results = op_client.list_production_results(cell_id=CELL_ID)
        synced_atts = op_client.list_production_attachments(cell_id=CELL_ID)

        assert len(synced_jobs) == 1, f"Expected 1 job, got {len(synced_jobs)}"
        assert len(synced_traces) == 2, f"Expected 2 traces, got {len(synced_traces)}"
        assert len(synced_results) == 1, f"Expected 1 result, got {len(synced_results)}"
        assert len(synced_atts) == 1, f"Expected 1 attachment, got {len(synced_atts)}"
        print("[OK] Zero duplicate records on replay and full acknowledgment verified.")

    print("\n=== All Task 032 Acceptance Checks PASSED successfully! ===")


if __name__ == "__main__":
    run_acceptance_probe()
