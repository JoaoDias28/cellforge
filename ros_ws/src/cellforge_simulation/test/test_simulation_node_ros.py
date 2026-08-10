"""Jazzy smoke test for Task 018 generated services and bridge mapping."""

from __future__ import annotations

import json
from pathlib import Path

import rclpy
from cellforge_interfaces.msg import JobEvent
from cellforge_interfaces.srv import (
    ConfigureSimulation,
    ControlSimulation,
    FinalizeSimulation,
    RegisterSimulationAdapter,
)
from cellforge_simulation.backends import ContractSimulationBackend
from cellforge_simulation.ros_node import SimulationBridgeNode
from cellforge_simulation.service import SimulationControlService


def test_bridge_maps_generated_ros_services_to_pure_control(tmp_path: Path) -> None:
    project = tmp_path / "project"
    scenario = project / "scenarios" / "nominal.yaml"
    scenario.parent.mkdir(parents=True)
    (project / "scene.usda").write_text('#usda 1.0\ndef Xform "World" {}\n', encoding="utf-8")
    (project / "cell.yaml").write_text(
        """schema_version: 0.1.0
cell: {id: ros-smoke}
scene: {usd: scene.usda, root_prim: /World}
components:
  - id: robot-001
    config: {}
scenarios: [scenarios/nominal.yaml]
""",
        encoding="utf-8",
    )
    scenario.write_text(
        """schema_version: 0.1.0
scenario: {id: ros-smoke, name: ROS smoke, seed: 18}
simulation: {requested_fidelity: L0}
job: {}
initial_state: {}
faults: []
assertions:
  final_status: SUCCESS
  required_events: [job.completed]
  forbidden_events: [safety.bypass]
""",
        encoding="utf-8",
    )

    rclpy.init()
    node = rclpy.create_node("task_018_simulation_bridge_test")
    bridge = SimulationBridgeNode(node, SimulationControlService(ContractSimulationBackend()))
    try:
        register = RegisterSimulationAdapter.Request(
            component_instance_id="robot-001",
            capabilities=["robot_motion.execute_trajectory"],
            fidelity="L0",
            endpoint="/device/robot-001/execute",
            fault_codes=[],
        )
        register_response = bridge._register_callback(
            register, RegisterSimulationAdapter.Response()
        )
        assert register_response.success

        configure = ConfigureSimulation.Request(
            project_path=str(project), scenario_path=str(scenario)
        )
        configure_response = bridge._configure_callback(configure, ConfigureSimulation.Response())
        assert configure_response.success
        assert configure_response.seed == 18

        reset_response = bridge._control_callback(
            ControlSimulation.Request(command="RESET", step_count=1),
            ControlSimulation.Response(),
        )
        assert reset_response.state == "PAUSED"
        bridge._control_callback(
            ControlSimulation.Request(command="START", step_count=1),
            ControlSimulation.Response(),
        )
        event = JobEvent(event_type="job.completed", payload_json="{}")
        bridge._trace_callback(event)

        evidence = tmp_path / "evidence.json"
        finalize_response = bridge._finalize_callback(
            FinalizeSimulation.Request(final_status="SUCCESS", evidence_path=str(evidence)),
            FinalizeSimulation.Response(),
        )
        assert finalize_response.success
        assert finalize_response.scenario_passed
        assert json.loads(evidence.read_text(encoding="utf-8"))["result"]["passed"]
    finally:
        node.destroy_node()
        rclpy.shutdown()
