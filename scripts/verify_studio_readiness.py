"""Headless Task 040 acceptance probe for deterministic readiness guidance."""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "kit" / "cellforge.studio"))
sys.path.insert(0, str(ROOT / "src" / "python" / "cellforge_domain" / "src"))
sys.path.insert(0, str(ROOT / "src" / "python" / "cellforge_cli" / "src"))

from cellforge.studio.application import ProjectContents  # noqa: E402
from cellforge.studio.readiness import (  # noqa: E402
    EvaluateStudioReadiness,
    ReadinessBackendProbe,
    ReadinessStatus,
    validate_studio_readiness_report_document,
)


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
    service = EvaluateStudioReadiness(schemas)
    pen = ROOT / "examples" / "pen_engraving"
    kitting = ROOT / "examples" / "kitting"

    nominal = service.EvaluateStudioReadiness(pen)
    kitting_report = service.EvaluateStudioReadiness(kitting)
    if nominal.summary.blocked_count or kitting_report.summary.blocked_count:
        raise RuntimeError("nominal pen/kitting readiness unexpectedly blocked")
    if nominal.observed_fidelity != "L0" or kitting_report.observed_fidelity != "L0":
        raise RuntimeError("nominal reports did not preserve explicit L0 fidelity")
    if validate_studio_readiness_report_document(nominal.normalized()):
        raise RuntimeError("nominal report failed its Draft 2020-12 diagnostic schema")

    advisory = next(check for check in nominal.checks if check.status == ReadinessStatus.ADVISORY)
    if advisory.category not in {"calibration", "evidence", "safety_review"}:
        raise RuntimeError("nominal advisory was not source-linked to an expected category")

    unavailable = service.EvaluateStudioReadiness(
        pen,
        requested_fidelity="L2",
        backend_probe=ReadinessBackendProbe(
            available=False,
            observed_fidelity="L0",
            detail="Isaac Sim/GPU probe unavailable",
        ),
    )
    fidelity = next(check for check in unavailable.checks if check.category == "fidelity")
    if fidelity.status != ReadinessStatus.UNAVAILABLE:
        raise RuntimeError("unavailable L2 backend was coerced into a pass")

    with tempfile.TemporaryDirectory(prefix="cellforge-readiness-probe-") as temporary:
        project = _copy_project(Path(temporary) / "blocked", pen)
        (project / "components" / "robot" / "component.yaml").unlink()
        blocked = service.EvaluateStudioReadiness(project)
        if blocked.summary.blocked_count == 0:
            raise RuntimeError("missing component manifest did not block readiness")

        project = _copy_project(Path(temporary) / "preview", pen)
        contents = ProjectContents(
            cell_yaml=(project / "cell.yaml")
            .read_text(encoding="utf-8")
            .replace("Pen Engraving Reference Cell", "Readiness Preview Cell"),
            scene_usda=(project / "scene.usda").read_text(encoding="utf-8"),
        )
        before = {name: (project / name).read_bytes() for name in ("cell.yaml", "scene.usda")}
        preview = service.PreviewStudioReadinessRemediation(
            project,
            "readiness.open-validator",
            candidate_contents=contents,
        )
        if not preview.can_save:
            raise RuntimeError("valid remediation candidate was not saveable")
        if any((project / name).read_bytes() != data for name, data in before.items()):
            raise RuntimeError("remediation preview changed a canonical source")
        saved = service.SaveStudioReadiness(
            preview,
            preview.confirmation_token,
            confirmed=True,
        )
        if (
            not saved.success
            or b"Readiness Preview Cell" not in (project / "cell.yaml").read_bytes()
        ):
            raise RuntimeError("explicit readiness Save did not commit the reviewed candidate")

    if nominal.to_json() != service.EvaluateStudioReadiness(pen).to_json():
        raise RuntimeError("readiness report replay was not deterministic")
    print(
        "Verified Task 040 nominal, blocked, advisory, unavailable, deterministic, "
        "no-write preview, and explicit Save readiness paths."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
