"""Deterministic non-Kit Task 016 component placement acceptance probe."""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path
from uuid import UUID

import yaml


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "src" / "kit" / "cellforge.studio"))
    from cellforge.studio.component_service import ComponentPlacementService
    from cellforge.studio.project_service import ProjectCommandService

    with tempfile.TemporaryDirectory(prefix="cellforge-task016-", dir=root) as directory:
        project = Path(directory) / "pen-project"
        shutil.copytree(root / "examples" / "pen_engraving", project)
        shutil.copytree(root / "schemas", project / "schemas")
        cell_path = project / "cell.yaml"
        cell_path.write_text(
            cell_path.read_text(encoding="utf-8").replace(
                "schema: ../../schemas/recipe.schema.json",
                "schema: schemas/recipe.schema.json",
            ),
            encoding="utf-8",
            newline="\n",
        )
        components = ComponentPlacementService(
            root / "schemas",
            new_uuid=lambda: UUID("12345678-1234-5678-1234-567812345678"),
        )
        backend = ProjectCommandService(root / "schemas", component_service=components)
        opened = backend.inspect(project)
        if opened.contents is None:
            raise RuntimeError("Task 016 probe could not open the reference project")
        browser = backend.browse_components(project)
        if len(browser.components) != 6:
            raise RuntimeError("Task 016 probe did not discover the reference registry")
        placed = backend.place_component(
            project,
            opened.contents,
            component="generic.pen_fixture.reference",
            version="0.1.0",
            alias="probe_fixture",
            variants={},
        )
        if placed.contents is None or placed.instance_id is None:
            raise RuntimeError("Task 016 probe placement was rejected")
        saved = backend.save(project, placed.contents)
        if saved.project is None:
            raise RuntimeError("Task 016 probe could not save the linked artifact pair")
        document = yaml.safe_load(cell_path.read_text(encoding="utf-8"))
        ids = {item["id"] for item in document["components"]}
        scene_text = (project / "scene.usda").read_text(encoding="utf-8")
        if placed.instance_id not in ids or placed.instance_id not in scene_text:
            raise RuntimeError("Task 016 probe did not persist the shared immutable instance ID")
    print("Verified Task 016 browser and linked component placement headlessly.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
