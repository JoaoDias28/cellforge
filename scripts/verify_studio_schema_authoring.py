"""Headless Task 041 acceptance probe for schema-driven authoring."""

from __future__ import annotations

import hashlib
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "kit" / "cellforge.studio"))
sys.path.insert(0, str(ROOT / "src" / "python" / "cellforge_domain" / "src"))
sys.path.insert(0, str(ROOT / "src" / "python" / "cellforge_cli" / "src"))

from cellforge.studio.schema_authoring import SchemaAuthoringService  # noqa: E402
from cellforge.studio.schema_form_renderer import SchemaFormRenderer  # noqa: E402


def _copy_project(destination: Path, source: Path) -> Path:
    shutil.copytree(source, destination)
    shutil.copytree(ROOT / "schemas", destination / "schemas")
    cell_path = destination / "cell.yaml"
    cell_path.write_text(
        cell_path.read_text(encoding="utf-8").replace(
            "../../schemas/recipe.schema.json", "schemas/recipe.schema.json"
        ),
        encoding="utf-8",
    )
    return destination


def main() -> int:
    schemas = ROOT / "schemas"
    examples = ROOT / "examples"
    service = SchemaAuthoringService(schemas)

    cell = service.BuildSchemaForm(
        schemas / "cell.schema.json",
        source=examples / "pen_engraving" / "cell.yaml",
        schema_kind="cell",
    )
    recipe = service.BuildSchemaForm(
        schemas / "recipe.schema.json",
        source=examples / "pen_engraving" / "recipe.yaml",
        schema_kind="recipe",
    )
    scenario = service.BuildSchemaForm(
        schemas / "scenario.schema.json",
        source=examples / "kitting" / "scenarios" / "gripper_close_recovery.yaml",
        schema_kind="scenario",
    )
    component = service.BuildSchemaForm(
        examples / "kitting" / "components" / "gripper" / "config.schema.json",
        {"jaw_opening_mm": 25},
        schema_kind="component-config",
    )
    if any(form.findings for form in (cell, recipe, scenario, component)):
        raise RuntimeError("canonical Task 041 forms returned validation findings")
    if not any(field.unit == "s" for field in recipe.fields):
        raise RuntimeError("recipe timing annotation was not rendered")
    if not any(field.advanced for field in recipe.fields):
        raise RuntimeError("recipe advanced fields were not rendered")
    if not any(
        field.unit == "mm"
        for field in service.BuildSchemaForm(
            examples / "kitting" / "components" / "gripper" / "config.schema.json",
            {"jaw_opening_mm": 25},
        ).fields
    ):
        raise RuntimeError("component configuration unit annotation was not rendered")
    if not SchemaFormRenderer().render(recipe).fields:
        raise RuntimeError("schema renderer returned no fields")

    before = {"recipe": (examples / "pen_engraving" / "recipe.yaml").read_bytes()}
    candidate = service.PreviewSourceEdit(
        recipe,
        recipe.source_text.replace("Pen Engraving Reference", "Task 041 Probe", 1),
    )
    if not candidate.can_save:
        raise RuntimeError("valid source preview was not saveable")
    if hashlib.sha256(before["recipe"]).hexdigest() != candidate.base_source_hash:
        raise RuntimeError("preview base hash did not identify the original source")
    if (examples / "pen_engraving" / "recipe.yaml").read_bytes() != before["recipe"]:
        raise RuntimeError("source preview wrote the example recipe")

    with tempfile.TemporaryDirectory(prefix="cellforge-task-041-probe-") as temporary:
        project = _copy_project(Path(temporary) / "project", examples / "pen_engraving")
        source = project / "recipe.yaml"
        form = service.BuildSchemaForm(
            schemas / "recipe.schema.json", source=source, schema_kind="recipe"
        )
        changed = service.PreviewFormEdit(form, {"/recipe/name": "Task 041 Probe"})
        if not changed.can_save or not changed.diff:
            raise RuntimeError("form preview did not produce a saveable structured diff")
        if not source.is_file():
            raise RuntimeError("probe source disappeared during no-write preview")
        saved = service.SaveAuthoringCandidate(changed, changed.confirmation_token, confirmed=True)
        if not saved.success or b"Task 041 Probe" not in source.read_bytes():
            raise RuntimeError("explicit direct Save did not persist the reviewed candidate")

    ambiguity = service.BuildSchemaForm(
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "required": ["mode"],
            "properties": {"mode": {"enum": ["a", "b"]}},
        },
        {},
    )
    if not ambiguity.choices or ambiguity.can_save:
        raise RuntimeError("ambiguous required enum did not remain unresolved")

    print(
        "Verified Task 041 canonical forms, annotations, renderer, deterministic preview, "
        "no-write hashes, explicit Save, and ambiguity handling."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
