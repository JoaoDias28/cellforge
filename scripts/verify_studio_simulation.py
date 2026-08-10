"""GPU-independent Task 018 scenario-control acceptance probe."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    package_root = root / "ros_ws" / "src" / "cellforge_simulation"
    sys.path.insert(0, str(package_root))

    from cellforge_simulation.backends import ContractSimulationBackend
    from cellforge_simulation.models import (
        AdapterRegistration,
        load_canonical_project,
        load_scenario,
    )
    from cellforge_simulation.service import SimulationControlService

    project_root = root / "examples" / "pen_engraving"
    scenario_path = project_root / "scenarios" / "nominal.yaml"
    scenario = load_scenario(scenario_path)
    project = load_canonical_project(project_root, scenario_path)
    service = SimulationControlService(ContractSimulationBackend())
    for instance_id in project.required_adapter_ids:
        service.register_adapter(
            AdapterRegistration.create(
                instance_id,
                ["sdk.test.execute"],
                "L0",
                f"/device/{instance_id}/execute",
                [],
            )
        )
    service.configure(scenario, project=project)
    first_samples = service.reset()
    replay_samples = service.reset()
    if first_samples != replay_samples:
        raise RuntimeError("same-seed reset did not reproduce exact setup samples")
    service.start()
    for event_type in scenario.assertions.required_events:
        service.capture_event(event_type)
    with tempfile.TemporaryDirectory(prefix="cellforge-task-018-") as directory:
        evidence_path = Path(directory) / "nominal.evidence.json"
        result = service.finalize(scenario.assertions.final_status, evidence_path)
        report = json.loads(evidence_path.read_text(encoding="utf-8"))
        if not result.passed or report["fidelity"]["achieved"] != "L0":
            raise RuntimeError("nominal Task 018 evidence did not pass honestly at L0")
        if report["canonical_project"]["cell_yaml"]["sha256"] != project.cell_sha256:
            raise RuntimeError("evidence did not preserve canonical cell.yaml identity")
        if report["canonical_project"]["usd_scene"]["sha256"] != project.scene_sha256:
            raise RuntimeError("evidence did not preserve canonical USD scene identity")
    print("Verified deterministic Task 018 control, fidelity, trace assertions, and evidence.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
