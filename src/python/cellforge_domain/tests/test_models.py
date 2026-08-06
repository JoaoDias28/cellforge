"""Contract tests for CellForge domain documents."""

import ast
import json
from pathlib import Path
from typing import Any

import pytest
import yaml
from cellforge_domain import (
    BundleManifest,
    CellProject,
    ComponentType,
    DeploymentProfile,
    Port,
    Recipe,
    Scenario,
    SourceLoadError,
    load_document,
    to_canonical_json,
)
from pydantic import ValidationError

REPOSITORY_ROOT = Path(__file__).parents[4]
EXAMPLE_ROOT = REPOSITORY_ROOT / "examples" / "pen_engraving"


@pytest.mark.parametrize(
    ("relative_path", "model_type"),
    [
        ("components/robot/component.yaml", ComponentType),
        ("components/gripper/component.yaml", ComponentType),
        ("components/camera/component.yaml", ComponentType),
        ("components/fixture/component.yaml", ComponentType),
        ("components/laser/component.yaml", ComponentType),
        ("components/safety_status/component.yaml", ComponentType),
        ("cell.yaml", CellProject),
        ("recipe.yaml", Recipe),
        ("scenarios/nominal.yaml", Scenario),
        ("scenarios/laser_timeout.yaml", Scenario),
        ("deployment-sim.yaml", DeploymentProfile),
    ],
)
def test_reference_documents_load(relative_path: str, model_type: type[Any]) -> None:
    model = load_document(EXAMPLE_ROOT / relative_path, model_type)

    assert model.schema_version == "0.1.0"


def test_json_document_loads_with_same_model(tmp_path: Path) -> None:
    yaml_recipe = load_document(EXAMPLE_ROOT / "recipe.yaml", Recipe)
    json_path = tmp_path / "recipe.json"
    json_path.write_text(to_canonical_json(yaml_recipe), encoding="utf-8")

    json_recipe = load_document(json_path, Recipe)

    assert json_recipe == yaml_recipe


@pytest.mark.parametrize(
    "invalid_id",
    ["Uppercase", "has spaces", "slash/value", "-leading", "trailing-"],
)
def test_invalid_stable_identifiers_are_rejected(invalid_id: str) -> None:
    with pytest.raises(ValidationError, match="lowercase URL-safe stable identifier"):
        Port.model_validate({"id": invalid_id, "direction": "input", "type": "digital.boolean"})


@pytest.mark.parametrize("invalid_version", ["1", "1.2", "01.2.3", "1.02.3", "v1.2.3"])
def test_invalid_semantic_versions_are_rejected(invalid_version: str) -> None:
    data = yaml.safe_load(
        (EXAMPLE_ROOT / "components" / "robot" / "component.yaml").read_text(encoding="utf-8")
    )
    data["component"]["version"] = invalid_version

    with pytest.raises(ValidationError, match="Semantic Version 2.0.0"):
        ComponentType.model_validate(data)


def test_missing_required_field_is_rejected() -> None:
    data = yaml.safe_load((EXAMPLE_ROOT / "cell.yaml").read_text(encoding="utf-8"))
    del data["components"][0]["component"]

    with pytest.raises(ValidationError) as error:
        CellProject.model_validate(data)

    assert error.value.errors()[0]["loc"] == ("components", 0, "component")
    assert error.value.errors()[0]["type"] == "missing"


def test_duplicate_component_instance_ids_are_rejected() -> None:
    data = yaml.safe_load((EXAMPLE_ROOT / "cell.yaml").read_text(encoding="utf-8"))
    duplicate = dict(data["components"][0])
    duplicate["alias"] = "second_robot"
    data["components"].append(duplicate)

    with pytest.raises(ValidationError, match="component instance IDs must be unique"):
        CellProject.model_validate(data)


def test_validation_error_contains_source_paths(tmp_path: Path) -> None:
    source = tmp_path / "invalid.yaml"
    source.write_text("schema_version: 0.1.0\n", encoding="utf-8")

    with pytest.raises(SourceLoadError) as caught:
        load_document(source, CellProject)

    error = caught.value
    assert error.source_path == source.resolve()
    assert error.code == "source.validation-failed"
    assert error.findings
    assert error.findings[0].code == "model.missing"
    assert error.findings[0].path == f"{source.resolve()}#/cell"
    assert "schema_version" not in str(error)


def test_parser_failure_has_safe_public_message(tmp_path: Path) -> None:
    source = tmp_path / "broken.yaml"
    source.write_text("private_token: [unterminated", encoding="utf-8")

    with pytest.raises(SourceLoadError) as caught:
        load_document(source, CellProject)

    error = caught.value
    assert error.code == "source.parse-failed"
    assert error.diagnostic_cause_type is not None
    assert "private_token" not in str(error)
    assert "Traceback" not in str(error)


def test_missing_file_has_safe_source_context(tmp_path: Path) -> None:
    source = tmp_path / "missing.yaml"

    with pytest.raises(SourceLoadError) as caught:
        load_document(source, CellProject)

    error = caught.value
    assert error.source_path == source.resolve()
    assert error.code == "source.read-failed"
    assert error.diagnostic_cause_type == "FileNotFoundError"
    assert "Could not read source document" in str(error)
    assert "No such file" not in str(error)


def test_unsupported_format_and_non_object_root_are_rejected(tmp_path: Path) -> None:
    unsupported = tmp_path / "cell.toml"
    unsupported.write_text("name = 'cell'", encoding="utf-8")
    with pytest.raises(SourceLoadError, match="Unsupported document format") as unsupported_error:
        load_document(unsupported, CellProject)
    assert unsupported_error.value.code == "source.unsupported-format"

    sequence = tmp_path / "cell.json"
    sequence.write_text("[]", encoding="utf-8")
    with pytest.raises(SourceLoadError) as sequence_error:
        load_document(sequence, CellProject)
    assert sequence_error.value.code == "source.root-not-object"


def test_canonical_serialization_sorts_nested_mappings_and_uses_aliases() -> None:
    first = load_document(EXAMPLE_ROOT / "cell.yaml", CellProject)
    first.components[0].config = {"z": 1, "a": {"z": False, "a": True}}
    second = load_document(EXAMPLE_ROOT / "cell.yaml", CellProject)
    second.components[0].config = {"a": {"a": True, "z": False}, "z": 1}

    first_json = to_canonical_json(first)
    second_json = to_canonical_json(second)

    assert first_json == second_json
    assert '"from":' in first_json
    assert '"from_":' not in first_json


def test_bundle_manifest_validates_content_addresses() -> None:
    manifest = BundleManifest.model_validate(
        {
            "schema_version": "0.1.0",
            "bundle_id": "a" * 64,
            "source_revision": "b" * 40,
            "cell_id": "0d3c6b63-a57f-4207-8638-e4cf76efec90",
            "target_profile": "pen-sim-amd64",
            "components": [
                {
                    "instance_id": "robot-001",
                    "component": "generic.six_axis_robot.reference",
                    "version": "0.1.0",
                }
            ],
            "recipes": [{"id": "pen-aluminium-reference", "version": 1}],
            "files": [{"path": "config/cell.yaml", "sha256": "c" * 64, "size": 42}],
        }
    )

    encoded = json.loads(to_canonical_json(manifest))
    assert encoded["bundle_id"] == "a" * 64
    assert encoded["cell_id"] == "0d3c6b63-a57f-4207-8638-e4cf76efec90"

    with pytest.raises(ValidationError, match="SHA-256"):
        BundleManifest.model_validate({**manifest.model_dump(), "bundle_id": "not-a-digest"})


def test_domain_package_has_no_forbidden_imports() -> None:
    package_root = REPOSITORY_ROOT / "src" / "python" / "cellforge_domain" / "src"
    forbidden = {"rclpy", "rospy", "isaacsim", "omni", "fastapi"}
    imported_roots: set[str] = set()
    for source in package_root.rglob("*.py"):
        module = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        for node in ast.walk(module):
            if isinstance(node, ast.Import):
                imported_roots.update(alias.name.partition(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_roots.add(node.module.partition(".")[0])

    assert imported_roots.isdisjoint(forbidden)
