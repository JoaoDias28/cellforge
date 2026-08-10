"""Pure Cell Studio application state for ROS-backed simulation controls."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class SimulationCommandResult:
    success: bool
    code: str
    message: str
    state: str = ""
    details: dict[str, Any] | None = None


class SimulationClient(Protocol):
    def configure(self, project_path: str, scenario_path: str) -> SimulationCommandResult: ...

    def control(self, command: str, step_count: int = 1) -> SimulationCommandResult: ...

    def inject_fault(
        self, at: str, target: str, fault_code: str, parameters_json: str
    ) -> SimulationCommandResult: ...

    def finalize(self, final_status: str, evidence_path: str) -> SimulationCommandResult: ...

    def close(self) -> None: ...


@dataclass(frozen=True, slots=True)
class SimulationSnapshot:
    available: bool
    state: str
    code: str
    detail: str
    evidence_path: str
    safety_disclaimer: str = (
        "Simulation is engineering evidence only. Functional safety remains independently "
        "enforced and validated by rated hardware."
    )


class SimulationApplication:
    """Presentation-neutral command coordinator; widgets contain no simulation rules."""

    def __init__(self, client: SimulationClient | None, unavailable_message: str = "") -> None:
        self._client = client
        self._snapshot = SimulationSnapshot(
            available=client is not None,
            state="UNAVAILABLE" if client is None else "STOPPED",
            code="simulation.backend.unavailable" if client is None else "simulation.ready",
            detail=(
                unavailable_message
                if client is None
                else "ROS 2 simulation client is ready; configure verifies bridge availability."
            ),
            evidence_path="",
        )

    @property
    def snapshot(self) -> SimulationSnapshot:
        return self._snapshot

    def _apply(self, result: SimulationCommandResult, evidence_path: str = "") -> None:
        self._snapshot = SimulationSnapshot(
            available=self._client is not None,
            state=result.state or self._snapshot.state,
            code=result.code,
            detail=result.message,
            evidence_path=evidence_path or self._snapshot.evidence_path,
        )

    def _failure(self, error: RuntimeError) -> None:
        message = str(error)
        code, separator, detail = message.partition(": ")
        self._apply(
            SimulationCommandResult(
                False,
                code if separator else "simulation.command.failed",
                detail if separator else message,
                "FAILED",
            )
        )

    def configure(self, project_path: str, scenario_path: str) -> None:
        if self._client is None:
            return
        try:
            self._apply(self._client.configure(project_path.strip(), scenario_path.strip()))
        except RuntimeError as error:
            self._failure(error)

    def control(self, command: str, step_count: int = 1) -> None:
        if self._client is not None:
            try:
                self._apply(self._client.control(command, step_count))
            except RuntimeError as error:
                self._failure(error)

    def inject_fault(self, at: str, target: str, code: str, parameters_json: str) -> None:
        if self._client is not None:
            try:
                self._apply(self._client.inject_fault(at, target, code, parameters_json))
            except RuntimeError as error:
                self._failure(error)

    def finalize(self, final_status: str, evidence_path: str) -> None:
        if self._client is not None:
            try:
                self._apply(
                    self._client.finalize(final_status.strip(), evidence_path.strip()),
                    evidence_path.strip(),
                )
            except RuntimeError as error:
                self._failure(error)

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None
