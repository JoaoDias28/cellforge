"""Unit and contract tests for ScenarioEvidenceService."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cellforge.studio.application import ProjectContents
from cellforge.studio.scenario_service import (
    SAFETY_DISCLAIMER,
    ScenarioAssertionSpec,
    ScenarioEvidenceService,
    ScenarioFaultSpec,
)

ROOT = Path(__file__).resolve().parents[4]
SCHEMAS = ROOT / "schemas"
PEN_PROJECT = ROOT / "examples" / "pen_engraving"


@pytest.fixture
def pen_contents() -> ProjectContents:
    cell_yaml = (PEN_PROJECT / "cell.yaml").read_text(encoding="utf-8")
    scene_usda = (PEN_PROJECT / "scene.usda").read_text(encoding="utf-8")
    return ProjectContents(cell_yaml=cell_yaml, scene_usda=scene_usda)


@pytest.fixture
def scenario_service() -> ScenarioEvidenceService:
    return ScenarioEvidenceService(SCHEMAS)


def test_browse_scenarios_discovers_pen_scenarios(
    scenario_service: ScenarioEvidenceService, pen_contents: ProjectContents
) -> None:
    result = scenario_service.browse_scenarios(PEN_PROJECT, pen_contents)

    assert len(result.scenarios) == 14
    ids = {s.id for s in result.scenarios}
    assert "pen-nominal" in ids
    assert "pen-physical-nominal" in ids
    assert "pen-laser-timeout" in ids
    assert "pen-physical-dropped" in ids

    # Check fidelity breakdown
    l0_scenarios = [s for s in result.scenarios if s.requested_fidelity == "L0"]
    l2_scenarios = [s for s in result.scenarios if s.requested_fidelity == "L2"]
    assert len(l0_scenarios) == 10
    assert len(l2_scenarios) == 4


def test_inspect_scenario_parses_details(
    scenario_service: ScenarioEvidenceService, pen_contents: ProjectContents
) -> None:
    detail = scenario_service.inspect_scenario(
        PEN_PROJECT, pen_contents, scenario_id_or_path="nominal"
    )
    assert detail is not None
    assert detail.summary.id == "pen-nominal"
    assert detail.summary.seed == 1001
    assert detail.summary.requested_fidelity == "L0"
    assert detail.summary.job_recipe_id == "pen-aluminium-reference"
    assert detail.summary.job_recipe_version == 1
    assert detail.assertions.final_status == "SUCCESS"
    assert "process.command.completed" in detail.assertions.required_events
    assert "safety.bypass" in detail.assertions.forbidden_events


def test_execute_nominal_scenario_produces_valid_evidence(
    scenario_service: ScenarioEvidenceService, pen_contents: ProjectContents
) -> None:
    result = scenario_service.execute_scenario(
        PEN_PROJECT,
        pen_contents,
        scenario_id_or_path="nominal",
        seed_override=2002,
        available_backend_fidelity="L0",
    )

    assert result.passed is True
    assert result.final_status == "SUCCESS"
    assert len(result.failures) == 0
    assert result.fidelity.achieved == "L0"
    assert result.fidelity.safety_disclaimer == SAFETY_DISCLAIMER
    assert len(result.trace_events) > 5

    # Check canonical evidence document fields
    doc = result.evidence_document
    assert doc["schema_version"] == "0.1.0"
    assert doc["kind"] == "cellforge.simulation_evidence"
    assert doc["scenario"]["id"] == "pen-nominal"
    assert doc["scenario"]["seed"] == 2002
    assert doc["result"]["passed"] is True
    assert doc["result"]["final_status"] == "SUCCESS"
    assert "cell_yaml" in doc["canonical_project"]
    assert "usd_scene" in doc["canonical_project"]
    assert doc["safety_disclaimer"] == SAFETY_DISCLAIMER


def test_execute_scenario_with_fault_injection(
    scenario_service: ScenarioEvidenceService, pen_contents: ProjectContents
) -> None:
    injected = [
        ScenarioFaultSpec(
            at="process.cycle",
            target="laser-001",
            fault="laser.process.timeout",
            parameters={"timeout_ms": 5000},
        )
    ]
    result = scenario_service.execute_scenario(
        PEN_PROJECT,
        pen_contents,
        scenario_id_or_path="nominal",
        injected_faults=injected,
        available_backend_fidelity="L0",
    )

    assert result.passed is False
    assert result.final_status == "FAILED"
    assert len(result.failures) > 0
    assert any("laser.process.timeout" in f for f in result.failures)


def test_replay_evidence_verifies_deterministic_match(
    scenario_service: ScenarioEvidenceService, pen_contents: ProjectContents
) -> None:
    exec_res = scenario_service.execute_scenario(
        PEN_PROJECT,
        pen_contents,
        scenario_id_or_path="nominal",
        seed_override=1001,
        available_backend_fidelity="L0",
    )

    replay_res = scenario_service.replay_evidence(
        exec_res.evidence_document,
        expected_assertions=ScenarioAssertionSpec(
            final_status="SUCCESS",
            required_events=("process.command.completed", "job.completed"),
            forbidden_events=("safety.bypass",),
        ),
    )

    assert replay_res.passed is True
    assert replay_res.events_matched is True
    assert len(replay_res.mismatches) == 0
    assert replay_res.original_event_count == len(exec_res.trace_events)


def test_fidelity_enforcement_refuses_to_present_l0_as_l2(
    scenario_service: ScenarioEvidenceService, pen_contents: ProjectContents
) -> None:
    # Attempting to run an L2 physical scenario on an L0 backend must fail closed
    with pytest.raises(RuntimeError) as excinfo:
        scenario_service.execute_scenario(
            PEN_PROJECT,
            pen_contents,
            scenario_id_or_path="pen-physical-nominal",
            available_backend_fidelity="L0",
        )
    assert "simulation.fidelity.unsupported" in str(excinfo.value)
    assert "refuses to present lower-fidelity or CPU-only results as L2" in str(excinfo.value)


def test_fidelity_enforcement_requires_cuda_gpu_and_physx_for_l2(
    scenario_service: ScenarioEvidenceService, pen_contents: ProjectContents
) -> None:
    # Attempting L2 without CUDA GPU or PhysX must fail closed
    with pytest.raises(RuntimeError) as excinfo:
        scenario_service.execute_scenario(
            PEN_PROJECT,
            pen_contents,
            scenario_id_or_path="pen-physical-nominal",
            available_backend_fidelity="L2",
            has_cuda_gpu=False,
            actual_physx_executed=False,
        )
    assert "L2 fidelity requires an active NVIDIA CUDA GPU and PhysX" in str(excinfo.value)


def test_browse_and_inspect_stored_evidence(
    scenario_service: ScenarioEvidenceService, pen_contents: ProjectContents, tmp_path: Path
) -> None:
    # Generate an evidence document into a project temp directory
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir(parents=True)
    exec_res = scenario_service.execute_scenario(
        PEN_PROJECT,
        pen_contents,
        scenario_id_or_path="nominal",
        seed_override=3003,
        available_backend_fidelity="L0",
    )
    ev_file = evidence_dir / "evidence_nominal_3003.json"
    ev_file.write_text(json.dumps(exec_res.evidence_document, indent=2), encoding="utf-8")

    # Browse
    summaries = scenario_service.browse_evidence(tmp_path)
    assert len(summaries) == 1
    assert summaries[0].scenario_id == "pen-nominal"
    assert summaries[0].seed == 3003
    assert summaries[0].passed is True

    # Inspect
    detail = scenario_service.inspect_evidence(tmp_path, "evidence/evidence_nominal_3003.json")
    assert detail is not None
    assert detail.summary.scenario_id == "pen-nominal"
    assert len(detail.project_cell_sha256) == 64
    assert len(detail.project_scene_sha256) == 64
    assert detail.safety_disclaimer == SAFETY_DISCLAIMER
