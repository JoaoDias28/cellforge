"""Tests for signed Ed25519 approval/evidence snapshots."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from cellforge_platform.api.router import create_platform_app
from cellforge_platform.auth.signing import PlatformSigner, PlatformVerifier
from cellforge_platform.client import PlatformClient
from cellforge_platform.config import PlatformSettings
from cellforge_platform.models import EvidenceRecordCreate


@pytest.fixture
def signer_and_app(tmp_path: Path) -> tuple[PlatformSigner, PlatformClient]:
    signer = PlatformSigner.generate(key_id="test-platform-key-1")
    settings = PlatformSettings(
        environment="development",
        database_url=":memory:",
        storage_root=tmp_path / "storage",
        allow_dev_auth=True,
    )
    app = create_platform_app(settings, platform_signer=signer)
    client = PlatformClient(app=app, dev_user="admin", dev_role="administrator")
    return signer, client


def test_signed_snapshot_generation_and_verification(
    signer_and_app: tuple[PlatformSigner, PlatformClient],
) -> None:
    signer, client = signer_and_app
    cell_id = "cell-001"

    # 1. Setup project, approved recipe, and evidence
    client.register_project(
        cell_id=cell_id,
        name="Test Cell",
        cell_yaml_sha256="a" * 64,
        scene_sha256="b" * 64,
    )

    alice_client = PlatformClient(
        app=client.app,
        dev_user="alice",
        dev_role="process_engineer",
    )
    alice_client.publish_recipe(
        cell_id=cell_id,
        recipe_id="engrave_pen",
        version=1,
        name="Pen Engraving",
        schema_sha256="c" * 64,
        recipe_data={"speed": 100},
    )

    # 2 role approvals
    bob_client = PlatformClient(
        app=client.app,
        dev_user="bob",
        dev_role="automation_engineer",
    )
    bob_client.approve_recipe(cell_id, "engrave_pen", 1, role="automation_engineer")

    carol_client = PlatformClient(
        app=client.app,
        dev_user="carol",
        dev_role="process_engineer",
    )
    carol_client.approve_recipe(cell_id, "engrave_pen", 1, role="process_engineer")

    # Upload artifact and create evidence
    digest = client.upload_artifact(b"CALIBRATION_REPORT", media_type="text/plain")
    client.create_evidence(
        EvidenceRecordCreate(
            schema_version="0.1.0",
            evidence_id=str(uuid.uuid4()),
            kind="calibration",
            cell_id=cell_id,
            subject={"cell_id": cell_id},
            artifact_sha256=digest,
            issuer="calib_tool",
        )
    )

    # 2. Generate signed evidence snapshot
    snapshot = client.generate_evidence_snapshot(cell_id)
    assert snapshot.cell_id == cell_id
    assert snapshot.key_id == "test-platform-key-1"
    assert snapshot.signature
    assert len(snapshot.recipes) == 1
    assert snapshot.recipes[0]["is_approved_for_production"] is True
    assert len(snapshot.evidence) == 1

    # 3. Verify signature using PlatformVerifier
    verifier = PlatformVerifier({"test-platform-key-1": signer.public_key_raw_b64()})
    doc_dict = snapshot.model_dump(mode="json")
    assert verifier.verify_document(doc_dict, snapshot.signature, snapshot.key_id) is True

    # 4. Tampering with snapshot fails signature verification
    tampered_doc = dict(doc_dict)
    tampered_doc["cell_id"] = "cell-TAMPERED"
    assert verifier.verify_document(tampered_doc, snapshot.signature, snapshot.key_id) is False
