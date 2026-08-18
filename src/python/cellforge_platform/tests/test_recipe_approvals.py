"""Tests for append-only recipe approval lifecycle and two-role production authorization."""

from __future__ import annotations

from pathlib import Path

import pytest
from cellforge_platform.api.router import create_platform_app
from cellforge_platform.client import PlatformClient, PlatformClientError
from cellforge_platform.config import PlatformSettings


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


def test_recipe_lifecycle_and_two_role_production_approval(platform_client: PlatformClient) -> None:
    # 1. Register a project
    platform_client.register_project(
        cell_id="cell-001",
        name="Test Cell",
        cell_yaml_sha256="a" * 64,
        scene_sha256="b" * 64,
    )

    # 2. Publish recipe as process engineer "alice"
    alice_client = PlatformClient(
        app=platform_client.app,
        dev_user="alice",
        dev_role="process_engineer",
    )

    recipe = alice_client.publish_recipe(
        cell_id="cell-001",
        recipe_id="engrave_pen",
        version=1,
        name="Pen Engraving Recipe",
        schema_sha256="c" * 64,
        recipe_data={"feed_rate": 100, "power": 80},
    )
    assert recipe.status == "draft"

    # 3. Check initial approvals summary
    summary = platform_client.get_recipe_approvals(
        cell_id="cell-001",
        recipe_id="engrave_pen",
        version=1,
    )
    assert summary.status == "draft"
    assert summary.is_approved_for_production is False
    assert len(summary.approvals) == 0

    # 4. Self-approval by author "alice" cannot satisfy dual-role requirement
    alice_summary = alice_client.approve_recipe(
        cell_id="cell-001",
        recipe_id="engrave_pen",
        version=1,
        role="process_engineer",
        decision="approved",
        comments="Author approval",
    )
    assert len(alice_summary.approvals) == 1
    # is_approved_for_production must remain False because self-approval is rejected
    assert alice_summary.is_approved_for_production is False

    # 5. First independent approval by "bob" (automation_engineer)
    bob_client = PlatformClient(
        app=platform_client.app,
        dev_user="bob",
        dev_role="automation_engineer",
    )
    bob_summary = bob_client.approve_recipe(
        cell_id="cell-001",
        recipe_id="engrave_pen",
        version=1,
        role="automation_engineer",
        decision="approved",
        comments="Automation safety checked",
    )
    assert len(bob_summary.approvals) == 2
    # Only 1 independent approval so far (bob) -> still not approved for production
    assert bob_summary.is_approved_for_production is False

    # 6. Second independent approval by "carol" (process_engineer)
    carol_client = PlatformClient(
        app=platform_client.app,
        dev_user="carol",
        dev_role="process_engineer",
    )
    carol_summary = carol_client.approve_recipe(
        cell_id="cell-001",
        recipe_id="engrave_pen",
        version=1,
        role="process_engineer",
        decision="approved",
        comments="Peer process review passed",
    )
    # Now we have 2 distinct non-author users (bob, carol) with
    # 2 distinct roles (automation_engineer, process_engineer)
    assert carol_summary.is_approved_for_production is True

    assert carol_summary.status == "APPROVED"

    # 7. Check that the recipe record status in platform is now APPROVED
    rec_record = platform_client.get_recipe("cell-001", "engrave_pen", 1)
    assert rec_record.status == "APPROVED"


def test_unauthorized_role_approval_rejected(platform_client: PlatformClient) -> None:
    platform_client.register_project(
        cell_id="cell-002",
        name="Test Cell 2",
        cell_yaml_sha256="a" * 64,
        scene_sha256="b" * 64,
    )
    platform_client.publish_recipe(
        cell_id="cell-002",
        recipe_id="rec2",
        version=1,
        name="Rec 2",
        schema_sha256="c" * 64,
        recipe_data={"speed": 50},
    )

    # Operator cannot approve recipes
    operator_client = PlatformClient(
        app=platform_client.app,
        dev_user="dave",
        dev_role="operator",
    )

    with pytest.raises(PlatformClientError) as exc_info:
        operator_client.approve_recipe(
            cell_id="cell-002",
            recipe_id="rec2",
            version=1,
            role="process_engineer",
        )
    assert exc_info.value.status_code == 403
