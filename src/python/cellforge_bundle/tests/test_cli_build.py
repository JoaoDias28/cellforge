from __future__ import annotations

import json
import shutil
from pathlib import Path

from cellforge_cli.main import main
from pytest import CaptureFixture

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]


def _project_copy(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    shutil.copytree(REPOSITORY_ROOT / "examples" / "pen_engraving", project)
    shutil.copytree(REPOSITORY_ROOT / "schemas", project / "schemas")
    cell_path = project / "cell.yaml"
    cell_path.write_text(
        cell_path.read_text(encoding="utf-8").replace(
            "schema: ../../schemas/recipe.schema.json",
            "schema: schemas/recipe.schema.json",
        ),
        encoding="utf-8",
        newline="\n",
    )
    return project


def test_cli_build_writes_once_and_reports_output_failure(
    tmp_path: Path, capsys: CaptureFixture[str]
) -> None:
    project = _project_copy(tmp_path)
    output = tmp_path / "manifest.json"
    arguments = [
        "--json",
        "build",
        str(project),
        "--target",
        "pen-sim-amd64",
        "--mode",
        "simulation",
        "--source-revision",
        "b" * 40,
        "--output",
        str(output),
    ]

    assert main(arguments) == 0
    first = json.loads(capsys.readouterr().out)
    assert first["ok"] is True
    assert output.is_file()

    assert main(arguments) == 6
    second = json.loads(capsys.readouterr().out)
    assert second["ok"] is False
    assert second["errors"][0]["code"] == "cli.manifest-write-failed"
