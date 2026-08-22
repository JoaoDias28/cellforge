"""Contract tests for Task 041 schema-driven authoring."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

import yaml

from cellforge.studio.application import StudioApplication, StudioStatus
from cellforge.studio.project_service import RECOVERY_FILE, ProjectCommandService
from cellforge.studio.schema_authoring import SchemaAuthoringService
from cellforge.studio.schema_form_renderer import SchemaFormRenderer

ROOT = Path(__file__).resolve().parents[4]
SCHEMAS = ROOT / "schemas"
EXAMPLES = ROOT / "examples"


def _yaml_data(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _service() -> SchemaAuthoringService:
    return SchemaAuthoringService(SCHEMAS)


def _project_copy(tmp_path: Path) -> Path:
    project = tmp_path / "pen-project"
    shutil.copytree(EXAMPLES / "pen_engraving", project)
    shutil.copytree(SCHEMAS, project / "schemas")
    cell_path = project / "cell.yaml"
    cell_path.write_text(
        cell_path.read_text(encoding="utf-8").replace(
            "../../schemas/recipe.schema.json", "schemas/recipe.schema.json"
        ),
        encoding="utf-8",
        newline="\n",
    )
    return project


def test_supported_cell_form_uses_schema_fields_refs_and_stable_values() -> None:
    source = EXAMPLES / "pen_engraving" / "cell.yaml"
    schema = SCHEMAS / "cell.schema.json"
    service = _service()

    first = service.BuildSchemaForm(schema, source=source, schema_kind="cell")
    second = service.BuildSchemaForm(schema, source=source, schema_kind="cell")

    assert {field.path for field in first.fields} >= {
        "/schema_version",
        "/cell/id",
        "/cell/name",
        "/scene/usd",
        "/components",
        "/components/0/id",
        "/connections",
    }
    assert first.values == second.values
    assert first.generated_paths == second.generated_paths
    assert first.groups
    assert first.findings == ()


def test_cell_form_and_source_candidates_round_trip_to_same_canonical_value() -> None:
    source = EXAMPLES / "pen_engraving" / "cell.yaml"
    service = _service()
    form = service.BuildSchemaForm(SCHEMAS / "cell.schema.json", source=source, schema_kind="cell")

    form_candidate = service.PreviewFormEdit(form, {"/cell/name": "Round-trip cell"})
    source_candidate = service.PreviewSourceEdit(form, form_candidate.source_text)

    assert form_candidate.can_save
    assert source_candidate.can_save
    assert source_candidate.canonical_value == form_candidate.canonical_value
    assert source_candidate.canonical_text == form_candidate.canonical_text
    assert source_candidate.diff == form_candidate.diff


def test_component_configuration_form_exposes_required_optional_and_ranges() -> None:
    schema = EXAMPLES / "kitting" / "components" / "gripper" / "config.schema.json"
    service = _service()

    form = service.BuildSchemaForm(schema, {"jaw_opening_mm": 25}, schema_kind="component-config")

    field = next(item for item in form.fields if item.path == "/jaw_opening_mm")
    assert field.required
    assert field.field_type == "number"
    assert field.minimum is None
    assert field.maximum == 100
    assert field.widget == "number"
    assert form.can_save


def test_recipe_form_preserves_enums_advanced_metadata_and_byte_stable_noop() -> None:
    source = EXAMPLES / "pen_engraving" / "recipe.yaml"
    service = _service()
    form = service.BuildSchemaForm(
        SCHEMAS / "recipe.schema.json",
        source=source,
        schema_kind="recipe",
    )

    status = next(item for item in form.fields if item.path == "/recipe/status")
    assert status.enum == ("DRAFT", "VALIDATED", "TESTED", "APPROVED", "RETIRED")
    assert any(item.unit == "s" for item in form.fields)
    assert any(item.advanced for item in form.fields)

    candidate = service.PreviewFormEdit(form, {})
    assert candidate.source_text == source.read_text(encoding="utf-8")
    assert candidate.original_bytes == source.read_bytes()
    assert hashlib.sha256(candidate.original_bytes).hexdigest() == candidate.base_source_hash


def test_scenario_form_keeps_seed_fault_and_fidelity_fields() -> None:
    source = EXAMPLES / "kitting" / "scenarios" / "gripper_close_recovery.yaml"
    service = _service()
    form = service.BuildSchemaForm(
        SCHEMAS / "scenario.schema.json",
        source=source,
        schema_kind="scenario",
    )

    assert {item.path for item in form.fields} >= {
        "/scenario/seed",
        "/simulation/requested_fidelity",
        "/faults",
    }
    assert form.values["scenario"]["seed"] == 3802
    assert form.values["simulation"]["requested_fidelity"] == "L0"


def test_required_ambiguity_is_explicit_and_singletons_are_generated() -> None:
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "required": ["choice", "fixed", "id"],
        "properties": {
            "choice": {"type": "string", "enum": ["left", "right"]},
            "fixed": {"enum": ["only"]},
            "id": {"type": "string", "x-cellforge": {"generated": True}},
        },
    }
    form = SchemaAuthoringService().BuildSchemaForm(
        schema,
        {},
        schema_kind="cell",
        allocator_seed="fixed-seed",
    )

    assert tuple(choice.key for choice in form.choices) == ("/choice",)
    assert form.values["fixed"] == "only"
    assert "/id" in form.generated_paths
    assert form.fields[-1].generated
    assert not form.can_save

    explicit = SchemaAuthoringService().BuildSchemaForm(
        schema,
        {},
        schema_kind="cell",
        allocator_seed="fixed-seed",
        required_choices={"/choice": ("left",)},
    )
    assert explicit.values["choice"] == "left"
    assert not explicit.choices


def test_unknown_annotations_are_ignored_but_unknown_validation_keywords_block() -> None:
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "required": ["value"],
        "x-cellforge": {"unknown_presentation": "ignored"},
        "properties": {
            "value": {
                "type": "string",
                "x-cellforge": {"label": "Value", "unknown": True},
                "x-unknown-extension": {"allowed": True},
                "notAValidationKeyword": True,
            }
        },
    }
    form = SchemaAuthoringService().BuildSchemaForm(schema, {"value": "ok"})

    assert next(item for item in form.fields if item.path == "/value").label == "Value"
    assert any(item.code == "schema.unknown-keyword" for item in form.findings)
    assert not form.can_save


def test_source_preview_is_read_only_and_reports_exact_structured_diff(tmp_path: Path) -> None:
    source = tmp_path / "document.yaml"
    source.write_text("name: before\ncount: 2\n", encoding="utf-8")
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "required": ["name", "count"],
        "properties": {
            "name": {"type": "string"},
            "count": {"type": "integer", "minimum": 1, "maximum": 10},
        },
    }
    service = SchemaAuthoringService()
    form = service.BuildSchemaForm(schema, source=source)
    before = source.read_bytes()
    candidate = service.PreviewSourceEdit(form, "name: after\ncount: 3\n")

    assert source.read_bytes() == before
    assert candidate.can_save
    assert [(item.path, item.operation) for item in candidate.diff] == [
        ("/count", "replace"),
        ("/name", "replace"),
    ]
    assert candidate.source_path == str(source.resolve())


def test_invalid_types_ranges_enums_yaml_and_schema_versions_are_structured() -> None:
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "required": ["mode", "count", "schema_version"],
        "properties": {
            "schema_version": {"const": "0.1.0"},
            "mode": {"enum": ["safe", "fast"]},
            "count": {"type": "integer", "minimum": 1, "maximum": 3},
        },
    }
    service = SchemaAuthoringService()
    invalid = service.PreviewSourceEdit(
        schema,
        "schema_version: 9.9.9\nmode: unknown\ncount: too-many\n",
        schema_kind="test",
    )
    malformed = service.PreviewSourceEdit(schema, "schema_version: [", schema_kind="test")
    unsupported_schema = dict(schema)
    unsupported_schema["$schema"] = "https://json-schema.org/draft/2019-09/schema"
    unsupported = service.BuildSchemaForm(unsupported_schema, {"schema_version": "0.1.0"})

    codes = {item.code for item in invalid.findings}
    assert {"schema.const", "schema.enum", "schema.type"} <= codes
    assert any(item.code == "source.parse-failed" for item in malformed.findings)
    assert any(item.code == "schema.version-unsupported" for item in unsupported.findings)
    assert not invalid.can_save
    assert not malformed.can_save
    assert not unsupported.can_save


def test_unresolved_schema_reference_is_structured_and_blocks_save() -> None:
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {"value": {"$ref": "#/$defs/missing"}},
    }

    form = SchemaAuthoringService().BuildSchemaForm(schema, {"value": "ok"})

    assert any(item.code == "schema.reference-invalid" for item in form.findings)
    assert not form.can_save


def test_merge_source_edit_surfaces_conflict_instead_of_guessing(tmp_path: Path) -> None:
    source = tmp_path / "document.yaml"
    source.write_text("name: before\n", encoding="utf-8")
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "required": ["name"],
        "properties": {"name": {"type": "string"}},
    }
    service = SchemaAuthoringService()
    form = service.BuildSchemaForm(schema, source=source)
    form_edit = service.UpdateSchemaForm(form, {"/name": "from-form"})
    source_edit = service.PreviewSourceEdit(form, "name: from-source\n")
    merged = service.MergeSourceEdit(form_edit, source_edit)

    assert any(item.code == "authoring.merge-conflict" for item in merged.findings)
    assert not merged.can_save


def test_save_requires_confirmation_and_updates_direct_source_only_after_preview(
    tmp_path: Path,
) -> None:
    source = tmp_path / "document.json"
    source.write_text('{"name": "before"}\n', encoding="utf-8")
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "required": ["name"],
        "properties": {"name": {"type": "string"}},
    }
    service = SchemaAuthoringService()
    form = service.BuildSchemaForm(schema, source=source)
    candidate = service.PreviewFormEdit(form, {"/name": "after"})
    before = source.read_bytes()

    blocked = service.SaveAuthoringCandidate(
        candidate, candidate.confirmation_token, confirmed=False
    )
    assert not blocked.success
    assert source.read_bytes() == before

    saved = service.SaveAuthoringCandidate(candidate, candidate.confirmation_token, confirmed=True)
    assert saved.success
    assert json.loads(source.read_text(encoding="utf-8")) == {"name": "after"}


def test_project_save_uses_paired_transaction_and_restores_all_sources_on_failure(
    tmp_path: Path,
) -> None:
    project = _project_copy(tmp_path)
    before = {
        relative: (project / relative).read_bytes()
        for relative in ("cell.yaml", "scene.usda", "recipe.yaml")
    }
    calls = 0

    def fail_second_replace(source: str | Path, target: str | Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected replacement failure")
        Path(source).replace(target)

    service = ProjectCommandService(SCHEMAS, replace_file=fail_second_replace)
    opened = service.inspect(project)
    assert opened.project is not None
    assert opened.contents is not None
    form = service.build_schema_form(
        project,
        opened.contents,
        schema=SCHEMAS / "recipe.schema.json",
        source_path=project / "recipe.yaml",
        schema_kind="recipe",
    )
    candidate = SchemaAuthoringService(SCHEMAS).PreviewFormEdit(
        form, {"/recipe/name": "Interrupted"}
    )
    saved = service.save_authoring_candidate(
        candidate,
        candidate.confirmation_token,
        confirmed=True,
        project_path=project,
        project_contents=opened.contents,
    )

    assert calls > 1
    assert not saved.success
    assert any(item.code == "authoring.save-failed" for item in saved.findings)
    assert {relative: (project / relative).read_bytes() for relative in before} == before
    assert not (project / RECOVERY_FILE).exists()
    assert ProjectCommandService(SCHEMAS).inspect(project).project is not None


def test_application_reports_authoring_backend_failure_without_widget_exception(
    tmp_path: Path,
) -> None:
    project = _project_copy(tmp_path)

    class BrokenProjectService(ProjectCommandService):
        def build_schema_form(self, *args: Any, **kwargs: Any) -> Any:
            del args, kwargs
            raise RuntimeError("authoring backend unavailable")

    application = StudioApplication(BrokenProjectService(SCHEMAS))
    assert application.open_project(project).status is StudioStatus.PROJECT_READY
    snapshot = application.build_schema_form(
        SCHEMAS / "cell.schema.json",
        source_path=project / "cell.yaml",
        schema_kind="cell",
    )

    assert snapshot.status is StudioStatus.OPERATION_FAILED
    assert snapshot.project is not None
    assert snapshot.logs[-1].level.value == "error"


def test_released_recipe_candidate_is_immutable() -> None:
    source = EXAMPLES / "pen_engraving" / "recipe.yaml"
    data = _yaml_data(source)
    data["recipe"]["status"] = "APPROVED"
    service = _service()
    form = service.BuildSchemaForm(SCHEMAS / "recipe.schema.json", data, schema_kind="recipe")
    candidate = service.PreviewFormEdit(form, {"/product/sku": "changed"})

    assert candidate.released_recipe
    assert any(item.code == "authoring.recipe.released-immutable" for item in candidate.findings)
    assert not candidate.can_save


def test_scenario_source_edit_cannot_drop_explicit_seed_fault_or_fidelity() -> None:
    source = EXAMPLES / "kitting" / "scenarios" / "gripper_close_recovery.yaml"
    service = _service()
    form = service.BuildSchemaForm(
        SCHEMAS / "scenario.schema.json", source=source, schema_kind="scenario"
    )
    data = _yaml_data(source)
    data.pop("faults")
    candidate = service.PreviewSourceEdit(form, yaml.safe_dump(data, sort_keys=False))

    assert any(item.code == "authoring.scenario.fidelity-state-lost" for item in candidate.findings)
    assert not candidate.can_save


def test_renderer_only_maps_service_dtos_and_preserves_advanced_state() -> None:
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {
            "value": {
                "type": "number",
                "x-cellforge": {
                    "label": "Measured value",
                    "group": "Limits",
                    "unit": "mm",
                    "advanced": True,
                },
            }
        },
    }
    form = SchemaAuthoringService().BuildSchemaForm(schema, {"value": 2})
    rendered = SchemaFormRenderer().render(form)

    field = rendered.fields[0]
    assert field.label == "Measured value"
    assert field.group == "Limits"
    assert field.unit == "mm"
    assert field.advanced
    assert rendered.can_save


def test_backend_failure_is_a_structured_finding_not_a_widget_exception(tmp_path: Path) -> None:
    class BrokenBackend:
        def inspect(self, _root: Path) -> None:
            raise RuntimeError("backend unavailable")

    source = tmp_path / "document.yaml"
    source.write_text("name: before\n", encoding="utf-8")
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "required": ["name"],
        "properties": {"name": {"type": "string"}},
    }
    service = SchemaAuthoringService(project_service=BrokenBackend())
    form = service.BuildSchemaForm(schema, source=source, project_path=tmp_path)
    candidate = service.PreviewFormEdit(form, {"/name": "after"})

    assert any(item.code == "authoring.backend-unavailable" for item in candidate.findings)
    assert not candidate.can_save


def test_stale_preview_is_rejected_without_overwriting_new_source(tmp_path: Path) -> None:
    source = tmp_path / "document.yaml"
    source.write_text("name: before\n", encoding="utf-8")
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "required": ["name"],
        "properties": {"name": {"type": "string"}},
    }
    service = SchemaAuthoringService()
    form = service.BuildSchemaForm(schema, source=source)
    candidate = service.PreviewFormEdit(form, {"/name": "after"})
    source.write_text("name: changed-externally\n", encoding="utf-8")

    saved = service.SaveAuthoringCandidate(candidate, candidate.confirmation_token, confirmed=True)

    assert not saved.success
    assert "changed-externally" in source.read_text(encoding="utf-8")
