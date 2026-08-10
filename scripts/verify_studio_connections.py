"""Deterministic non-Kit Task 017 connection-authoring acceptance probe."""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

import yaml


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "src" / "kit" / "cellforge.studio"))
    from cellforge.studio.project_service import ProjectCommandService

    with tempfile.TemporaryDirectory(prefix="cellforge-task017-", dir=root) as directory:
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
        backend = ProjectCommandService(root / "schemas")
        opened = backend.inspect(project)
        if opened.contents is None:
            raise RuntimeError("Task 017 probe could not open the reference project")
        graph = backend.browse_connections(project, opened.contents)
        if not graph.ports or not all(
            edge.modeled_only and not edge.executable
            for edge in graph.edges
            if edge.kind == "safety"
        ):
            raise RuntimeError("Task 017 probe did not preserve modeled-safety semantics")
        connected = backend.connect_ports(
            project,
            opened.contents,
            connection_id="software-cycle-state-probe",
            kind="software",
            from_component="laser-001",
            from_port="cycle_state",
            to_component="camera-001",
            to_port="process_state",
        )
        if connected.contents is None or connected.edge is None or not connected.edge.executable:
            raise RuntimeError("Task 017 probe rejected a compatible software connection")
        invalid = backend.connect_ports(
            project,
            opened.contents,
            connection_id="invalid-probe",
            kind="industrial_io",
            from_component="fixture-001",
            from_port="seated",
            to_component="robot-001",
            to_port="trajectory",
        )
        if invalid.contents is not None or not invalid.validation:
            raise RuntimeError("Task 017 probe silently accepted an incompatible connection")
        saved = backend.save(project, connected.contents)
        if saved.project is None:
            raise RuntimeError("Task 017 probe could not persist the validated edge")
        document = yaml.safe_load(cell_path.read_text(encoding="utf-8"))
        if "software-cycle-state-probe" not in {item["id"] for item in document["connections"]}:
            raise RuntimeError("Task 017 probe did not persist the connection in cell.yaml")
    print("Verified Task 017 typed connection authoring and validation headlessly.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
