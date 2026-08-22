"""Headless Task 039 acceptance probe for deterministic preview and explicit Save."""

from __future__ import annotations

import hashlib
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "kit" / "cellforge.studio"))

from cellforge.studio.guided_launcher import (  # noqa: E402
    CreateProjectRequest,
    GuidedProjectService,
    validate_project_preview_document,
)


def _hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def main() -> int:
    root = ROOT
    schemas = root / "schemas"
    with tempfile.TemporaryDirectory(prefix="cellforge-guided-probe-") as temporary:
        destination = Path(temporary) / "guided-blank"
        request = CreateProjectRequest(
            template_id="blank",
            destination_directory=destination,
            cell_display_name="Headless Guided Cell",
            requested_schema_version="0.1.0",
            seed=3907,
        )
        service = GuidedProjectService(schemas)
        before = _hashes(Path(temporary))
        first = service.CreateProject(request)
        second = service.PreviewProject(first)
        if first != second or not first.can_save:
            raise RuntimeError("guided preview was not deterministic or saveable")
        validate_project_preview_document(first.as_dict())
        if _hashes(Path(temporary)) != before:
            raise RuntimeError("preview changed the filesystem")

        saved = service.ConfirmProjectSave(
            first,
            first.confirmation_token,
            confirmed=True,
        )
        if not saved.success or not destination.is_dir():
            raise RuntimeError("explicit guided Save did not create a valid project")
        reopened = service.OpenProject(destination)
        if not reopened.is_valid or reopened.contents is None:
            raise RuntimeError("saved guided project did not reopen through the validator")
        if reopened.source_hashes.get("cell.yaml") != first.candidate_hashes.get("cell.yaml"):
            raise RuntimeError("reopened cell.yaml hash differs from preview")
        if reopened.source_hashes.get("scene.usda") != first.candidate_hashes.get("scene.usda"):
            raise RuntimeError("reopened USD hash differs from preview")

    print("Verified Task 039 deterministic guided preview, no-write boundary, and explicit Save.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
