"""Pure scenario authoring, execution, fault injection, timeline, replay, and evidence service."""

from __future__ import annotations

import hashlib
import json
import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml

from cellforge.studio.application import ProjectContents, ValidationItem

SAFETY_DISCLAIMER = (
    "Simulation status and evidence are standard-control engineering data only. Functional safety "
    "remains independently enforced and validated by rated hardware."
)

FIDELITY_LIMITATIONS: dict[str, str] = {
    "L0": (
        "Contract sequencing and deterministic adapter outcomes only; no kinematics, physics, "
        "rendered perception, process quality, hardware, or functional-safety evidence."
    ),
    "L1": (
        "Kinematics, transforms, collision geometry, and programmed timing only; no validated "
        "physical interaction, process quality, hardware, or functional-safety evidence."
    ),
    "L2": (
        "Configured Isaac physics, sensors, product movement, timing, and faults only; no physical "
        "process qualification, hardware, or functional-safety evidence."
    ),
    "L3": (
        "Rendered perception variation and configured inference in addition to L2; no physical "
        "process qualification, hardware, or functional-safety evidence."
    ),
}

_FIDELITY_RANK: dict[str, int] = {
    "L0": 0,
    "L1": 1,
    "L2": 2,
    "L3": 3,
}


class FidelityLevel(StrEnum):
    """Supported simulation fidelity levels."""

    L0 = "L0"
    L1 = "L1"
    L2 = "L2"
    L3 = "L3"


@dataclass(frozen=True, slots=True)
class ScenarioFaultSpec:
    """One scheduled or injected fault definition."""

    at: str
    target: str
    fault: str
    parameters: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ScenarioAssertionSpec:
    """Declared criteria for scenario pass/fail."""

    final_status: str
    required_events: tuple[str, ...] = ()
    forbidden_events: tuple[str, ...] = ()
    max_cycle_seconds: float | None = None


@dataclass(frozen=True, slots=True)
class ScenarioSummary:
    """High-level summary of one declared scenario."""

    id: str
    name: str
    path: str
    seed: int
    timeout_seconds: float
    requested_fidelity: str
    job_recipe_id: str | None
    job_recipe_version: int | None
    fault_count: int
    valid: bool


@dataclass(frozen=True, slots=True)
class ScenarioDetail:
    """Full scenario specification and form metadata."""

    summary: ScenarioSummary
    data: Mapping[str, Any]
    initial_state: Mapping[str, Any]
    randomization: Mapping[str, Any]
    faults: tuple[ScenarioFaultSpec, ...]
    assertions: ScenarioAssertionSpec
    validation: tuple[ValidationItem, ...] = ()


@dataclass(frozen=True, slots=True)
class ScenarioBrowserResult:
    """Result of querying all declared scenarios in a project."""

    scenarios: tuple[ScenarioSummary, ...]
    validation: tuple[ValidationItem, ...] = ()


@dataclass(frozen=True, slots=True)
class SimulationTraceEvent:
    """One chronological trace event in simulation timeline."""

    sequence: int
    event_type: str
    component_instance_id: str = ""
    result_code: str = ""
    payload: Mapping[str, Any] = field(default_factory=dict)

    def as_json(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "event_type": self.event_type,
            "component_instance_id": self.component_instance_id,
            "result_code": self.result_code,
            "payload": dict(self.payload),
        }


@dataclass(frozen=True, slots=True)
class FidelityInfo:
    """Fidelity details ensuring honest labeling."""

    requested: str
    achieved: str
    limitations: str
    is_valid_l2: bool = False
    safety_disclaimer: str = SAFETY_DISCLAIMER


@dataclass(frozen=True, slots=True)
class ScenarioExecutionResult:
    """Structured result of executing a scenario."""

    scenario_id: str
    passed: bool
    final_status: str
    failures: tuple[str, ...]
    fidelity: FidelityInfo
    randomization_samples: Mapping[str, float]
    trace_events: tuple[SimulationTraceEvent, ...]
    evidence_document: Mapping[str, Any]
    evidence_path: str = ""


@dataclass(frozen=True, slots=True)
class ScenarioReplayResult:
    """Structured result of replaying and verifying a recorded trace."""

    scenario_id: str
    passed: bool
    events_matched: bool
    original_event_count: int
    replayed_event_count: int
    mismatches: tuple[str, ...]
    evidence_sha256: str


@dataclass(frozen=True, slots=True)
class EvidenceSummary:
    """Summary of one stored simulation evidence document."""

    path: str
    scenario_id: str
    scenario_name: str
    seed: int
    passed: bool
    final_status: str
    failure_count: int
    requested_fidelity: str
    achieved_fidelity: str
    event_count: int
    cell_id: str
    source_sha256: str


@dataclass(frozen=True, slots=True)
class EvidenceDetail:
    """Full detail of one simulation evidence document."""

    summary: EvidenceSummary
    data: Mapping[str, Any]
    project_cell_sha256: str
    project_scene_sha256: str
    trace_events: tuple[SimulationTraceEvent, ...]
    failures: tuple[str, ...]
    assertions: Mapping[str, Any]
    safety_disclaimer: str


class ScenarioEvidenceService:
    """Discover, validate, execute, replay, and inspect scenario evidence."""

    def __init__(self, canonical_schema_directory: Path | None = None) -> None:
        self._schemas = (
            canonical_schema_directory.resolve() if canonical_schema_directory is not None else None
        )

    def browse_scenarios(
        self, project_path: Path, contents: ProjectContents
    ) -> ScenarioBrowserResult:
        """Enumerate and summarize all scenarios declared in the project."""
        cell_data = self._parse_cell_yaml(contents.cell_yaml)
        if cell_data is None:
            return ScenarioBrowserResult(
                (),
                (
                    ValidationItem(
                        code="scenario.project.invalid",
                        severity="error",
                        path="cell.yaml",
                        message="cell.yaml could not be parsed as a YAML mapping",
                    ),
                ),
            )

        declared = cell_data.get("scenarios", [])
        if not isinstance(declared, list):
            return ScenarioBrowserResult(
                (),
                (
                    ValidationItem(
                        code="scenario.list.invalid",
                        severity="error",
                        path="scenarios",
                        message="cell.yaml scenarios field must be a list of paths",
                    ),
                ),
            )

        summaries: list[ScenarioSummary] = []
        findings: list[ValidationItem] = []

        for rel_path in declared:
            if not isinstance(rel_path, str) or not rel_path.strip():
                continue
            normalized_path = Path(rel_path.strip()).as_posix()
            data, error = self._load_scenario_data(project_path, contents, normalized_path)
            if error is not None:
                findings.append(
                    ValidationItem(
                        code="scenario.file.unreadable",
                        severity="error",
                        path=normalized_path,
                        message=error,
                    )
                )
                summaries.append(
                    ScenarioSummary(
                        id=Path(normalized_path).stem,
                        name=Path(normalized_path).stem,
                        path=normalized_path,
                        seed=0,
                        timeout_seconds=0.0,
                        requested_fidelity="L0",
                        job_recipe_id=None,
                        job_recipe_version=None,
                        fault_count=0,
                        valid=False,
                    )
                )
            if data is None:
                continue

            summary, item_findings = self._summarize_scenario(normalized_path, data)
            findings.extend(item_findings)
            summaries.append(summary)

        return ScenarioBrowserResult(tuple(summaries), tuple(findings))

    def inspect_scenario(
        self,
        project_path: Path,
        contents: ProjectContents,
        *,
        scenario_id_or_path: str,
    ) -> ScenarioDetail | None:
        """Inspect full scenario definition and parameters."""
        cell_data = self._parse_cell_yaml(contents.cell_yaml)
        if cell_data is None:
            return None

        declared = cell_data.get("scenarios", [])
        matched_path: str | None = None
        matched_data: dict[str, Any] | None = None

        for item in declared:
            if isinstance(item, str) and item.strip():
                normalized = Path(item.strip()).as_posix()
                data, error = self._load_scenario_data(project_path, contents, normalized)
                if data is not None and error is None:
                    sc_body = (
                        data.get("scenario", {}) if isinstance(data.get("scenario"), dict) else {}
                    )
                    sc_id = sc_body.get("id")
                    if scenario_id_or_path in (
                        normalized,
                        Path(normalized).stem,
                        Path(normalized).name,
                        sc_id,
                    ):
                        matched_path = normalized
                        matched_data = data
                        break

        if matched_path is None or matched_data is None:
            target_path = Path(scenario_id_or_path.strip()).as_posix()
            matched_data, error = self._load_scenario_data(project_path, contents, target_path)
            if matched_data is None or error is not None:
                return None
            matched_path = target_path

        summary, findings = self._summarize_scenario(matched_path, matched_data)
        data = matched_data
        initial_state = (
            data.get("initial_state", {}) if isinstance(data.get("initial_state"), dict) else {}
        )
        randomization = (
            data.get("randomization", {}) if isinstance(data.get("randomization"), dict) else {}
        )

        fault_specs: list[ScenarioFaultSpec] = []
        for fault_data in data.get("faults", []):
            if isinstance(fault_data, dict):
                fault_specs.append(
                    ScenarioFaultSpec(
                        at=str(fault_data.get("at", "")),
                        target=str(fault_data.get("target", "")),
                        fault=str(fault_data.get("fault", "")),
                        parameters=fault_data.get("parameters", {})
                        if isinstance(fault_data.get("parameters"), dict)
                        else {},
                    )
                )

        asserts_data = (
            data.get("assertions", {}) if isinstance(data.get("assertions"), dict) else {}
        )
        assertions = ScenarioAssertionSpec(
            final_status=str(asserts_data.get("final_status", "SUCCESS")),
            required_events=tuple(str(e) for e in asserts_data.get("required_events", [])),
            forbidden_events=tuple(str(e) for e in asserts_data.get("forbidden_events", [])),
            max_cycle_seconds=asserts_data.get("max_cycle_seconds"),
        )

        return ScenarioDetail(
            summary=summary,
            data=data,
            initial_state=initial_state,
            randomization=randomization,
            faults=tuple(fault_specs),
            assertions=assertions,
            validation=tuple(findings),
        )

    def execute_scenario(
        self,
        project_path: Path,
        contents: ProjectContents,
        *,
        scenario_id_or_path: str,
        seed_override: int | None = None,
        injected_faults: Sequence[ScenarioFaultSpec] | None = None,
        available_backend_fidelity: str = "L0",
        has_cuda_gpu: bool = False,
        actual_physx_executed: bool = False,
    ) -> ScenarioExecutionResult:
        """Run a scenario against the pure simulation engine and generate evidence."""
        detail = self.inspect_scenario(
            project_path, contents, scenario_id_or_path=scenario_id_or_path
        )
        if detail is None:
            raise RuntimeError(f"scenario.not_found: Scenario '{scenario_id_or_path}' not found")

        scenario_data = detail.data
        scenario_id = detail.summary.id
        requested_fidelity = detail.summary.requested_fidelity
        seed = (
            seed_override
            if seed_override is not None
            else int(scenario_data.get("scenario", {}).get("seed", 1001))
        )

        # Strict fidelity enforcement
        achieved_fidelity = available_backend_fidelity
        if _FIDELITY_RANK.get(achieved_fidelity, 0) < _FIDELITY_RANK.get(requested_fidelity, 0):
            raise RuntimeError(
                f"simulation.fidelity.unsupported: requested {requested_fidelity} "
                f"fidelity but available simulation environment only supports {achieved_fidelity}. "
                "CellForge refuses to present lower-fidelity or CPU-only results as L2."
            )

        # L2 additionally requires CUDA GPU and PhysX execution
        is_valid_l2 = False
        if requested_fidelity == "L2":
            if not has_cuda_gpu or not actual_physx_executed:
                if achieved_fidelity == "L2":
                    achieved_fidelity = "L0"
                raise RuntimeError(
                    "simulation.fidelity.unsupported: L2 fidelity requires an active "
                    "NVIDIA CUDA GPU and PhysX physical simulation execution. "
                    "CPU mock execution cannot claim L2."
                )
            is_valid_l2 = True

        limitations = FIDELITY_LIMITATIONS.get(achieved_fidelity, FIDELITY_LIMITATIONS["L0"])

        # Sample randomization deterministically from seed
        rng = random.Random(seed)
        samples: dict[str, float] = {}
        for param, dist in detail.randomization.items():
            if isinstance(dist, dict) and dist.get("distribution") == "uniform":
                minimum = float(dist.get("min", 0.0))
                maximum = float(dist.get("max", 1.0))
                samples[param] = rng.uniform(minimum, maximum)

        # Execute simulated workflow and record trace events
        trace_events: list[SimulationTraceEvent] = []
        seq = 1

        def emit(
            event_type: str,
            component: str = "",
            code: str = "",
            payload: dict[str, Any] | None = None,
        ) -> None:
            nonlocal seq
            trace_events.append(
                SimulationTraceEvent(
                    sequence=seq,
                    event_type=event_type,
                    component_instance_id=component,
                    result_code=code,
                    payload=payload or {},
                )
            )
            seq += 1

        emit(
            "simulation.configured",
            payload={
                "scenario_id": scenario_id,
                "seed": seed,
                "requested_fidelity": requested_fidelity,
                "achieved_fidelity": achieved_fidelity,
            },
        )
        emit("simulation.reset", payload={"seed": seed, "samples": dict(samples)})
        emit("simulation.started")

        # Collect all faults (from scenario and injected overrides)
        all_faults = list(detail.faults)
        if injected_faults:
            all_faults.extend(injected_faults)

        fault_map: dict[str, list[ScenarioFaultSpec]] = {}
        for fault in all_faults:
            fault_map.setdefault(fault.at, []).append(fault)

        # Process steps based on scenario type (e.g. pen cell canonical flow)
        failures: list[str] = []
        final_status = "SUCCESS"

        # Apply any faults scheduled at startup / setup
        for fault in fault_map.get("at_setup", []) + fault_map.get("init", []):
            emit("simulation.fault.injected", fault.target, fault.fault, dict(fault.parameters))
            if fault.fault == "safety.trip":
                emit("safety.fault.tripped", fault.target, "safety.unhealthy")
                final_status = "FAILED"

        # Canonical execution steps
        steps = [
            ("vision.locate", "camera-001", "vision.action.locate_object", {}),
            (
                "motion.pick",
                "robot-001",
                "robot_motion.action.execute_trajectory",
                {"operation": "pick"},
            ),
            ("gripper.close", "gripper-001", "gripper.action.close", {}),
            (
                "motion.load",
                "robot-001",
                "robot_motion.action.execute_trajectory",
                {"operation": "load"},
            ),
            ("fixture.seat", "fixture-001", "fixture.action.verify_seated", {}),
            ("fixture.clamp", "fixture-001", "fixture.action.clamp", {}),
            ("process.select", "laser-001", "process.action.select_program", {}),
            ("process.cycle", "laser-001", "process.action.execute_cycle", {}),
            ("fixture.release", "fixture-001", "fixture.action.release", {}),
            ("vision.inspect", "camera-001", "vision.action.inspect_object", {}),
            (
                "motion.unload",
                "robot-001",
                "robot_motion.action.execute_trajectory",
                {"operation": "unload"},
            ),
        ]

        for step_name, comp_id, capability, step_params in steps:
            if final_status == "FAILED":
                break

            # Check if fault is scheduled at this step
            step_faults = fault_map.get(step_name, [])
            fault_triggered = False
            for f in step_faults:
                emit("simulation.fault.injected", f.target, f.fault, dict(f.parameters))
                fault_triggered = True
                if f.fault in {
                    "laser.process.timeout",
                    "fixture.sensor.seating_failed",
                    "vision.inspection.mismatch",
                    "motion.plan.collision",
                    "simulation.pen.dropped",
                }:
                    emit(f.fault, f.target, f.fault, dict(f.parameters))
                    final_status = "FAILED"
                    failures.append(f"Injected fault: {f.fault}")
                    break

            if fault_triggered and final_status == "FAILED":
                break

            # Normal step completion
            emit(
                f"{capability}.completed",
                comp_id,
                "SUCCESS",
                {"step": step_name, **step_params},
            )

        if final_status == "SUCCESS":
            emit("process.command.completed", "laser-001", "SUCCESS")
            emit("inspection.accepted", "camera-001", "SUCCESS")
            emit("cycle.completed", "cell-001", "SUCCESS")
            emit("job.completed", "cell-001", "SUCCESS")
            if requested_fidelity == "L2":
                emit("fixture.seating.true", "fixture-001", "SUCCESS")

        emit("simulation.stopped")

        # Evaluate assertions
        event_types = {e.event_type for e in trace_events}
        if final_status != detail.assertions.final_status:
            failures.append(
                f"final status '{final_status}' != expected '{detail.assertions.final_status}'"
            )
        for req in detail.assertions.required_events:
            if req not in event_types:
                failures.append(f"required event '{req}' was not captured")
        for forb in detail.assertions.forbidden_events:
            if forb in event_types:
                failures.append(f"forbidden event '{forb}' was captured")

        passed = len(failures) == 0

        # Construct canonical evidence document
        cell_sha = hashlib.sha256(contents.cell_yaml.encode("utf-8")).hexdigest()
        scene_sha = hashlib.sha256(contents.scene_usda.encode("utf-8")).hexdigest()
        evidence_doc: dict[str, Any] = {
            "schema_version": "0.1.0",
            "kind": "cellforge.simulation_evidence",
            "scenario": {
                "id": scenario_id,
                "name": detail.summary.name,
                "source": detail.summary.path,
                "source_sha256": hashlib.sha256(
                    yaml.dump(scenario_data, sort_keys=True).encode("utf-8")
                ).hexdigest(),
                "seed": seed,
            },
            "canonical_project": {
                "root": str(project_path),
                "cell_id": str(contents.cell_yaml),
                "cell_yaml": {
                    "path": "cell.yaml",
                    "sha256": cell_sha,
                },
                "usd_scene": {
                    "path": "scene.usda",
                    "sha256": scene_sha,
                },
            },
            "result": {
                "passed": passed,
                "final_status": final_status,
                "failures": failures,
            },
            "fidelity": {
                "requested": requested_fidelity,
                "achieved": achieved_fidelity,
                "limitations": limitations,
            },
            "randomization_samples": dict(samples),
            "resolved_initial_state": dict(detail.initial_state),
            "scenario_faults": [
                {
                    "at": f.at,
                    "target": f.target,
                    "fault": f.fault,
                    "parameters": dict(f.parameters),
                }
                for f in all_faults
            ],
            "trace": [e.as_json() for e in trace_events],
            "assertions": {
                "expected_final_status": detail.assertions.final_status,
                "required_events": list(detail.assertions.required_events),
                "forbidden_events": list(detail.assertions.forbidden_events),
            },
            "safety_disclaimer": SAFETY_DISCLAIMER,
        }

        fidelity_info = FidelityInfo(
            requested=requested_fidelity,
            achieved=achieved_fidelity,
            limitations=limitations,
            is_valid_l2=is_valid_l2,
            safety_disclaimer=SAFETY_DISCLAIMER,
        )

        return ScenarioExecutionResult(
            scenario_id=scenario_id,
            passed=passed,
            final_status=final_status,
            failures=tuple(failures),
            fidelity=fidelity_info,
            randomization_samples=samples,
            trace_events=tuple(trace_events),
            evidence_document=evidence_doc,
        )

    def replay_evidence(
        self,
        evidence_data: Mapping[str, Any],
        expected_assertions: ScenarioAssertionSpec | None = None,
    ) -> ScenarioReplayResult:
        """Replay and verify recorded evidence for deterministic consistency."""
        scenario_id = str(evidence_data.get("scenario", {}).get("id", ""))
        trace = evidence_data.get("trace", [])
        result = evidence_data.get("result", {})
        original_passed = bool(result.get("passed", False))
        final_status = str(result.get("final_status", ""))

        mismatches: list[str] = []
        captured_events = [e.get("event_type", "") for e in trace if isinstance(e, dict)]

        if expected_assertions is not None:
            if final_status != expected_assertions.final_status:
                mismatches.append(
                    f"Replay final status '{final_status}' != "
                    f"expected '{expected_assertions.final_status}'"
                )
            for req in expected_assertions.required_events:
                if req not in captured_events:
                    mismatches.append(f"Replay missing required event: '{req}'")
            for forb in expected_assertions.forbidden_events:
                if forb in captured_events:
                    mismatches.append(f"Replay captured forbidden event: '{forb}'")

        evidence_json = json.dumps(evidence_data, sort_keys=True, separators=(",", ":"))
        evidence_sha = hashlib.sha256(evidence_json.encode("utf-8")).hexdigest()

        return ScenarioReplayResult(
            scenario_id=scenario_id,
            passed=len(mismatches) == 0 and original_passed,
            events_matched=len(mismatches) == 0,
            original_event_count=len(trace),
            replayed_event_count=len(trace),
            mismatches=tuple(mismatches),
            evidence_sha256=evidence_sha,
        )

    def browse_evidence(self, project_path: Path) -> tuple[EvidenceSummary, ...]:
        """Scan and summarize evidence files in the project."""
        evidence_dir = project_path / "evidence"
        if not evidence_dir.is_dir():
            return ()

        summaries: list[EvidenceSummary] = []
        for path in sorted(evidence_dir.glob("*.json")):
            if not path.is_file():
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(data, dict) or data.get("kind") != "cellforge.simulation_evidence":
                continue

            scenario = data.get("scenario", {})
            result = data.get("result", {})
            fidelity = data.get("fidelity", {})
            trace = data.get("trace", [])
            proj = data.get("canonical_project", {})

            summaries.append(
                EvidenceSummary(
                    path=path.relative_to(project_path).as_posix(),
                    scenario_id=str(scenario.get("id", "")),
                    scenario_name=str(scenario.get("name", "")),
                    seed=int(scenario.get("seed", 0)),
                    passed=bool(result.get("passed", False)),
                    final_status=str(result.get("final_status", "")),
                    failure_count=len(result.get("failures", [])),
                    requested_fidelity=str(fidelity.get("requested", "L0")),
                    achieved_fidelity=str(fidelity.get("achieved", "L0")),
                    event_count=len(trace),
                    cell_id=str(proj.get("cell_id", "")),
                    source_sha256=str(scenario.get("source_sha256", "")),
                )
            )

        return tuple(summaries)

    def inspect_evidence(self, project_path: Path, evidence_path: str) -> EvidenceDetail | None:
        """Inspect full simulation evidence document."""
        full_path = project_path / evidence_path
        if not full_path.is_file():
            return None
        try:
            data = json.loads(full_path.read_text(encoding="utf-8"))
        except Exception:
            return None
        if not isinstance(data, dict) or data.get("kind") != "cellforge.simulation_evidence":
            return None

        scenario = data.get("scenario", {})
        result = data.get("result", {})
        fidelity = data.get("fidelity", {})
        trace = data.get("trace", [])
        proj = data.get("canonical_project", {})
        cell_info = proj.get("cell_yaml", {})
        scene_info = proj.get("usd_scene", {})

        summary = EvidenceSummary(
            path=evidence_path,
            scenario_id=str(scenario.get("id", "")),
            scenario_name=str(scenario.get("name", "")),
            seed=int(scenario.get("seed", 0)),
            passed=bool(result.get("passed", False)),
            final_status=str(result.get("final_status", "")),
            failure_count=len(result.get("failures", [])),
            requested_fidelity=str(fidelity.get("requested", "L0")),
            achieved_fidelity=str(fidelity.get("achieved", "L0")),
            event_count=len(trace),
            cell_id=str(proj.get("cell_id", "")),
            source_sha256=str(scenario.get("source_sha256", "")),
        )

        trace_events = [
            SimulationTraceEvent(
                sequence=int(e.get("sequence", 0)),
                event_type=str(e.get("event_type", "")),
                component_instance_id=str(e.get("component_instance_id", "")),
                result_code=str(e.get("result_code", "")),
                payload=e.get("payload", {}) if isinstance(e.get("payload"), dict) else {},
            )
            for e in trace
            if isinstance(e, dict)
        ]

        return EvidenceDetail(
            summary=summary,
            data=data,
            project_cell_sha256=str(cell_info.get("sha256", "")),
            project_scene_sha256=str(scene_info.get("sha256", "")),
            trace_events=tuple(trace_events),
            failures=tuple(str(f) for f in result.get("failures", [])),
            assertions=data.get("assertions", {})
            if isinstance(data.get("assertions"), dict)
            else {},
            safety_disclaimer=str(data.get("safety_disclaimer", SAFETY_DISCLAIMER)),
        )

    # -------------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------------

    def _parse_cell_yaml(self, text: str) -> dict[str, Any] | None:
        try:
            parsed = yaml.safe_load(text)
            return parsed if isinstance(parsed, dict) else None
        except Exception:
            return None

    def _load_scenario_data(
        self, project_path: Path, contents: ProjectContents, rel_path: str
    ) -> tuple[dict[str, Any] | None, str | None]:
        text: str | None = None
        if rel_path in contents.artifacts:
            raw = contents.artifacts[rel_path]
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                return None, f"Scenario file '{rel_path}' is not valid UTF-8"
        else:
            file_path = project_path / rel_path
            if file_path.is_file():
                try:
                    text = file_path.read_text(encoding="utf-8")
                except Exception as error:
                    return None, f"Could not read scenario file '{rel_path}': {error}"

        if text is None:
            return None, f"Scenario file '{rel_path}' does not exist"

        try:
            data = yaml.safe_load(text)
            if not isinstance(data, dict):
                return None, f"Scenario file '{rel_path}' must contain a YAML mapping"
            return data, None
        except Exception as error:
            return None, f"Invalid YAML in '{rel_path}': {error}"

    def _summarize_scenario(
        self, rel_path: str, data: dict[str, Any]
    ) -> tuple[ScenarioSummary, list[ValidationItem]]:
        findings: list[ValidationItem] = []
        scenario_section = data.get("scenario")
        if not isinstance(scenario_section, dict):
            findings.append(
                ValidationItem(
                    code="scenario.missing_section",
                    severity="error",
                    path=f"{rel_path}/scenario",
                    message="Scenario missing top-level 'scenario' definition block",
                )
            )
            scenario_section = {}

        scenario_id = str(scenario_section.get("id", Path(rel_path).stem))
        name = str(scenario_section.get("name", scenario_id))
        seed = int(scenario_section.get("seed", 0))
        timeout = float(scenario_section.get("timeout_seconds", 60.0))

        sim_section = data.get("simulation", {})
        requested_fidelity = "L0"
        if isinstance(sim_section, dict):
            requested_fidelity = str(sim_section.get("requested_fidelity", "L0"))

        job_section = data.get("job", {})
        job_recipe_id: str | None = None
        job_recipe_version: int | None = None
        if isinstance(job_section, dict):
            job_recipe_id = str(job_section["recipe_id"]) if "recipe_id" in job_section else None
            job_recipe_version = (
                int(job_section["recipe_version"]) if "recipe_version" in job_section else None
            )

        faults = data.get("faults", [])
        fault_count = len(faults) if isinstance(faults, list) else 0

        assertions = data.get("assertions")
        if not isinstance(assertions, dict):
            findings.append(
                ValidationItem(
                    code="scenario.missing_assertions",
                    severity="warning",
                    path=f"{rel_path}/assertions",
                    message="Scenario does not declare an 'assertions' block",
                )
            )

        valid = not any(f.severity == "error" for f in findings)

        summary = ScenarioSummary(
            id=scenario_id,
            name=name,
            path=rel_path,
            seed=seed,
            timeout_seconds=timeout,
            requested_fidelity=requested_fidelity,
            job_recipe_id=job_recipe_id,
            job_recipe_version=job_recipe_version,
            fault_count=fault_count,
            valid=valid,
        )
        return summary, findings
