"""Tests for cell projects, recipes, and release bundle publishing."""

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
        dev_user="automation-lead",
        dev_role="automation_engineer",
        app=app,
    )


def test_project_and_recipe_lifecycle(platform_client: PlatformClient) -> None:
    # Register project
    proj = platform_client.register_project(
        cell_id="cell.laser_marking.01",
        name="Laser Marking Cell #1",
        cell_yaml_sha256="1" * 64,
        scene_sha256="2" * 64,
        description="High precision laser marking workcell",
        git_repo="https://git.internal/cells/laser-01",
        git_revision="c" * 40,
        metadata={"facility": "Factory-A", "line": "Line-3"},
    )
    assert proj.cell_id == "cell.laser_marking.01"
    assert proj.metadata["facility"] == "Factory-A"

    # Retrieve project
    p = platform_client.get_project("cell.laser_marking.01")
    assert p.id == proj.id
    assert p.name == "Laser Marking Cell #1"

    # Publish recipe
    rec = platform_client.publish_recipe(
        cell_id="cell.laser_marking.01",
        recipe_id="engrave_serial_plate",
        version=1,
        name="Engrave Serial Plate v1",
        schema_sha256="3" * 64,
        recipe_data={"text": "CELLFORGE-2026", "power_pct": 85, "speed_mms": 120},
        status="approved",
    )
    assert rec.recipe_id == "engrave_serial_plate"
    assert rec.version == 1
    assert rec.status == "approved"

    # List recipes
    recipes = platform_client.list_recipes("cell.laser_marking.01")
    assert len(recipes) == 1
    assert recipes[0].id == rec.id

    # Conflict on republishing recipe v1 with different data
    with pytest.raises(PlatformClientError) as exc_info:
        platform_client.publish_recipe(
            cell_id="cell.laser_marking.01",
            recipe_id="engrave_serial_plate",
            version=1,
            name="Engrave Serial Plate v1 Modified",
            schema_sha256="3" * 64,
            recipe_data={"text": "ALTERED-TEXT", "power_pct": 99},
        )
    assert exc_info.value.status_code == 409


def test_bundle_publication_and_download(platform_client: PlatformClient) -> None:
    bundle_bytes = b"IMMUTABLE-SIGNED-BUNDLE-ARCHIVE-BYTES"
    manifest = {
        "bundle_id": "bundle-pen-cell-sim-2026",
        "target_profile": "simulation_cpu_linux_x86_64",
        "execution_mode": "simulation",
        "source_revision": "e" * 40,
    }
    signature = {
        "algorithm": "ed25519",
        "key_id": "cellforge-release-key-1",
        "signature_base64": "SGVsbG9Xb3JsZFNpZ25hdHVyZQ==",
    }
    checksums = "1234567890abcdef  manifest.json\n"

    # Publish bundle
    bundle = platform_client.publish_bundle(
        bundle_id="bundle-pen-cell-sim-2026",
        target_profile="simulation_cpu_linux_x86_64",
        execution_mode="simulation",
        source_revision="e" * 40,
        manifest=manifest,
        signature=signature,
        checksums_txt=checksums,
        bundle_bytes=bundle_bytes,
        project_id="cell.laser_marking.01",
    )
    assert bundle.bundle_id == "bundle-pen-cell-sim-2026"
    assert bundle.key_id == "cellforge-release-key-1"
    assert bundle.blob_digest is not None

    # Retrieve bundle
    b_retrieved = platform_client.get_bundle("bundle-pen-cell-sim-2026")
    assert b_retrieved.id == bundle.id

    # Download bundle
    downloaded = platform_client.download_bundle("bundle-pen-cell-sim-2026")
    assert downloaded == bundle_bytes

    # Conflict on republishing with different revision
    with pytest.raises(PlatformClientError) as exc_info:
        platform_client.publish_bundle(
            bundle_id="bundle-pen-cell-sim-2026",
            target_profile="simulation_cpu_linux_x86_64",
            execution_mode="simulation",
            source_revision="f" * 40,
            manifest=manifest,
            signature=signature,
            checksums_txt=checksums,
        )
    assert exc_info.value.status_code == 409
