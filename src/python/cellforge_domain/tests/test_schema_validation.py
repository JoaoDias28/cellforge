"""Contract tests for Draft 2020-12 and example-tree validation."""

import shutil
from pathlib import Path

import pytest
import yaml
from cellforge_domain import (
    Recipe,
    SchemaDocumentKind,
    SchemaKey,
    SchemaRegistry,
    SourceLoadError,
    load_document,
)
from cellforge_domain.example_validation import format_finding, main, validate_example_tree

REPOSITORY_ROOT = Path(__file__).parents[4]
SCHEMA_ROOT = REPOSITORY_ROOT / "schemas"
EXAMPLE_ROOT = REPOSITORY_ROOT / "examples" / "pen_engraving"
FIXTURE_ROOT = REPOSITORY_ROOT / "tests" / "fixtures" / "validation"


def test_registry_loads_every_canonical_schema_by_kind_and_version() -> None:
    registry = SchemaRegistry.from_directory(SCHEMA_ROOT)

    assert len(registry) == len(tuple(SCHEMA_ROOT.glob("*.json"))) == 5
    assert SchemaKey(SchemaDocumentKind.RECIPE, "0.1.0") in registry.keys
    assert (
        registry.get(SchemaDocumentKind.CELL, "0.1.0").path
        == (SCHEMA_ROOT / "cell.schema.json").resolve()
    )


def test_all_reference_yaml_and_cross_file_references_validate() -> None:
    report = validate_example_tree(EXAMPLE_ROOT, SchemaRegistry.from_directory(SCHEMA_ROOT))

    assert report.documents_checked == len(tuple(EXAMPLE_ROOT.rglob("*.yaml")))
    assert report.auxiliary_schemas_checked == 7
    assert report.findings == ()


def test_intentional_fixture_reports_file_path_rule_and_message() -> None:
    source = FIXTURE_ROOT / "invalid-recipe.yaml"
    registry = SchemaRegistry.from_directory(SCHEMA_ROOT)

    with pytest.raises(SourceLoadError) as caught:
        load_document(
            source,
            Recipe,
            schema_registry=registry,
        )

    finding = caught.value.findings[0]
    rendered = format_finding(finding)
    assert finding.code == "schema.enum"
    assert finding.path == f"{source.resolve()}#/recipe/status"
    assert "'UNREVIEWED' is not one of" in finding.message
    assert str(source.resolve()) in rendered
    assert "rule=schema.enum" in rendered
    assert "message=" in rendered


def test_unknown_schema_version_is_a_source_aware_failure(tmp_path: Path) -> None:
    source = tmp_path / "recipe.yaml"
    source.write_text(
        (EXAMPLE_ROOT / "recipe.yaml")
        .read_text(encoding="utf-8")
        .replace("schema_version: 0.1.0", "schema_version: 9.9.9"),
        encoding="utf-8",
    )

    with pytest.raises(SourceLoadError) as caught:
        load_document(
            source,
            Recipe,
            schema_registry=SchemaRegistry.from_directory(SCHEMA_ROOT),
            schema_kind=SchemaDocumentKind.RECIPE,
        )

    assert caught.value.findings[0].code == "schema.version-not-registered"
    assert caught.value.findings[0].path == f"{source.resolve()}#/schema_version"


def test_missing_recipe_and_deployment_references_fail(tmp_path: Path) -> None:
    project = tmp_path / "pen_engraving"
    shutil.copytree(EXAMPLE_ROOT, project)
    cell_path = project / "cell.yaml"
    cell = yaml.safe_load(cell_path.read_text(encoding="utf-8"))
    cell["recipes"][0]["path"] = "missing-recipe.yaml"
    cell["deployment_profiles"][0] = "missing-deployment.yaml"
    cell_path.write_text(yaml.safe_dump(cell, sort_keys=False), encoding="utf-8")

    report = validate_example_tree(project, SchemaRegistry.from_directory(SCHEMA_ROOT))
    codes = {finding.code for finding in report.findings}

    assert "reference.recipe-not-found" in codes
    assert "reference.deployment-profile-not-found" in codes


def test_validation_command_succeeds_for_reference_examples(
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = main(["--schemas", str(SCHEMA_ROOT), "--examples", str(EXAMPLE_ROOT)])

    captured = capsys.readouterr()
    assert result == 0
    assert "Validated 5 canonical schemas" in captured.out
    assert captured.err == ""
