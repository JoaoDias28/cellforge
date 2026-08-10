"""Pure simulation lifecycle, deterministic setup, assertions, and evidence."""

from __future__ import annotations

import json
import os
import random
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol

from cellforge_simulation.models import (
    AdapterRegistration,
    CanonicalProject,
    FaultDefinition,
    FidelityLevel,
    ScenarioDefinition,
    SimulationState,
)

SAFETY_DISCLAIMER = (
    "Simulation status and evidence are standard-control engineering data only. Functional safety "
    "remains independently enforced and validated by rated hardware."
)
FIDELITY_LIMITATIONS = {
    FidelityLevel.L0: (
        "Contract sequencing and deterministic adapter outcomes only; no kinematics, physics, "
        "rendered perception, process quality, hardware, or functional-safety evidence."
    ),
    FidelityLevel.L1: (
        "Kinematics, transforms, collision geometry, and programmed timing only; no validated "
        "physical interaction, process quality, hardware, or functional-safety evidence."
    ),
    FidelityLevel.L2: (
        "Configured Isaac physics, sensors, product movement, timing, and faults only; no physical "
        "process qualification, hardware, or functional-safety evidence."
    ),
    FidelityLevel.L3: (
        "Rendered perception variation and configured inference in addition to L2; no physical "
        "process qualification, hardware, or functional-safety evidence."
    ),
}


class SimulationControlError(RuntimeError):
    """A stable lifecycle, registration, or fidelity failure."""


class EvidenceWriteError(SimulationControlError):
    """Evidence could not be stored durably."""


class SimulationBackend(Protocol):
    """Port implemented by Isaac Sim and deterministic test backends."""

    def reset(self, seed: int, initial_state: dict[str, Any]) -> None: ...

    def play(self) -> None: ...

    def pause(self) -> None: ...

    def step(self, count: int) -> None: ...

    def inject_fault(self, fault: FaultDefinition) -> None: ...


@dataclass(frozen=True, slots=True)
class SimulationTraceEvent:
    sequence: int
    event_type: str
    component_instance_id: str = ""
    result_code: str = ""
    payload: dict[str, Any] | None = None

    def as_json(self) -> dict[str, Any]:
        value = asdict(self)
        value["payload"] = self.payload or {}
        return value


@dataclass(frozen=True, slots=True)
class ScenarioOutcome:
    passed: bool
    failures: tuple[str, ...]
    evidence_path: Path


class SimulationControlService:
    """Own simulation state and deterministic evidence independently of ROS and Kit."""

    def __init__(self, backend: SimulationBackend) -> None:
        self._backend = backend
        self._state = SimulationState.STOPPED
        self._registrations: dict[tuple[str, str], AdapterRegistration] = {}
        self._scenario: ScenarioDefinition | None = None
        self._required_adapter_ids: tuple[str, ...] = ()
        self._project: CanonicalProject | None = None
        self._samples: dict[str, float] = {}
        self._trace: list[SimulationTraceEvent] = []
        self._applied_scheduled_faults: set[int] = set()

    @property
    def state(self) -> SimulationState:
        return self._state

    @property
    def trace(self) -> tuple[SimulationTraceEvent, ...]:
        return tuple(self._trace)

    @property
    def samples(self) -> dict[str, float]:
        return dict(self._samples)

    @property
    def registrations(self) -> tuple[AdapterRegistration, ...]:
        return tuple(self._registrations[key] for key in sorted(self._registrations))

    def _emit(
        self,
        event_type: str,
        *,
        component_instance_id: str = "",
        result_code: str = "",
        payload: dict[str, Any] | None = None,
    ) -> None:
        self._trace.append(
            SimulationTraceEvent(
                sequence=len(self._trace) + 1,
                event_type=event_type,
                component_instance_id=component_instance_id,
                result_code=result_code,
                payload=payload,
            )
        )

    def register_adapter(self, registration: AdapterRegistration) -> None:
        key = (registration.component_instance_id, registration.endpoint)
        existing = self._registrations.get(key)
        if existing is not None and existing != registration:
            raise SimulationControlError(
                "simulation.adapter.conflict: component instance already has a different adapter"
            )
        self._registrations[key] = registration

    def configure(self, scenario: ScenarioDefinition, *, project: CanonicalProject) -> None:
        if self._state is SimulationState.RUNNING:
            raise SimulationControlError(
                "simulation.configure.running: pause before reconfiguration"
            )
        required = project.required_adapter_ids
        if not required:
            raise SimulationControlError(
                "simulation.adapters.required: no required adapters declared"
            )
        registered_ids = {
            registration.component_instance_id for registration in self._registrations.values()
        }
        missing = [item for item in required if item not in registered_ids]
        if missing:
            raise SimulationControlError(
                f"simulation.adapters.missing: no registered adapter for {', '.join(missing)}"
            )
        unknown_fault_targets = sorted(
            {
                fault.target
                for fault in scenario.faults
                if fault.target not in required and fault.target != "operator"
            }
        )
        if unknown_fault_targets:
            raise SimulationControlError(
                "simulation.fault.target_unknown: fault targets are not required cell instances: "
                + ", ".join(unknown_fault_targets)
            )
        unsupported_faults = sorted(
            {
                f"{fault.target}:{fault.fault}"
                for fault in scenario.faults
                if fault.target != "operator"
                and not any(
                    registration.component_instance_id == fault.target
                    and fault.fault in registration.fault_codes
                    for registration in self._registrations.values()
                )
            }
        )
        if unsupported_faults:
            raise SimulationControlError(
                "simulation.fault.unsupported: adapters do not declare "
                + ", ".join(unsupported_faults)
            )
        achieved = min(
            registration.fidelity
            for registration in self._registrations.values()
            if registration.component_instance_id in required
        )
        if achieved < scenario.requested_fidelity:
            raise SimulationControlError(
                "simulation.fidelity.unsupported: requested "
                f"{scenario.requested_fidelity.label()} but weakest required adapter supports "
                f"{achieved.label()}"
            )
        self._scenario = scenario
        self._project = project
        self._required_adapter_ids = required
        self._samples = {}
        self._trace = []
        self._applied_scheduled_faults = set()
        self._state = SimulationState.CONFIGURED
        self._emit(
            "simulation.configured",
            payload={
                "scenario_id": scenario.scenario_id,
                "seed": scenario.seed,
                "requested_fidelity": scenario.requested_fidelity.label(),
                "achieved_fidelity": achieved.label(),
            },
        )

    def reset(self) -> dict[str, float]:
        scenario = self._require_scenario()
        if self._project is None:
            raise SimulationControlError(
                "simulation.project.missing: canonical project is unavailable"
            )
        if self._state is SimulationState.RUNNING:
            self._backend.pause()
        generator = random.Random(scenario.seed)
        self._samples = {
            key: generator.uniform(distribution.minimum, distribution.maximum)
            for key, distribution in sorted(scenario.randomization.items())
        }
        setup = dict(scenario.initial_state)
        setup["randomization"] = dict(self._samples)
        self._backend.reset(scenario.seed, setup)
        self._trace = []
        self._applied_scheduled_faults = set()
        self._state = SimulationState.PAUSED
        self._emit(
            "simulation.reset",
            payload={
                "seed": scenario.seed,
                "samples": dict(self._samples),
            },
        )
        return dict(self._samples)

    def start(self) -> None:
        self._require_state(SimulationState.PAUSED, "start")
        self._backend.play()
        self._state = SimulationState.RUNNING
        self._emit("simulation.started")

    def pause(self) -> None:
        self._require_state(SimulationState.RUNNING, "pause")
        self._backend.pause()
        self._state = SimulationState.PAUSED
        self._emit("simulation.paused")

    def step(self, count: int = 1) -> None:
        self._require_state(SimulationState.PAUSED, "step")
        if isinstance(count, bool) or not isinstance(count, int) or count < 1 or count > 10000:
            raise SimulationControlError("simulation.step.invalid: count must be in [1, 10000]")
        self._backend.step(count)
        self._emit("simulation.stepped", payload={"count": count})

    def inject_fault(self, fault: FaultDefinition) -> None:
        if self._state not in {SimulationState.PAUSED, SimulationState.RUNNING}:
            raise SimulationControlError(
                "simulation.fault.invalid_state: reset before injecting a fault"
            )
        if fault.target != "operator" and fault.target not in self._required_adapter_ids:
            raise SimulationControlError(
                f"simulation.fault.target_unknown: '{fault.target}' is not a required adapter"
            )
        if not fault.at.strip() or not fault.fault.strip():
            raise SimulationControlError(
                "simulation.fault.invalid: schedule point and fault code must be non-blank"
            )
        if fault.target != "operator" and not any(
            registration.component_instance_id == fault.target
            and fault.fault in registration.fault_codes
            for registration in self._registrations.values()
        ):
            raise SimulationControlError(
                f"simulation.fault.unsupported: adapter '{fault.target}' does not declare "
                f"'{fault.fault}'"
            )
        self._backend.inject_fault(fault)
        self._emit(
            "simulation.fault.injected",
            component_instance_id=fault.target,
            result_code=fault.fault,
            payload={"at": fault.at, "parameters": fault.parameters},
        )

    def apply_scheduled_faults(self, trigger: str) -> int:
        """Inject every unapplied scenario fault scheduled for an exact trigger."""

        scenario = self._require_scenario()
        applied = 0
        for index, fault in enumerate(scenario.faults):
            if index in self._applied_scheduled_faults or fault.at != trigger:
                continue
            self.inject_fault(fault)
            self._applied_scheduled_faults.add(index)
            applied += 1
        return applied

    def capture_event(
        self,
        event_type: str,
        *,
        component_instance_id: str = "",
        result_code: str = "",
        payload: dict[str, Any] | None = None,
    ) -> None:
        if self._state not in {SimulationState.PAUSED, SimulationState.RUNNING}:
            raise SimulationControlError(
                "simulation.trace.invalid_state: reset before trace capture"
            )
        if not event_type.strip():
            raise SimulationControlError("simulation.trace.invalid_event: event type is blank")
        self._emit(
            event_type.strip(),
            component_instance_id=component_instance_id,
            result_code=result_code,
            payload=payload,
        )

    def finalize(self, final_status: str, evidence_path: Path) -> ScenarioOutcome:
        scenario = self._require_scenario()
        project = self._project
        if project is None:
            raise SimulationControlError(
                "simulation.project.missing: canonical project is unavailable"
            )
        if self._state is SimulationState.RUNNING:
            self._backend.pause()
        if self._state not in {SimulationState.RUNNING, SimulationState.PAUSED}:
            raise SimulationControlError(
                "simulation.finalize.invalid_state: reset and run before finalizing"
            )
        events = [event.event_type for event in self._trace]
        failures: list[str] = []
        if final_status != scenario.assertions.final_status:
            failures.append(
                f"final status '{final_status}' != expected '{scenario.assertions.final_status}'"
            )
        for required in scenario.assertions.required_events:
            if required not in events:
                failures.append(f"required event '{required}' was not captured")
        for forbidden in scenario.assertions.forbidden_events:
            if forbidden in events:
                failures.append(f"forbidden event '{forbidden}' was captured")
        passed = not failures
        self._state = SimulationState.COMPLETED if passed else SimulationState.FAILED
        achieved = min(
            registration.fidelity
            for registration in self._registrations.values()
            if registration.component_instance_id in self._required_adapter_ids
        )
        report = {
            "schema_version": "0.1.0",
            "kind": "cellforge.simulation_evidence",
            "scenario": {
                "id": scenario.scenario_id,
                "name": scenario.name,
                "source": scenario.source,
                "source_sha256": scenario.source_sha256,
                "seed": scenario.seed,
            },
            "canonical_project": {
                "root": project.root,
                "cell_id": project.cell_id,
                "cell_yaml": {
                    "path": project.cell_path,
                    "sha256": project.cell_sha256,
                },
                "usd_scene": {
                    "path": project.scene_path,
                    "sha256": project.scene_sha256,
                },
            },
            "result": {
                "passed": passed,
                "final_status": final_status,
                "failures": failures,
            },
            "fidelity": {
                "requested": scenario.requested_fidelity.label(),
                "achieved": achieved.label(),
                "limitations": FIDELITY_LIMITATIONS[achieved],
            },
            "randomization_samples": dict(self._samples),
            "resolved_initial_state": scenario.initial_state,
            "scenario_faults": [
                {
                    "at": fault.at,
                    "target": fault.target,
                    "fault": fault.fault,
                    "parameters": fault.parameters,
                }
                for fault in scenario.faults
            ],
            "required_adapters": [
                {
                    "component_instance_id": registration.component_instance_id,
                    "capabilities": list(registration.capabilities),
                    "fidelity": registration.fidelity.label(),
                    "endpoint": registration.endpoint,
                    "fault_codes": list(registration.fault_codes),
                }
                for registration in self.registrations
                if registration.component_instance_id in self._required_adapter_ids
            ],
            "assertions": {
                "expected_final_status": scenario.assertions.final_status,
                "required_events": list(scenario.assertions.required_events),
                "forbidden_events": list(scenario.assertions.forbidden_events),
            },
            "trace": [event.as_json() for event in self._trace],
            "safety_boundary": SAFETY_DISCLAIMER,
        }
        try:
            _atomic_write_json(evidence_path, report)
        except OSError as error:
            self._state = SimulationState.FAILED
            raise EvidenceWriteError(
                f"simulation.evidence.write_failed: cannot store {evidence_path}: {error}"
            ) from error
        return ScenarioOutcome(passed, tuple(failures), evidence_path)

    def _require_scenario(self) -> ScenarioDefinition:
        if self._scenario is None:
            raise SimulationControlError("simulation.not_configured: configure a scenario first")
        return self._scenario

    def _require_state(self, expected: SimulationState, command: str) -> None:
        self._require_scenario()
        if self._state is not expected:
            raise SimulationControlError(
                f"simulation.{command}.invalid_state: expected {expected.value}, "
                f"got {self._state.value}"
            )


def _atomic_write_json(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
