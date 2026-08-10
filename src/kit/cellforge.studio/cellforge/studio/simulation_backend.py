"""ROS 2 client adapter used by Cell Studio's pure simulation application."""

from __future__ import annotations

import json
from typing import Any

from cellforge.studio.simulation_application import (
    SimulationApplication,
    SimulationCommandResult,
)


class RosSimulationClient:
    def __init__(self, timeout_seconds: float = 5.0) -> None:
        import rclpy
        from cellforge_interfaces.srv import (
            ConfigureSimulation,
            ControlSimulation,
            FinalizeSimulation,
            InjectSimulationFault,
        )

        self._rclpy = rclpy
        self._timeout = timeout_seconds
        if not rclpy.ok():
            rclpy.init()
            self._owns_context = True
        else:
            self._owns_context = False
        self._node = rclpy.create_node("cellforge_studio_simulation_client")
        self._configure = self._node.create_client(ConfigureSimulation, "/simulation/configure")
        self._control = self._node.create_client(ControlSimulation, "/simulation/control")
        self._fault = self._node.create_client(InjectSimulationFault, "/simulation/inject_fault")
        self._finalize = self._node.create_client(FinalizeSimulation, "/simulation/finalize")
        self._types = (
            ConfigureSimulation,
            ControlSimulation,
            InjectSimulationFault,
            FinalizeSimulation,
        )

    def _call(self, client: Any, request: Any) -> Any:
        if not client.wait_for_service(timeout_sec=self._timeout):
            raise RuntimeError("simulation.ros.unavailable: simulation bridge service timed out")
        future = client.call_async(request)
        self._rclpy.spin_until_future_complete(self._node, future, timeout_sec=self._timeout)
        response = future.result()
        if response is None:
            raise RuntimeError("simulation.ros.timeout: no response from simulation bridge")
        return response

    @staticmethod
    def _result(response: Any, *, details: dict[str, Any] | None = None) -> SimulationCommandResult:
        return SimulationCommandResult(
            success=bool(response.success),
            code=str(response.result_code),
            message=str(response.result_message),
            state=str(getattr(response, "state", "")),
            details=details,
        )

    def configure(self, project_path: str, scenario_path: str) -> SimulationCommandResult:
        request = self._types[0].Request()
        request.project_path = project_path
        request.scenario_path = scenario_path
        response = self._call(self._configure, request)
        return self._result(
            response,
            details={
                "seed": response.seed,
                "requested_fidelity": response.requested_fidelity,
                "achieved_fidelity": response.achieved_fidelity,
            },
        )

    def control(self, command: str, step_count: int = 1) -> SimulationCommandResult:
        request = self._types[1].Request()
        request.command = command
        request.step_count = step_count
        return self._result(self._call(self._control, request))

    def inject_fault(
        self, at: str, target: str, fault_code: str, parameters_json: str
    ) -> SimulationCommandResult:
        request = self._types[2].Request()
        request.at = at
        request.component_instance_id = target
        request.fault_code = fault_code
        request.parameters_json = parameters_json or "{}"
        return self._result(self._call(self._fault, request))

    def finalize(self, final_status: str, evidence_path: str) -> SimulationCommandResult:
        request = self._types[3].Request()
        request.final_status = final_status
        request.evidence_path = evidence_path
        response = self._call(self._finalize, request)
        return self._result(
            response,
            details={
                "scenario_passed": response.scenario_passed,
                "failures": json.loads(response.failures_json),
            },
        )

    def close(self) -> None:
        self._node.destroy_node()
        if self._owns_context and self._rclpy.ok():
            self._rclpy.shutdown()


def create_simulation_application(unavailable_message: str = "") -> SimulationApplication:
    if unavailable_message:
        return SimulationApplication(None, unavailable_message=unavailable_message)
    try:
        return SimulationApplication(RosSimulationClient())
    except (ImportError, RuntimeError) as error:
        return SimulationApplication(
            None,
            unavailable_message=(
                "ROS 2 Jazzy and generated CellForge simulation interfaces are unavailable: "
                f"{error}"
            ),
        )
