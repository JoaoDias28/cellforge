"""Tests for server-side cell dependency resolution API."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from cellforge_platform import (
    PlatformClient,
    PlatformSettings,
    create_platform_app,
)

REPOSITORY_ROOT = Path(__file__).parents[4]


@pytest.fixture
def platform_client(tmp_path: Path) -> PlatformClient:
    settings = PlatformSettings(
        environment="development",
        database_url=":memory:",
        storage_root=tmp_path / "artifacts",
        allow_dev_auth=True,
    )
    app = create_platform_app(settings)
    client = PlatformClient(dev_user="dev", dev_role="automation_engineer", app=app)

    # Publish all reference components from examples/pen_engraving/components
    components_dir = REPOSITORY_ROOT / "examples" / "pen_engraving" / "components"
    for comp_file in components_dir.rglob("component.yaml"):
        manifest = yaml.safe_load(comp_file.read_text(encoding="utf-8"))
        client.publish_component(manifest)

    return client


def test_server_side_cell_resolution(platform_client: PlatformClient) -> None:
    pen_cell_path = REPOSITORY_ROOT / "examples" / "pen_engraving" / "cell.yaml"
    cell_yaml = pen_cell_path.read_text(encoding="utf-8")

    resp = platform_client.resolve_cell(cell_yaml, mode="simulation")
    assert resp.valid is True
    assert resp.mode == "simulation"
    assert isinstance(resp.resolved_components, list)
    assert len(resp.resolved_components) == 6
    comp_instances = {c["instance_id"]: c["component"] for c in resp.resolved_components}
    assert comp_instances["robot-001"] == "generic.six_axis_robot.reference"
    assert comp_instances["gripper-001"] == "generic.parallel_gripper.pen"
    assert comp_instances["laser-001"] == "generic.laser_marker.reference"
