"""Isaac Sim 6/OpenUSD Task 028 spatial configuration interaction probe."""

from __future__ import annotations

import os
import shutil
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import omni.kit.app
from pxr import Usd

from cellforge.studio.project_service import ProjectCommandService

root = Path.cwd().resolve()
temporary_root = Path(os.environ.get("CELLFORGE_TEST_TEMP", root))
with tempfile.TemporaryDirectory(prefix="cellforge-task028-kit-", dir=temporary_root) as directory:
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
        raise RuntimeError("Kit Task 028 probe could not open the reference project")
    transformed = backend.set_component_transform(
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
    if transformed.contents is None:
        raise RuntimeError("Kit Task 028 probe rejected the selected viewport transform")
    calibration = backend.create_calibration(
        project,
        transformed.contents,
        instance_id="camera-001",
        kind="camera.intrinsics",
        valid_until=(datetime.now(UTC) + timedelta(days=1)).isoformat(),
        data={"focal_length_mm": 12.0},
    )
    if calibration.contents is None or calibration.calibration_path is None:
        raise RuntimeError("Kit Task 028 probe rejected the selected component calibration")
    saved = backend.save(project, calibration.contents)
    if saved.contents is None:
        raise RuntimeError("Kit Task 028 probe could not transactionally save the paired edit")
    stage = Usd.Stage.Open(str(project / "scene.usda"))
    if stage is None:
        raise RuntimeError("OpenUSD could not compose the configured Task 028 stage")
    camera = stage.GetPrimAtPath("/World/Camera")
    if not camera.IsValid() or not camera.GetAttribute("xformOp:transform").IsValid():
        raise RuntimeError("OpenUSD did not compose the selected component transform")
    if not (project / calibration.calibration_path).is_file():
        raise RuntimeError("Kit Task 028 probe did not persist the immutable calibration")

print("Verified Task 028 spatial configuration through Isaac Sim 6/OpenUSD.")
omni.kit.app.get_app().post_quit(0)
