"""Tests for component publishing, versioning, conflict rejection, search, and deprecation."""

from __future__ import annotations

from pathlib import Path

import pytest
from cellforge_platform import (
    PlatformClient,
    PlatformClientError,
    PlatformSettings,
    create_platform_app,
)


@pytest.fixture
def platform_client(tmp_path: Path) -> PlatformClient:
    settings = PlatformSettings(
        environment="development",
        database_url=":memory:",
        storage_root=tmp_path / "artifacts",
        allow_dev_auth=True,
    )
    app = create_platform_app(settings)
    return PlatformClient(
        dev_user="engineer1",
        dev_role="automation_engineer",
        app=app,
    )


def test_component_publish_and_retrieve(platform_client: PlatformClient) -> None:
    manifest = {
        "component": "vendor.robot.arm6",
        "version": "1.0.0",
        "name": "6-Axis Industrial Robot",
        "kind": "robot",
        "support_level": "production_qualified",
        "license": {"type": "Apache-2.0"},
        "geometry": {"cad": "robot.usda"},
    }
    package_data = b"ZIP-ARCHIVE-PAYLOAD-FOR-ROBOT-ARM6-V1.0.0"

    # Publish
    detail = platform_client.publish_component(
        manifest,
        package_bytes=package_data,
        git_repo="https://github.com/vendor/robot-arm",
        git_commit="a" * 40,
    )
    assert detail.summary.component == "vendor.robot.arm6"
    assert detail.summary.version == "1.0.0"
    assert detail.summary.kind == "robot"
    assert detail.summary.support_level == "production_qualified"
    assert detail.summary.package_blob_digest is not None
    assert detail.git_commit == "a" * 40

    # Retrieve
    retrieved = platform_client.get_component("vendor.robot.arm6", "1.0.0")
    assert retrieved.summary.id == detail.summary.id
    assert retrieved.manifest["name"] == "6-Axis Industrial Robot"

    # Download package artifact
    downloaded_bytes = platform_client.download_component("vendor.robot.arm6", "1.0.0")
    assert downloaded_bytes == package_data


def test_component_idempotent_publish_and_conflict_rejection(
    platform_client: PlatformClient,
) -> None:
    manifest_v1 = {
        "component": "vendor.gripper.two_finger",
        "version": "1.2.0",
        "name": "Parallel Gripper",
        "kind": "end_effector",
        "support_level": "bench_tested",
    }
    pkg_data = b"GRIPPER-V1.2.0"

    # Initial publish
    d1 = platform_client.publish_component(manifest_v1, package_bytes=pkg_data)

    # Idempotent re-publish of the EXACT SAME content succeeds
    d2 = platform_client.publish_component(manifest_v1, package_bytes=pkg_data)
    assert d2.summary.id == d1.summary.id

    # Publishing SAME (component, version) with DIFFERENT manifest must fail with 409 Conflict
    conflicting_manifest = {
        "component": "vendor.gripper.two_finger",
        "version": "1.2.0",
        "name": "Parallel Gripper MODIFIED",
        "kind": "end_effector",
        "support_level": "production_qualified",
    }
    with pytest.raises(PlatformClientError) as exc_info:
        platform_client.publish_component(conflicting_manifest, package_bytes=pkg_data)
    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "conflict.component_already_exists"


def test_component_search_and_deprecation(platform_client: PlatformClient) -> None:
    m1 = {
        "component": "acme.sensor.laser",
        "version": "1.0.0",
        "name": "Laser Scanner",
        "kind": "sensor",
        "support_level": "production_qualified",
    }
    m2 = {
        "component": "acme.sensor.laser",
        "version": "2.0.0",
        "name": "Laser Scanner Pro",
        "kind": "sensor",
        "support_level": "production_qualified",
    }
    m3 = {
        "component": "acme.fixture.clamp",
        "version": "1.0.0",
        "name": "Pneumatic Clamp",
        "kind": "fixture",
        "support_level": "simulated",
    }
    platform_client.publish_component(m1)
    platform_client.publish_component(m2)
    platform_client.publish_component(m3)

    # Search by kind
    sensors = platform_client.list_components(kind="sensor")
    assert len(sensors) == 2
    assert {s.version for s in sensors} == {"1.0.0", "2.0.0"}

    # Search by query
    clamps = platform_client.list_components(query="clamp")
    assert len(clamps) == 1
    assert clamps[0].component == "acme.fixture.clamp"

    # Deprecate laser v1.0.0
    dep = platform_client.deprecate_component(
        "acme.sensor.laser",
        "1.0.0",
        "Replaced by v2.0.0 with improved accuracy.",
    )
    assert dep.is_deprecated is True
    assert dep.deprecation_reason == "Replaced by v2.0.0 with improved accuracy."
    assert dep.support_level == "deprecated"

    # Verify listing excluding deprecated
    active_sensors = platform_client.list_components(kind="sensor", include_deprecated=False)
    assert len(active_sensors) == 1
    assert active_sensors[0].version == "2.0.0"
