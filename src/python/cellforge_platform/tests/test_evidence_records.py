"""Tests for content-addressed evidence registry and querying."""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

import pytest
from cellforge_platform.api.router import create_platform_app
from cellforge_platform.client import PlatformClient, PlatformClientError
from cellforge_platform.config import PlatformSettings
from cellforge_platform.models import EvidenceRecordCreate


@pytest.fixture
def platform_client(tmp_path: Path) -> PlatformClient:
    settings = PlatformSettings(
        environment="development",
        database_url=":memory:",
        storage_root=tmp_path / "storage",
        allow_dev_auth=True,
    )
    app = create_platform_app(settings)
    return PlatformClient(app=app, dev_user="test_admin", dev_role="administrator")


def test_evidence_registration_and_content_addressing(platform_client: PlatformClient) -> None:
    # 1. Upload artifact blob
    blob_content = b"SIMULATION_TEST_TRACE_LOGS_SAMPLE_EVIDENCE"
    digest = platform_client.upload_artifact(blob_content, media_type="text/plain")

    # 2. Register evidence record
    evidence_id = str(uuid.uuid4())
    create_req = EvidenceRecordCreate(
        schema_version="0.1.0",
        evidence_id=evidence_id,
        kind="simulation",
        cell_id="cell-001",
        subject={"cell_id": "cell-001", "scenario_id": "engrave_pen_fault_free"},
        artifact_sha256=digest,
        issuer="test_runner_ci",
        valid_until="2030-01-01T00:00:00Z",
        signature="dummy_signature",
        metadata={"cycle_time_s": 12.5, "passed": True},
    )
    record = platform_client.create_evidence(create_req)
    assert record.id == evidence_id
    assert record.kind == "simulation"
    assert record.cell_id == "cell-001"
    assert record.artifact_sha256 == digest

    # 3. Retrieve evidence record by ID
    fetched = platform_client.get_evidence(evidence_id)
    assert fetched.id == evidence_id
    assert fetched.issuer == "test_runner_ci"

    # 4. List evidence records with filters
    records = platform_client.list_evidence(cell_id="cell-001", kind="simulation")
    assert len(records) == 1
    assert records[0].id == evidence_id

    records_empty = platform_client.list_evidence(cell_id="cell-001", kind="safety_review")
    assert len(records_empty) == 0


def test_evidence_rejects_missing_artifact_blob(platform_client: PlatformClient) -> None:
    missing_digest = hashlib.sha256(b"NON_EXISTENT_BLOB").hexdigest()
    evidence_id = str(uuid.uuid4())
    create_req = EvidenceRecordCreate(
        schema_version="0.1.0",
        evidence_id=evidence_id,
        kind="calibration",
        cell_id="cell-001",
        subject={"cell_id": "cell-001"},
        artifact_sha256=missing_digest,
        issuer="calibrator",
    )
    with pytest.raises(PlatformClientError) as exc_info:
        platform_client.create_evidence(create_req)
    assert exc_info.value.status_code == 400
    assert "evidence.artifact_not_found" in exc_info.value.code
