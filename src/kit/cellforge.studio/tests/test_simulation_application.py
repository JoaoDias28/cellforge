from __future__ import annotations

from typing import Any

from cellforge.studio.simulation_application import (
    SimulationApplication,
    SimulationCommandResult,
)


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []
        self.closed = False

    def configure(self, project_path: str, scenario_path: str) -> SimulationCommandResult:
        self.calls.append(("configure", (project_path, scenario_path)))
        return SimulationCommandResult(True, "simulation.configured", "configured", "CONFIGURED")

    def control(self, command: str, step_count: int = 1) -> SimulationCommandResult:
        self.calls.append(("control", (command, step_count)))
        state = "RUNNING" if command == "START" else "PAUSED"
        return SimulationCommandResult(True, f"simulation.{command.lower()}", "ok", state)

    def inject_fault(
        self, at: str, target: str, fault_code: str, parameters_json: str
    ) -> SimulationCommandResult:
        self.calls.append(("fault", (at, target, fault_code, parameters_json)))
        return SimulationCommandResult(True, "simulation.fault.injected", "injected", "PAUSED")

    def finalize(self, final_status: str, evidence_path: str) -> SimulationCommandResult:
        self.calls.append(("finalize", (final_status, evidence_path)))
        return SimulationCommandResult(True, "simulation.evidence.stored", "stored", "COMPLETED")

    def close(self) -> None:
        self.closed = True


def test_simulation_application_delegates_every_command_to_the_client() -> None:
    client = FakeClient()
    application = SimulationApplication(client)
    application.configure("project", "scenario.yaml")
    application.control("RESET")
    application.control("STEP", 4)
    application.control("START")
    application.inject_fault("now", "laser-001", "laser.process.timeout", "{}")
    application.finalize("SUCCESS", "evidence.json")

    assert client.calls[0] == (
        "configure",
        ("project", "scenario.yaml"),
    )
    assert application.snapshot.state == "COMPLETED"
    assert application.snapshot.evidence_path == "evidence.json"
    assert "rated hardware" in application.snapshot.safety_disclaimer


def test_simulation_application_has_honest_unavailable_state() -> None:
    application = SimulationApplication(None, "ROS bridge missing")
    application.control("START")
    assert application.snapshot.available is False
    assert application.snapshot.state == "UNAVAILABLE"
    assert application.snapshot.detail == "ROS bridge missing"


def test_close_releases_client() -> None:
    client = FakeClient()
    application = SimulationApplication(client)
    application.close()
    assert client.closed is True
