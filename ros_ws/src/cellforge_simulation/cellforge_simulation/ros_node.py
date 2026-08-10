"""Thin ROS 2 service edge for the pure simulation application service."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cellforge_simulation.backends import ContractSimulationBackend
from cellforge_simulation.models import (
    AdapterRegistration,
    FaultDefinition,
    load_canonical_project,
    load_scenario,
)
from cellforge_simulation.service import SimulationControlError, SimulationControlService


def _message(error: Exception) -> tuple[str, str]:
    text = str(error)
    code, separator, detail = text.partition(": ")
    return (code if separator else "simulation.command.failed", detail if separator else text)


class SimulationBridgeNode:  # instantiated only after generated ROS imports are available
    def __init__(self, node: Any, service: SimulationControlService) -> None:
        from cellforge_interfaces.msg import JobEvent
        from cellforge_interfaces.srv import (
            ConfigureSimulation,
            ControlSimulation,
            FinalizeSimulation,
            InjectSimulationFault,
            RegisterSimulationAdapter,
        )

        self.node = node
        self.service = service
        self._types = {
            "configure": ConfigureSimulation,
            "control": ControlSimulation,
            "finalize": FinalizeSimulation,
            "fault": InjectSimulationFault,
            "register": RegisterSimulationAdapter,
        }
        node.create_service(ConfigureSimulation, "/simulation/configure", self._configure_callback)
        node.create_service(ControlSimulation, "/simulation/control", self._control_callback)
        node.create_service(
            RegisterSimulationAdapter,
            "/simulation/register_adapter",
            self._register_callback,
        )
        node.create_service(InjectSimulationFault, "/simulation/inject_fault", self._fault_callback)
        node.create_service(FinalizeSimulation, "/simulation/finalize", self._finalize_callback)
        node.create_subscription(JobEvent, "/events/job", self._trace_callback, 100)

    @staticmethod
    def _ok(response: Any, code: str, message: str = "") -> Any:
        response.success = True
        response.result_code = code
        response.result_message = message
        return response

    @staticmethod
    def _error(response: Any, error: Exception) -> Any:
        code, detail = _message(error)
        response.success = False
        response.result_code = code
        response.result_message = detail
        return response

    def _register_callback(self, request: Any, response: Any) -> Any:
        try:
            registration = AdapterRegistration.create(
                request.component_instance_id,
                list(request.capabilities),
                request.fidelity,
                request.endpoint,
                list(request.fault_codes),
            )
            self.service.register_adapter(registration)
            return self._ok(response, "simulation.adapter.registered")
        except (ValueError, SimulationControlError) as error:
            return self._error(response, error)

    def _configure_callback(self, request: Any, response: Any) -> Any:
        try:
            scenario = load_scenario(Path(request.scenario_path))
            project = load_canonical_project(
                Path(request.project_path), Path(request.scenario_path)
            )
            required = project.required_adapter_ids
            self.service.configure(scenario, project=project)
            achieved = min(
                registration.fidelity
                for registration in self.service.registrations
                if registration.component_instance_id in required
            )
            self._ok(response, "simulation.configured")
            response.seed = scenario.seed
            response.requested_fidelity = scenario.requested_fidelity.label()
            response.achieved_fidelity = achieved.label()
            return response
        except (OSError, ValueError, SimulationControlError) as error:
            return self._error(response, error)

    def _control_callback(self, request: Any, response: Any) -> Any:
        try:
            command = request.command.strip().upper()
            if command == "RESET":
                self.service.reset()
            elif command == "START":
                self.service.start()
            elif command == "PAUSE":
                self.service.pause()
            elif command == "STEP":
                self.service.step(int(request.step_count))
            else:
                raise SimulationControlError(
                    f"simulation.control.unsupported: unknown command '{request.command}'"
                )
            self._ok(response, f"simulation.{command.lower()}.completed")
            response.state = self.service.state.value
            return response
        except (ValueError, SimulationControlError) as error:
            response.state = self.service.state.value
            return self._error(response, error)

    def _fault_callback(self, request: Any, response: Any) -> Any:
        try:
            parameters = json.loads(request.parameters_json or "{}")
            if not isinstance(parameters, dict):
                raise ValueError("simulation.fault.parameters_invalid: expected a JSON object")
            fault = FaultDefinition(
                request.at.strip(),
                request.component_instance_id.strip(),
                request.fault_code.strip(),
                parameters,
            )
            self.service.inject_fault(fault)
            return self._ok(response, "simulation.fault.injected")
        except (json.JSONDecodeError, ValueError, SimulationControlError) as error:
            return self._error(response, error)

    def _finalize_callback(self, request: Any, response: Any) -> Any:
        try:
            outcome = self.service.finalize(
                request.final_status.strip(), Path(request.evidence_path)
            )
            self._ok(response, "simulation.evidence.stored")
            response.scenario_passed = outcome.passed
            response.failures_json = json.dumps(list(outcome.failures), sort_keys=True)
            return response
        except (ValueError, SimulationControlError) as error:
            response.scenario_passed = False
            response.failures_json = "[]"
            return self._error(response, error)

    def _trace_callback(self, message: Any) -> None:
        try:
            payload = json.loads(message.payload_json or "{}")
            if not isinstance(payload, dict):
                return
            self.service.capture_event(
                message.event_type,
                component_instance_id=message.component_instance_id,
                result_code=str(payload.get("result_code", "")),
                payload=payload,
            )
            triggers = {message.event_type}
            explicit_trigger = payload.get("scenario_trigger")
            if isinstance(explicit_trigger, str) and explicit_trigger:
                triggers.add(explicit_trigger)
            node = payload.get("node")
            if isinstance(node, str) and node:
                if message.event_type.endswith(".entered"):
                    triggers.add(f"before:{node}")
                if message.event_type.endswith(".completed"):
                    triggers.add(f"after:{node}")
                if message.event_type == "process.command.requested":
                    triggers.add("after:ExecuteProcessStarted")
            for trigger in sorted(triggers):
                self.service.apply_scheduled_faults(trigger)
        except (json.JSONDecodeError, SimulationControlError):
            return


def main(args: list[str] | None = None) -> None:
    import rclpy
    from std_msgs.msg import String

    rclpy.init(args=args)
    node = rclpy.create_node("cellforge_simulation_bridge")
    fault_publisher = node.create_publisher(String, "/simulation/fault_injection", 10)

    def publish_fault(payload: dict[str, Any]) -> None:
        message = String()
        message.data = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        fault_publisher.publish(message)

    backend_name = str(node.declare_parameter("backend", "contract").value)
    if backend_name == "contract":
        backend: Any = ContractSimulationBackend(publish_fault)
    elif backend_name == "isaac":
        from cellforge_simulation.isaac_backend import IsaacSimulationBackend

        backend = IsaacSimulationBackend(publish_fault)
    else:
        node.destroy_node()
        rclpy.shutdown()
        raise RuntimeError(
            f"simulation.backend.unsupported: expected 'contract' or 'isaac', got '{backend_name}'"
        )
    bridge = SimulationBridgeNode(node, SimulationControlService(backend))
    try:
        rclpy.spin(bridge.node)
    finally:
        bridge.node.destroy_node()
        rclpy.shutdown()
