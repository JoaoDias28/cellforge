"""Task 004 command contracts using isolated temporary project directories."""

import ast
import json
from pathlib import Path
from uuid import UUID

import pytest
from cellforge_cli import ExitCode
from cellforge_cli.main import main

REPOSITORY_ROOT = Path(__file__).parents[4]


def test_project_init_creates_valid_simulation_only_starter(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project = tmp_path / "starter"

    assert main(["project", "init", str(project), "--json"]) == ExitCode.SUCCESS
    initialized = json.loads(capsys.readouterr().out)
    UUID(initialized["result"]["cell_id"])
    assert (project / "cell.yaml").is_file()
    assert (project / "scene.usda").is_file()
    assert (project / "behavior_tree.xml").is_file()
    assert (project / "components" / "workspace" / "component.yaml").is_file()

    assert main(["validate", str(project), "--json"]) == ExitCode.SUCCESS
    validated = json.loads(capsys.readouterr().out)
    assert validated["ok"] is True
    assert validated["result"]["documents_checked"] == 3
    assert validated["errors"] == []


def test_copying_and_validating_pen_example_succeeds(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project = tmp_path / "pen-copy"

    assert main(["example", "copy", "pen-engraving", str(project)]) == ExitCode.SUCCESS
    assert "Copied pen-engraving example" in capsys.readouterr().out
    assert (project / "schemas" / "recipe.schema.json").is_file()
    assert "schema: schemas/recipe.schema.json" in (project / "cell.yaml").read_text(
        encoding="utf-8"
    )

    assert main(["validate", str(project)]) == ExitCode.SUCCESS
    captured = capsys.readouterr()
    assert "Valid project" in captured.out
    assert captured.err == ""


def test_invalid_project_returns_structured_errors(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project = tmp_path / "invalid-pen"
    assert main(["example", "copy", "pen-engraving", str(project)]) == ExitCode.SUCCESS
    capsys.readouterr()
    recipe = project / "recipe.yaml"
    recipe.write_text(
        recipe.read_text(encoding="utf-8").replace("status: TESTED", "status: UNREVIEWED"),
        encoding="utf-8",
    )

    assert main(["--json", "validate", str(project)]) == ExitCode.VALIDATION_FAILED
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["exit_code"] == 1
    errors_by_code = {error["code"]: error for error in payload["errors"]}
    finding = errors_by_code["schema.enum"]
    assert finding["severity"] == "error"
    assert finding["path"].endswith("recipe.yaml#/recipe/status")
    assert finding["message"]


def test_project_local_schemas_must_match_canonical_resources(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project = tmp_path / "tampered-schema"
    assert main(["example", "copy", "pen-engraving", str(project)]) == ExitCode.SUCCESS
    capsys.readouterr()
    schema = project / "schemas" / "recipe.schema.json"
    schema.write_text(
        schema.read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )

    assert main(["validate", str(project), "--json"]) == ExitCode.VALIDATION_FAILED
    payload = json.loads(capsys.readouterr().out)
    assert payload["errors"][0]["code"] == "cli.project-schema-mismatch"


def test_inspect_returns_typed_project_summary(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project = tmp_path / "inspectable"
    assert main(["project", "init", str(project)]) == ExitCode.SUCCESS
    capsys.readouterr()

    assert main(["inspect", str(project), "--json"]) == ExitCode.SUCCESS
    payload = json.loads(capsys.readouterr().out)
    result = payload["result"]
    assert payload["command"] == "inspect"
    assert result["name"] == "inspectable"
    assert result["component_count"] == 1
    assert result["deployment_profile_count"] == 1
    assert result["scene"] == "scene.usda"


def test_schema_list_is_deterministic_json(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["schema", "list", "--json"]) == ExitCode.SUCCESS

    payload = json.loads(capsys.readouterr().out)
    schemas = payload["result"]["schemas"]
    assert payload["command"] == "schema.list"
    assert len(schemas) == 5
    assert [(item["kind"], item["version"]) for item in schemas] == sorted(
        (item["kind"], item["version"]) for item in schemas
    )
    assert {item["filename"] for item in schemas} == {
        "cell.schema.json",
        "component.schema.json",
        "deployment-profile.schema.json",
        "recipe.schema.json",
        "scenario.schema.json",
    }


def test_commands_refuse_to_overwrite_existing_destination(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    destination = tmp_path / "occupied"
    destination.mkdir()
    marker = destination / "keep.txt"
    marker.write_text("user content", encoding="utf-8")

    assert (
        main(["example", "copy", "pen-engraving", str(destination), "--json"])
        == ExitCode.DESTINATION_EXISTS
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["errors"][0]["code"] == "cli.destination-exists"
    assert marker.read_text(encoding="utf-8") == "user content"

    assert main(["project", "init", str(destination)]) == ExitCode.DESTINATION_EXISTS
    assert "no files were overwritten" in capsys.readouterr().err
    assert marker.read_text(encoding="utf-8") == "user content"


def test_missing_project_and_usage_have_stable_exit_codes(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    missing = tmp_path / "missing"
    assert main(["validate", str(missing), "--json"]) == ExitCode.INPUT_NOT_FOUND
    payload = json.loads(capsys.readouterr().out)
    assert payload["errors"][0]["code"] == "cli.project-not-found"
    assert payload["exit_code"] == 3

    with pytest.raises(SystemExit) as caught:
        main(["validate"])
    assert caught.value.code == ExitCode.USAGE_ERROR


def test_cli_package_has_no_platform_or_production_framework_imports() -> None:
    package_root = REPOSITORY_ROOT / "src" / "python" / "cellforge_cli" / "src"
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
