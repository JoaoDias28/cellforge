"""Tests for RecipeAuthoringService: schema forms, lifecycle, versioning, and diffing."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from cellforge.studio.application import ProjectContents
from cellforge.studio.recipe_service import (
    DEFAULT_RECIPE_FIELD_METADATA,
    RecipeAuthoringService,
    RecipeStatusEnum,
)

ROOT = Path(__file__).resolve().parents[4]
SCHEMAS = ROOT / "schemas"
EXAMPLES_PEN = ROOT / "examples" / "pen_engraving"


@pytest.fixture
def service() -> RecipeAuthoringService:
    return RecipeAuthoringService(SCHEMAS)


@pytest.fixture
def pen_contents() -> ProjectContents:
    cell_yaml = (EXAMPLES_PEN / "cell.yaml").read_text(encoding="utf-8")
    scene_usda = (EXAMPLES_PEN / "scene.usda").read_text(encoding="utf-8")
    recipe_yaml = (EXAMPLES_PEN / "recipe.yaml").read_bytes()
    return ProjectContents(
        cell_yaml=cell_yaml,
        scene_usda=scene_usda,
        artifacts={"recipe.yaml": recipe_yaml},
    )


def test_discover_and_inspect_pen_recipe(
    service: RecipeAuthoringService, pen_contents: ProjectContents
) -> None:
    browser = service.browse(EXAMPLES_PEN, pen_contents)
    assert len(browser.recipes) > 0
    recipe_sum = browser.recipes[0]
    assert recipe_sum.id == "pen-aluminium-reference"
    assert recipe_sum.version == 1
    assert recipe_sum.status == RecipeStatusEnum.TESTED

    detail = service.inspect_recipe(
        EXAMPLES_PEN, pen_contents, recipe_id="pen-aluminium-reference", version=1
    )
    assert detail is not None
    assert detail.summary.id == "pen-aluminium-reference"
    assert "parameters" in detail.data
    assert len(detail.field_metadata) > 0


def test_field_metadata_units_and_ranges() -> None:
    meta_map = {m.path: m for m in DEFAULT_RECIPE_FIELD_METADATA}

    assert "parameters.robot_speed_scale" in meta_map
    speed_meta = meta_map["parameters.robot_speed_scale"]
    assert speed_meta.unit == "scale"
    assert speed_meta.minimum == 0.01

    assert "limits.max_pose_correction_mm" in meta_map
    tol_meta = meta_map["limits.max_pose_correction_mm"]
    assert tol_meta.unit == "mm"
    assert tol_meta.minimum == 0.0

    assert "timeouts.process" in meta_map
    time_meta = meta_map["timeouts.process"]
    assert time_meta.unit == "s"
    assert time_meta.minimum == 0.1


def test_lifecycle_transitions_and_evidence_requirement(
    service: RecipeAuthoringService, pen_contents: ProjectContents
) -> None:
    # 1. Reset recipe to DRAFT without evidence
    detail = service.inspect_recipe(
        EXAMPLES_PEN, pen_contents, recipe_id="pen-aluminium-reference", version=1
    )
    assert detail is not None
    draft_data = copy.deepcopy(dict(detail.data))
    draft_data["recipe"]["status"] = "DRAFT"
    draft_data.pop("approval", None)

    draft_result = service.edit_recipe(
        EXAMPLES_PEN, pen_contents, recipe_id="pen-aluminium-reference", version=1, data=draft_data
    )
    assert draft_result.contents is not None

    # 2. Transition DRAFT -> VALIDATED
    t_val = service.transition_lifecycle(
        EXAMPLES_PEN,
        draft_result.contents,
        recipe_id="pen-aluminium-reference",
        version=1,
        target_status=RecipeStatusEnum.VALIDATED,
    )
    assert t_val.contents is not None

    # 3. Transition VALIDATED -> TESTED without evidence must fail
    t_test_fail = service.transition_lifecycle(
        EXAMPLES_PEN,
        t_val.contents,
        recipe_id="pen-aluminium-reference",
        version=1,
        target_status=RecipeStatusEnum.TESTED,
        evidence=None,
    )
    assert t_test_fail.contents is None
    assert any("evidence" in f.message.lower() for f in t_test_fail.validation)

    # 4. Transition VALIDATED -> TESTED with evidence succeeds
    t_test_ok = service.transition_lifecycle(
        EXAMPLES_PEN,
        t_val.contents,
        recipe_id="pen-aluminium-reference",
        version=1,
        target_status=RecipeStatusEnum.TESTED,
        evidence=["simulation:run_001_pass"],
    )
    assert t_test_ok.contents is not None

    # 5. Transition TESTED -> APPROVED succeeds
    t_app_ok = service.transition_lifecycle(
        EXAMPLES_PEN,
        t_test_ok.contents,
        recipe_id="pen-aluminium-reference",
        version=1,
        target_status=RecipeStatusEnum.APPROVED,
    )
    assert t_app_ok.contents is not None
    detail_app = service.inspect_recipe(
        EXAMPLES_PEN, t_app_ok.contents, recipe_id="pen-aluminium-reference", version=1
    )
    assert detail_app is not None
    assert detail_app.summary.status == RecipeStatusEnum.APPROVED
    assert detail_app.summary.is_immutable is True

    # 6. Transition APPROVED -> RETIRED succeeds
    t_ret = service.transition_lifecycle(
        EXAMPLES_PEN,
        t_app_ok.contents,
        recipe_id="pen-aluminium-reference",
        version=1,
        target_status=RecipeStatusEnum.RETIRED,
    )
    assert t_ret.contents is not None
    detail_ret = service.inspect_recipe(
        EXAMPLES_PEN, t_ret.contents, recipe_id="pen-aluminium-reference", version=1
    )
    assert detail_ret is not None
    assert detail_ret.summary.status == RecipeStatusEnum.RETIRED


def test_invalid_lifecycle_skips_are_rejected(
    service: RecipeAuthoringService, pen_contents: ProjectContents
) -> None:
    # Set recipe to DRAFT
    detail = service.inspect_recipe(
        EXAMPLES_PEN, pen_contents, recipe_id="pen-aluminium-reference", version=1
    )
    assert detail is not None
    draft_data = copy.deepcopy(dict(detail.data))
    draft_data["recipe"]["status"] = "DRAFT"
    draft_res = service.edit_recipe(
        EXAMPLES_PEN, pen_contents, recipe_id="pen-aluminium-reference", version=1, data=draft_data
    )
    assert draft_res.contents is not None

    # DRAFT -> APPROVED directly without validation/testing is forbidden
    bad_transition = service.transition_lifecycle(
        EXAMPLES_PEN,
        draft_res.contents,
        recipe_id="pen-aluminium-reference",
        version=1,
        target_status=RecipeStatusEnum.APPROVED,
        evidence=["some_evidence"],
    )
    assert bad_transition.contents is None
    assert any("cannot transition" in f.message.lower() for f in bad_transition.validation)


def test_approved_recipe_is_immutable(
    service: RecipeAuthoringService, pen_contents: ProjectContents
) -> None:
    # Approve version 1
    t_app = service.transition_lifecycle(
        EXAMPLES_PEN,
        pen_contents,
        recipe_id="pen-aluminium-reference",
        version=1,
        target_status=RecipeStatusEnum.APPROVED,
    )
    approved_contents = t_app.contents
    assert approved_contents is not None

    # Attempt to edit approved recipe in-place -> must be rejected!
    detail = service.inspect_recipe(
        EXAMPLES_PEN, approved_contents, recipe_id="pen-aluminium-reference", version=1
    )
    assert detail is not None
    mutated_data = copy.deepcopy(dict(detail.data))
    mutated_data["parameters"]["robot_speed_scale"] = 0.5

    edit_result = service.edit_recipe(
        EXAMPLES_PEN,
        approved_contents,
        recipe_id="pen-aluminium-reference",
        version=1,
        data=mutated_data,
    )
    assert edit_result.contents is None
    assert any("immutable" in f.message.lower() for f in edit_result.validation)


def test_create_recipe_version_preserves_predecessor(
    service: RecipeAuthoringService, pen_contents: ProjectContents
) -> None:
    # Create version 2 from version 1
    new_ver_result = service.create_recipe_version(
        EXAMPLES_PEN,
        pen_contents,
        recipe_id="pen-aluminium-reference",
        base_version=1,
        overrides={"parameters": {"robot_speed_scale": 0.5}},
    )
    assert new_ver_result.contents is not None
    assert len(new_ver_result.validation) == 0

    browser = service.browse(EXAMPLES_PEN, new_ver_result.contents)
    versions = [r.version for r in browser.recipes if r.id == "pen-aluminium-reference"]
    assert 1 in versions
    assert 2 in versions

    # Verify v1 is untouched
    v1_detail = service.inspect_recipe(
        EXAMPLES_PEN, new_ver_result.contents, recipe_id="pen-aluminium-reference", version=1
    )
    assert v1_detail is not None
    assert v1_detail.data["parameters"]["robot_speed_scale"] == 0.25

    # Verify v2 is created as DRAFT with overridden parameter
    v2_detail = service.inspect_recipe(
        EXAMPLES_PEN, new_ver_result.contents, recipe_id="pen-aluminium-reference", version=2
    )
    assert v2_detail is not None
    assert v2_detail.summary.status == RecipeStatusEnum.DRAFT
    assert v2_detail.data["parameters"]["robot_speed_scale"] == 0.5


def test_recipe_diffing(service: RecipeAuthoringService, pen_contents: ProjectContents) -> None:
    v1_detail = service.inspect_recipe(
        EXAMPLES_PEN, pen_contents, recipe_id="pen-aluminium-reference", version=1
    )
    assert v1_detail is not None

    v2_data = copy.deepcopy(dict(v1_detail.data))
    v2_data["recipe"]["version"] = 2
    v2_data["parameters"]["robot_speed_scale"] = 0.5
    v2_data["limits"]["max_pose_correction_mm"] = 1.0  # Tighter tolerance -> breaking

    diff_result = service.diff(v1_detail.data, v2_data)
    assert diff_result.is_breaking is True
    assert len(diff_result.differences) > 0
    param_diff = next(d for d in diff_result.differences if d.key == "robot_speed_scale")
    assert param_diff.old_value == 0.25
    assert param_diff.new_value == 0.5
