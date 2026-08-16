"""Deterministic non-Kit Task 028 spatial configuration acceptance probe."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "src" / "kit" / "cellforge.studio"))
    from cellforge.studio.project_service import ProjectCommandService

    temporary_root = Path(os.environ.get("CELLFORGE_TEST_TEMP", root))
    with tempfile.TemporaryDirectory(prefix="cellforge-task028-", dir=temporary_root) as directory:
        project = Path(directory) / "pen-project"
        shutil.copytree(root / "examples" / "pen_engraving", project)
        shutil.copytree(root / "schemas", project / "schemas")
        cell_path = project / "cell.yaml"
        cell_path.write_text(
            cell_path.read_text(encoding="utf-8").replace(
                "schema: ../../schemas/recipe.schema.json", "schema: schemas/recipe.schema.json"
            ),
            encoding="utf-8",
            newline="\n",
        )
        backend = ProjectCommandService(root / "schemas")
        opened = backend.inspect(project)
        if opened.contents is None:
            raise RuntimeError("Task 028 probe could not open the reference project")
        moved = backend.set_component_transform(
            project,
            opened.contents,
            instance_id="camera-001",
            matrix=(
                1.0,
                0.0,
                0.0,
                0.7,
                0.0,
                1.0,
                0.0,
                -0.3,
                0.0,
                0.0,
                1.0,
                1.2,
                0.0,
                0.0,
                0.0,
                1.0,
            ),
        )
        if moved.contents is None:
            raise RuntimeError("Task 028 probe rejected a valid component transform")
        calibration = backend.create_calibration(
            project,
            moved.contents,
            instance_id="camera-001",
            kind="camera.intrinsics",
            valid_until=(datetime.now(UTC) + timedelta(days=1)).isoformat(),
            data={"focal_length_mm": 12.0},
        )
        if calibration.contents is None or calibration.calibration_path is None:
            raise RuntimeError("Task 028 probe could not stage a valid calibration")
        saved = backend.save(project, calibration.contents)
        if saved.contents is None or not (project / calibration.calibration_path).is_file():
            raise RuntimeError(
                "Task 028 probe did not transactionally persist spatial configuration"
            )
        reopened = backend.inspect(project)
        if reopened.contents is None or (
            reopened.contents.cell_yaml != saved.contents.cell_yaml
            or reopened.contents.scene_usda != saved.contents.scene_usda
        ):
            raise RuntimeError("Task 028 probe did not reopen identical paired spatial identities")
        if "matrix4d xformOp:transform" not in reopened.contents.scene_usda:
            raise RuntimeError("Task 028 probe did not persist the component transform")
    print("Verified Task 028 spatial configuration and calibration headlessly.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
