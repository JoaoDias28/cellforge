"""In-Kit ROS 2 host for the Isaac simulation backend."""

from __future__ import annotations

import json
from typing import Any


class KitRosSimulationHost:
    """Spin the ROS bridge from Kit's main-thread update stream without blocking UI."""

    def __init__(self) -> None:
        import omni.kit.app
        import rclpy
        from cellforge_simulation.isaac_backend import IsaacSimulationBackend
        from cellforge_simulation.ros_node import SimulationBridgeNode
        from cellforge_simulation.service import SimulationControlService
        from std_msgs.msg import String

        publisher: Any | None = None

        def publish_fault(payload: dict[str, Any]) -> None:
            if publisher is None:
                raise RuntimeError("simulation fault publisher is not initialized")
            message = String()
            message.data = json.dumps(payload, sort_keys=True, separators=(",", ":"))
            publisher.publish(message)

        backend = IsaacSimulationBackend(publish_fault)
        self._rclpy = rclpy
        if not rclpy.ok():
            rclpy.init()
            self._owns_context = True
        else:
            self._owns_context = False
        try:
            self._node = rclpy.create_node("cellforge_isaac_simulation_bridge")
            publisher = self._node.create_publisher(String, "/simulation/fault_injection", 10)
            self._bridge = SimulationBridgeNode(
                self._node,
                SimulationControlService(backend),
            )
        except Exception:
            if self._owns_context and rclpy.ok():
                rclpy.shutdown()
            raise
        stream = omni.kit.app.get_app().get_update_event_stream()
        self._update_subscription = stream.create_subscription_to_pop(
            self._on_update, name="CellForge ROS simulation bridge"
        )

    def _on_update(self, _event: Any) -> None:
        self._rclpy.spin_once(self._node, timeout_sec=0.0)

    def close(self) -> None:
        self._update_subscription = None
        self._node.destroy_node()
        if self._owns_context and self._rclpy.ok():
            self._rclpy.shutdown()


def create_kit_simulation_host() -> tuple[KitRosSimulationHost | None, str]:
    try:
        return KitRosSimulationHost(), ""
    except Exception as error:  # Kit/ROS extension failures must preserve a usable Studio shell.
        return None, (
            "Isaac/ROS simulation host is unavailable. Install the locked ROS 2 Jazzy workspace "
            f"in Isaac Sim 6 and reload the extension: {error}"
        )
