from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SIMULATION_ROOT = REPOSITORY_ROOT / "ros_ws" / "src" / "cellforge_simulation"
if str(SIMULATION_ROOT) not in sys.path:
    sys.path.insert(0, str(SIMULATION_ROOT))

from cellforge_simulation.models import (  # noqa: E402
    AdapterRegistration,
    CanonicalProject,
    FaultDefinition,
    ScenarioValidationError,
    load_canonical_project,
    load_scenario,
    parse_scenario,
)
from cellforge_simulation.service import (  # noqa: E402
    EvidenceWriteError,
    SimulationControlError,
    SimulationControlService,
)

NOMINAL = REPOSITORY_ROOT / "examples" / "pen_engraving" / "scenarios" / "nominal.yaml"
INSTANCE_IDS = ("camera-001", "fixture-001", "gripper-001", "laser-001", "robot-001")


def canonical_project(required: tuple[str, ...] = INSTANCE_IDS) -> CanonicalProject:
    return CanonicalProject(
        root="project",
        cell_id="cell-001",
        cell_path="project/cell.yaml",
        cell_sha256="d" * 64,
        scene_path="project/scene.usda",
        scene_sha256="e" * 64,
        required_adapter_ids=required,
    )


class RecordingBackend:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []

    def reset(self, seed: int, initial_state: dict[str, Any]) -> None:
        self.calls.append(("reset", (seed, initial_state)))

    def play(self) -> None:
        self.calls.append(("play", None))

    def pause(self) -> None:
        self.calls.append(("pause", None))

    def step(self, count: int) -> None:
        self.calls.append(("step", count))

    def inject_fault(self, fault: FaultDefinition) -> None:
        self.calls.append(("fault", fault))


def registration(instance_id: str, fidelity: str = "L0") -> AdapterRegistration:
    return AdapterRegistration.create(
        instance_id,
        ["sdk.test.execute"],
        fidelity,
        f"/device/{instance_id}/execute",
        ["laser.process.timeout", "sdk.test.injected_fault"],
    )


def configured_service(
    *, fidelity: str = "L0", scenario_fidelity: str = "L0"
) -> tuple[SimulationControlService, RecordingBackend]:
    backend = RecordingBackend()
    service = SimulationControlService(backend)
    for instance_id in INSTANCE_IDS:
        service.register_adapter(registration(instance_id, fidelity))
    scenario = parse_scenario(
        {
            "schema_version": "0.1.0",
            "scenario": {
                "id": "task-018-nominal",
                "name": "Task 018 nominal control",
                "seed": 1001,
                "timeout_seconds": 10,
            },
            "simulation": {"requested_fidelity": scenario_fidelity},
            "job": {},
            "initial_state": {"product_present": True, "safety_healthy": True},
            "randomization": {
                "product_x_mm": {"distribution": "uniform", "min": -1.0, "max": 1.0},
                "product_y_mm": {"distribution": "uniform", "min": -2.0, "max": 2.0},
            },
            "faults": [],
            "assertions": {
                "final_status": "SUCCESS",
                "required_events": ["simulation.started", "job.completed"],
                "forbidden_events": ["safety.bypass"],
            },
        },
        source="task-018-test",
        source_sha256="a" * 64,
    )
    service.configure(scenario, project=canonical_project())
    return service, backend


def test_nominal_scenario_requires_clean_reset_and_stores_evidence(tmp_path: Path) -> None:
    service, backend = configured_service()
    with pytest.raises(SimulationControlError, match="expected PAUSED"):
        service.start()

    samples = service.reset()
    service.start()
    service.capture_event("job.completed")
    evidence = tmp_path / "evidence" / "nominal.json"
    result = service.finalize("SUCCESS", evidence)

    assert result.passed is True
    assert backend.calls[0][0] == "reset"
    assert backend.calls[1][0] == "play"
    report = json.loads(evidence.read_text(encoding="utf-8"))
    assert report["scenario"]["seed"] == 1001
    assert report["canonical_project"]["cell_yaml"]["sha256"] == "d" * 64
    assert report["canonical_project"]["usd_scene"]["sha256"] == "e" * 64
    assert report["randomization_samples"] == samples
    assert report["fidelity"]["achieved"] == "L0"
    assert "no kinematics" in report["fidelity"]["limitations"].lower()
    assert "rated hardware" in report["safety_boundary"]


def test_same_seed_reset_is_exactly_reproducible_and_global_rng_independent(
    tmp_path: Path,
) -> None:
    first, first_backend = configured_service()
    second, second_backend = configured_service()

    first_samples = first.reset()
    second_samples = second.reset()
    replay_samples = first.reset()

    assert first_samples == second_samples == replay_samples
    assert first_backend.calls[0][1][1] == second_backend.calls[0][1][1]
    first.start()
    second.start()
    first.capture_event("job.completed")
    second.capture_event("job.completed")
    first_path = tmp_path / "first.json"
    second_path = tmp_path / "second.json"
    first.finalize("SUCCESS", first_path)
    second.finalize("SUCCESS", second_path)
    assert first_path.read_bytes() == second_path.read_bytes()


def test_backend_reset_failure_does_not_claim_a_clean_reset() -> None:
    class FailingBackend(RecordingBackend):
        def reset(self, seed: int, initial_state: dict[str, Any]) -> None:
            raise RuntimeError("injected backend reset failure")

    service, _ = configured_service()
    service._backend = FailingBackend()
    with pytest.raises(RuntimeError, match="injected backend reset failure"):
        service.reset()
    assert service.state.value == "CONFIGURED"


def test_pause_step_reset_and_invalid_control_paths_are_explicit() -> None:
    service, backend = configured_service()
    service.reset()
    service.step(3)
    service.start()
    service.pause()
    with pytest.raises(SimulationControlError, match="count must be"):
        service.step(0)
    service.reset()

    assert [call[0] for call in backend.calls] == ["reset", "step", "play", "pause", "reset"]
    assert [event.event_type for event in service.trace] == ["simulation.reset"]


def test_adapter_registration_conflict_missing_adapter_and_unsupported_fidelity_fail_closed() -> (
    None
):
    backend = RecordingBackend()
    service = SimulationControlService(backend)
    service.register_adapter(registration("robot-001"))
    with pytest.raises(SimulationControlError, match="conflict"):
        service.register_adapter(registration("robot-001", "L1"))
    service.register_adapter(
        AdapterRegistration.create(
            "robot-001",
            ["robot_motion.move_to_pose"],
            "L0",
            "/device/robot-001/move_to_pose",
        )
    )
    assert len(service.registrations) == 2

    scenario = parse_scenario(
        {
            "schema_version": "0.1.0",
            "scenario": {"id": "l2", "name": "L2 request", "seed": 4},
            "simulation": {"requested_fidelity": "L2"},
            "job": {},
            "initial_state": {},
            "faults": [],
            "assertions": {
                "final_status": "SUCCESS",
                "required_events": [],
                "forbidden_events": [],
            },
        },
        source="unsupported",
        source_sha256="b" * 64,
    )
    with pytest.raises(SimulationControlError, match="missing"):
        service.configure(scenario, project=canonical_project(("robot-001", "laser-001")))
    with pytest.raises(SimulationControlError, match="requested L2.*supports L0"):
        service.configure(scenario, project=canonical_project(("robot-001",)))


def test_fault_injection_is_target_checked_and_captured() -> None:
    service, backend = configured_service()
    service.reset()
    fault = FaultDefinition("before:ExecuteProcess", "laser-001", "laser.process.timeout", {})
    service.inject_fault(fault)
    with pytest.raises(SimulationControlError, match="not a required adapter"):
        service.inject_fault(FaultDefinition("now", "unknown-001", "fault", {}))
    with pytest.raises(SimulationControlError, match="does not declare"):
        service.inject_fault(FaultDefinition("now", "laser-001", "unsupported.fault", {}))

    assert backend.calls[-1] == ("fault", fault)
    assert service.trace[-1].result_code == "laser.process.timeout"


def test_scheduled_fault_is_applied_once_at_exact_trigger() -> None:
    scenario_path = NOMINAL.parent / "laser_timeout.yaml"
    scenario = load_scenario(scenario_path)
    backend = RecordingBackend()
    service = SimulationControlService(backend)
    for instance_id in INSTANCE_IDS:
        service.register_adapter(registration(instance_id))
    service.configure(scenario, project=canonical_project())
    service.reset()

    assert service.apply_scheduled_faults("before:ExecuteProcess") == 1
    assert service.apply_scheduled_faults("before:ExecuteProcess") == 0
    assert backend.calls[-1][0] == "fault"


def test_trace_assertion_failure_is_stored_as_failed_evidence(tmp_path: Path) -> None:
    service, _ = configured_service()
    service.reset()
    service.start()
    service.capture_event("safety.bypass")
    evidence = tmp_path / "failed.json"
    result = service.finalize("RECOVERABLE_FAULT", evidence)

    assert result.passed is False
    assert len(result.failures) == 3
    report = json.loads(evidence.read_text(encoding="utf-8"))
    assert report["result"]["passed"] is False
    assert report["result"]["failures"] == list(result.failures)


def test_evidence_write_failure_never_reports_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, _ = configured_service()
    service.reset()
    service.start()
    service.capture_event("job.completed")

    def fail_replace(_source: Path, _target: Path) -> None:
        raise OSError("injected storage failure")

    monkeypatch.setattr("cellforge_simulation.service.os.replace", fail_replace)
    with pytest.raises(EvidenceWriteError, match="injected storage failure"):
        service.finalize("SUCCESS", tmp_path / "evidence.json")


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda value: value["scenario"].update(seed=-1), "non-negative integer"),
        (
            lambda value: value.update(randomization={"x": {"distribution": "normal"}}),
            "expected exactly distribution",
        ),
        (
            lambda value: value.update(simulation={"requested_fidelity": "L9"}),
            "unsupported fidelity",
        ),
        (lambda value: value.update(unexpected=True), "unknown top-level"),
    ],
)
def test_invalid_scenario_inputs_are_rejected(mutation: Any, message: str) -> None:
    document: dict[str, Any] = {
        "schema_version": "0.1.0",
        "scenario": {"id": "invalid", "name": "Invalid", "seed": 1},
        "job": {},
        "initial_state": {},
        "faults": [],
        "assertions": {
            "final_status": "SUCCESS",
            "required_events": [],
            "forbidden_events": [],
        },
    }
    mutation(document)
    with pytest.raises(ScenarioValidationError, match=message):
        parse_scenario(document, source="invalid", source_sha256="c" * 64)


def test_existing_nominal_scenario_parses_without_seed_or_source_changes() -> None:
    scenario = load_scenario(NOMINAL)
    project = load_canonical_project(NOMINAL.parents[1], NOMINAL)
    assert scenario.scenario_id == "pen-nominal"
    assert scenario.seed == 1001
    assert scenario.requested_fidelity.name == "L0"
    assert project.required_adapter_ids == INSTANCE_IDS
    assert Path(project.scene_path).name == "scene.usda"


def test_all_reference_scenarios_configure_against_registered_l0_adapters() -> None:
    scenario_root = NOMINAL.parent
    project_root = scenario_root.parent
    for path in sorted(scenario_root.glob("*.yaml")):
        backend = RecordingBackend()
        service = SimulationControlService(backend)
        for instance_id in INSTANCE_IDS:
            fault_codes = [
                "laser.process.timeout",
                "laser.process.outcome_unknown",
                "sdk.test.injected_fault",
            ]
            service.register_adapter(
                AdapterRegistration.create(
                    instance_id,
                    ["sdk.test.execute"],
                    "L0",
                    f"/device/{instance_id}/execute",
                    fault_codes,
                )
            )
        service.configure(
            load_scenario(path),
            project=load_canonical_project(project_root, path),
        )
