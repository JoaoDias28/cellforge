"""Tests for idempotent synchronization of production jobs, traces, results, and attachments."""

from __future__ import annotations

from pathlib import Path

import pytest
from cellforge_platform.api.router import create_platform_app
from cellforge_platform.client import PlatformClient
from cellforge_platform.config import PlatformSettings
from cellforge_platform.models import (
    ProductionAttachmentRecord,
    ProductionJobRecord,
    ProductionResultRecord,
    ProductionTraceRecord,
)


@pytest.fixture
def platform_client(tmp_path: Path) -> PlatformClient:
    settings = PlatformSettings(
        environment="development",
        database_url=":memory:",
        storage_root=tmp_path / "storage",
        allow_dev_auth=True,
    )
    app = create_platform_app(settings)
    return PlatformClient(app=app, dev_user="operator_1", dev_role="operator")


def test_idempotent_production_synchronization(platform_client: PlatformClient) -> None:
    cell_id = "cell-prod-001"

    jobs = [
        ProductionJobRecord(
            idempotency_key="key-job-1",
            cell_id=cell_id,
            job_id="job-101",
            request_hash="a" * 64,
            status="COMPLETED",
            frozen_json='{"job_id": "job-101"}',
            result_json='{"success": true}',
            created_at="2026-08-18T12:00:00Z",
        )
    ]

    traces = [
        ProductionTraceRecord(
            trace_id="trace-001",
            sequence=1,
            cell_id=cell_id,
            job_id="job-101",
            component_instance_id="robot_arm",
            command_id="cmd_move_1",
            event_type="motion_started",
            severity="info",
            payload={"pose": [1.0, 2.0, 3.0]},
            timestamp="2026-08-18T12:00:01Z",
        ),
        ProductionTraceRecord(
            trace_id="trace-001",
            sequence=2,
            cell_id=cell_id,
            job_id="job-101",
            component_instance_id="robot_arm",
            command_id="cmd_move_1",
            event_type="motion_completed",
            severity="info",
            payload={"reached": True},
            timestamp="2026-08-18T12:00:05Z",
        ),
    ]

    results = [
        ProductionResultRecord(
            cell_id=cell_id,
            job_id="job-101",
            trace_id="trace-001",
            success=True,
            result_code="SUCCESS",
            result_message="Pen engraved successfully",
            output_payload_json='{"status": "OK"}',
            completed_at="2026-08-18T12:00:10Z",
        )
    ]

    attachments = [
        ProductionAttachmentRecord(
            digest="d" * 64,
            cell_id=cell_id,
            job_id="job-101",
            trace_id="trace-001",
            filename="inspection_after.png",
            media_type="image/png",
            size_bytes=1024,
        )
    ]

    # 1. First sync batch
    ack1 = platform_client.sync_batch(
        cell_id=cell_id,
        jobs=jobs,
        traces=traces,
        results=results,
        attachments=attachments,
    )
    assert "key-job-1" in ack1.acknowledged_job_keys
    assert "trace-001" in ack1.acknowledged_trace_ids
    assert "trace-001" in ack1.acknowledged_result_ids
    assert len(ack1.acknowledged_attachment_ids) == 1

    # 2. Verify stored records
    synced_jobs = platform_client.list_production_jobs(cell_id=cell_id)
    assert len(synced_jobs) == 1
    assert synced_jobs[0].job_id == "job-101"

    synced_traces = platform_client.list_production_traces(trace_id="trace-001")
    assert len(synced_traces) == 2
    assert [t.sequence for t in synced_traces] == [1, 2]

    synced_results = platform_client.list_production_results(cell_id=cell_id)
    assert len(synced_results) == 1
    assert synced_results[0].success is True

    synced_atts = platform_client.list_production_attachments(cell_id=cell_id)
    assert len(synced_atts) == 1
    assert synced_atts[0].filename == "inspection_after.png"

    # 3. Repeated (replay) sync must NOT create duplicate records
    ack2 = platform_client.sync_batch(
        cell_id=cell_id,
        jobs=jobs,
        traces=traces,
        results=results,
        attachments=attachments,
    )
    assert "key-job-1" in ack2.acknowledged_job_keys
    assert len(platform_client.list_production_jobs(cell_id=cell_id)) == 1
    assert len(platform_client.list_production_traces(trace_id="trace-001")) == 2
    assert len(platform_client.list_production_results(cell_id=cell_id)) == 1
    assert len(platform_client.list_production_attachments(cell_id=cell_id)) == 1

    # 4. Out-of-order trace sync
    out_of_order_trace = [
        ProductionTraceRecord(
            trace_id="trace-002",
            sequence=3,
            cell_id=cell_id,
            job_id="job-102",
            component_instance_id="laser",
            command_id="cmd_engrave",
            event_type="laser_done",
            severity="info",
            timestamp="2026-08-18T12:01:10Z",
        ),
        ProductionTraceRecord(
            trace_id="trace-002",
            sequence=1,
            cell_id=cell_id,
            job_id="job-102",
            component_instance_id="laser",
            command_id="cmd_engrave",
            event_type="laser_started",
            severity="info",
            timestamp="2026-08-18T12:01:00Z",
        ),
    ]
    platform_client.sync_batch(cell_id=cell_id, traces=out_of_order_trace)
    traces_t2 = platform_client.list_production_traces(trace_id="trace-002")
    assert len(traces_t2) == 2
    # Queried traces must be sorted by monotonic sequence (1, 3)
    assert [t.sequence for t in traces_t2] == [1, 3]
