"""Genuine Isaac Sim 6 ROS capability adapters for the reference L2 cell."""

from __future__ import annotations

import asyncio
import json
import os
import threading
from pathlib import Path
from typing import Any

import rclpy
from cellforge_interfaces.action import ExecuteProcess, ExecuteSkill, InspectObject, LocateObject
from cellforge_interfaces.msg import DeviceState as RosDeviceState
from cellforge_interfaces.msg import PoseEstimate
from cellforge_interfaces.msg import SafetyState as RosSafetyState
from cellforge_interfaces.srv import RegisterSimulationAdapter
from geometry_msgs.msg import PoseStamped
from rclpy.action import ActionServer, CancelResponse, GoalResponse
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import ShutdownException, SingleThreadedExecutor
from rclpy.node import Node
from sensor_msgs.msg import JointState  # type: ignore[import-not-found]
from std_msgs.msg import String

from cellforge_simulation.l2_runtime import IsaacL2Runtime, L2Event, L2Outcome
from cellforge_simulation.pen_physics_backend import IsaacPenPhysicsBackend
from cellforge_simulation.physical import DEFAULT_BOUNDS, sample_pen_pose

_ACTION_TYPES: dict[str, Any] = {
    "vision.action.locate_object": LocateObject,
    "vision.action.inspect_object": InspectObject,
    "process.action.execute_cycle": ExecuteProcess,
}
_COMPONENT_CAPABILITIES = {
    "camera-001": ("vision.action.inspect_object", "vision.action.locate_object"),
    "fixture-001": (
        "fixture.action.clamp",
        "fixture.action.release",
        "fixture.action.verify_seated",
    ),
    "gripper-001": ("gripper.action.close", "gripper.action.open"),
    "laser-001": ("process.action.execute_cycle", "process.action.select_program"),
    "robot-001": ("robot_motion.action.execute_trajectory",),
}
_FAULT_CODES = {
    "camera-001": (
        "inspection.rejected",
        "vision.object.not_found",
        "vision.pose.correction_limit",
    ),
    "fixture-001": ("fixture.sensor.seating_failed",),
    "gripper-001": ("gripper.grasp.failed", "simulation.pen.dropped"),
    "laser-001": (
        "laser.process.interlock_not_ready",
        "laser.process.outcome_unknown",
        "laser.process.timeout",
    ),
    "robot-001": ("motion.plan.collision", "motion.execution.failed"),
}


def _spin_kit_executor(executor: SingleThreadedExecutor, stop_event: threading.Event) -> None:
    """Drive rclpy callbacks from a worker loop with a running asyncio context.

    Isaac Sim owns the main asyncio loop.  Calling the rclpy global executor from that
    loop stalls the Kit coroutine on Windows, while action callbacks also need a running
    asyncio loop.  A zero-timeout executor tick on a dedicated loop satisfies both
    constraints without making callbacks depend on the global rclpy executor.
    """

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    def tick() -> None:
        if stop_event.is_set() or not rclpy.ok():
            loop.stop()
            return
        try:
            executor.spin_once(timeout_sec=0.0)
        except ShutdownException:
            if not stop_event.is_set():
                raise
            loop.stop()
            return
        loop.call_soon(tick)

    loop.call_soon(tick)
    try:
        loop.run_forever()
    finally:
        loop.close()


class IsaacL2AdapterNode(Node):  # type: ignore[misc]
    """One Kit-hosted node exposing every canonical simulated device capability."""

    def __init__(
        self,
        backend: IsaacPenPhysicsBackend,
        scenario: dict[str, Any],
        *,
        report_path: Path | None = None,
        runtime_loop: asyncio.AbstractEventLoop | None = None,
    ) -> None:
        super().__init__("isaac_l2_adapter")
        self._backend = backend
        self._report_path = report_path
        self._runtime_loop = runtime_loop
        self._runtime_thread_id = threading.get_ident()
        self._events_publisher = self.create_publisher(String, "/simulation/l2/events", 100)
        self._state_publishers = {
            component: self.create_publisher(
                RosDeviceState, f"/device/{component.replace('-', '_')}/state", 10
            )
            for component in (*_COMPONENT_CAPABILITIES, "safety-status-001")
        }
        self._safety_publisher = self.create_publisher(RosSafetyState, "/safety/state", 10)
        self._joint_state_publisher = self.create_publisher(JointState, "/joint_states", 10)
        self._runtime = IsaacL2Runtime(backend, scenario, event_sink=self._publish_event)
        self._completed_runs: list[dict[str, Any]] = []
        self._action_servers: list[Any] = []
        group = ReentrantCallbackGroup()
        for component, capabilities in _COMPONENT_CAPABILITIES.items():
            for capability in capabilities:
                action_type = _ACTION_TYPES.get(capability, ExecuteSkill)
                endpoint = capability.split(".")[-1]
                root = f"/device/{component.replace('-', '_')}"
                self._action_servers.append(
                    ActionServer(
                        self,
                        action_type,
                        f"{root}/{endpoint}",
                        execute_callback=lambda handle, selected=capability: self._execute(
                            selected, handle
                        ),
                        goal_callback=lambda goal, selected=capability: self._accept_goal(
                            selected, goal
                        ),
                        cancel_callback=lambda _handle: CancelResponse.ACCEPT,
                        callback_group=group,
                    )
                )
        self.create_subscription(
            String, "/simulation/l2/configure", self._configure, 10, callback_group=group
        )
        self.create_timer(0.25, self._publish_states)
        self._registration = self.create_client(
            RegisterSimulationAdapter, "/simulation/register_adapter", callback_group=group
        )
        self._registered: set[str] = set()
        self.create_timer(0.5, self._register)
        self.get_logger().info(
            f"Isaac Sim L2 adapters are READY for scenario '{self._runtime.scenario_id}'."
        )

    def _accept_goal(self, capability: str, goal: Any) -> GoalResponse:
        command_id = str(getattr(goal, "command_id", ""))
        timeout = getattr(goal, "timeout", None)
        if not command_id or timeout is None or _duration_seconds(timeout) <= 0:
            self.get_logger().warning(
                f"Rejected {capability} goal: command_id/timeout invalid "
                f"(command_id={command_id!r}, timeout={timeout!r})."
            )
            return GoalResponse.REJECT
        if hasattr(goal, "skill_id") and goal.skill_id != capability:
            self.get_logger().warning(
                f"Rejected {capability} goal: skill_id={goal.skill_id!r} does not match."
            )
            return GoalResponse.REJECT
        return GoalResponse.ACCEPT

    def _execute(self, capability: str, goal_handle: Any) -> Any:
        goal = goal_handle.request
        if goal_handle.is_cancel_requested:
            goal_handle.canceled()
            return self._action_result(
                capability,
                L2Outcome(False, "sdk.command.cancelled", "Command cancelled.", {}),
            )
        feedback = _ACTION_TYPES.get(capability, ExecuteSkill).Feedback()
        if hasattr(feedback, "phase"):
            feedback.phase = "OBSERVING_PHYSX"
        if hasattr(feedback, "progress"):
            feedback.progress = 0.25
        if hasattr(feedback, "message"):
            feedback.message = "Isaac adapter is applying the command."
        goal_handle.publish_feedback(feedback)
        self.get_logger().info(f"Executing {capability} goal '{goal.command_id}'.")
        try:
            payload = self._payload(capability, goal)

            def execute_runtime() -> L2Outcome:
                return self._runtime.execute(capability, payload, command_id=str(goal.command_id))

            outcome = self._run_on_kit(
                execute_runtime, timeout=max(1.0, _duration_seconds(goal.timeout) + 5.0)
            )
        except Exception as error:
            self.get_logger().error(f"L2 {capability} goal failed in adapter: {error}")
            goal_handle.abort()
            return self._action_result(
                capability,
                L2Outcome(False, "simulation.adapter.exception", str(error), {}),
            )
        if goal_handle.is_cancel_requested:
            goal_handle.canceled()
            outcome = L2Outcome(False, "sdk.command.cancelled", "Command cancelled.", {})
        elif outcome.success:
            goal_handle.succeed()
        else:
            goal_handle.abort()
        return self._action_result(capability, outcome)

    def _payload(self, capability: str, goal: Any) -> dict[str, Any]:
        if "locate_object" in capability:
            return {"object_type": goal.object_type, "profile_id": goal.profile_id}
        if "inspect_object" in capability:
            return {
                "inspection_profile": goal.inspection_profile,
                "expected": _json_object(goal.expected_json),
            }
        if "execute_cycle" in capability:
            variable = _json_object(goal.variable_data_json)
            return {
                "program_id": goal.program_id,
                "variable_data": variable,
                "engraving_text": str(variable.get("engraving_text", "")),
                "recipe_id": goal.recipe_id,
                "recipe_version": int(goal.recipe_version),
            }
        return _json_object(goal.input_payload_json)

    def _action_result(self, capability: str, outcome: L2Outcome) -> Any:
        if "locate_object" in capability:
            result = LocateObject.Result()
            result.estimates = [
                _pose_estimate(item) for item in outcome.output.get("estimates", [])
            ]
        elif "inspect_object" in capability:
            result = InspectObject.Result()
            result.accepted = bool(outcome.output.get("accepted", False))
            result.measurements_json = json.dumps(
                outcome.output.get("measurements", {}), sort_keys=True
            )
            result.evidence_uri = str(outcome.output.get("evidence_uri", ""))
        elif "execute_cycle" in capability:
            result = ExecuteProcess.Result()
            result.process_data_json = json.dumps(outcome.output, sort_keys=True)
            result.outcome_certain = outcome.outcome_certain
        else:
            result = ExecuteSkill.Result()
            result.output_payload_json = json.dumps(outcome.output, sort_keys=True)
        result.success = outcome.success
        result.result_code = outcome.result_code
        result.result_message = outcome.result_message
        return result

    def _configure(self, message: String) -> None:
        try:
            scenario = json.loads(message.data)
            if not isinstance(scenario, dict):
                raise ValueError("scenario must be a JSON object")
            scenario_id = str(scenario.get("scenario", {}).get("id", ""))
            if scenario_id == self._runtime.scenario_id:
                self._run_on_kit(self._runtime.publish_configuration_event)
                return

            def apply_configuration() -> None:
                if self._runtime.events:
                    self._completed_runs.append(
                        {
                            **self._runtime.evidence_metadata(),
                            "events": [event.as_json() for event in self._runtime.events],
                        }
                    )
                self._backend.reset_runtime_products()
                self._runtime = IsaacL2Runtime(
                    self._backend, scenario, event_sink=self._publish_event
                )

            self._run_on_kit(apply_configuration)
            self.get_logger().info(f"Configured L2 scenario '{self._runtime.scenario_id}'.")
        except (ValueError, TypeError) as error:
            self.get_logger().error(f"Rejected L2 scenario configuration: {error}")

    def _run_on_kit(self, callback: Any, *, timeout: float = 65.0) -> Any:
        if self._runtime_loop is None or threading.get_ident() == self._runtime_thread_id:
            return callback()

        async def invoke() -> Any:
            return callback()

        future = asyncio.run_coroutine_threadsafe(invoke(), self._runtime_loop)
        return future.result(timeout=timeout)

    def _publish_event(self, event: L2Event) -> None:
        message = String()
        message.data = json.dumps(event.as_json(), sort_keys=True, separators=(",", ":"))
        self._events_publisher.publish(message)

    def _publish_states(self) -> None:
        stamp = self.get_clock().now().to_msg()
        joints = JointState()
        joints.header.stamp = stamp
        joints.name = [f"joint_{index}" for index in range(1, 7)]
        joints.position = [0.0] * 6
        self._joint_state_publisher.publish(joints)
        for component, publisher in self._state_publishers.items():
            message = RosDeviceState()
            message.header.stamp = stamp
            message.component_instance_id = component
            message.state = "READY"
            message.ready = True
            message.details_json = json.dumps(
                {
                    "source": "Isaac Sim 6 OpenUSD/PhysX L2 adapter",
                    "scenario_id": self._runtime.scenario_id,
                    "safety_claim": "none",
                },
                sort_keys=True,
            )
            publisher.publish(message)
        safety = RosSafetyState()
        safety.header.stamp = stamp
        safety.healthy = self._runtime.safety_healthy
        safety.emergency_stop_ok = self._runtime.safety_healthy
        safety.guards_ok = self._runtime.safety_healthy
        safety.process_interlocks_ok = self._runtime.safety_healthy
        safety.reset_required = not self._runtime.safety_healthy
        safety.details_json = json.dumps(
            {
                "source": "Isaac Sim modeled read-only safety status",
                "safety_claim": "none; independent rated hardware remains authoritative",
            },
            sort_keys=True,
        )
        self._safety_publisher.publish(safety)

    def _register(self) -> None:
        if not self._registration.service_is_ready():
            return
        for component, capabilities in _COMPONENT_CAPABILITIES.items():
            if component in self._registered:
                continue
            request = RegisterSimulationAdapter.Request()
            request.component_instance_id = component
            request.capabilities = list(capabilities)
            request.fidelity = "L2"
            request.endpoint = f"/device/{component.replace('-', '_')}"
            request.fault_codes = list(_FAULT_CODES[component])
            future = self._registration.call_async(request)
            future.add_done_callback(
                lambda completed, selected=component: self._registration_done(selected, completed)
            )
            return

    def _registration_done(self, component: str, future: Any) -> None:
        try:
            response = future.result()
        except Exception as error:
            self.get_logger().warning(f"L2 registration for {component} failed: {error}")
            return
        if response.success:
            self._registered.add(component)
        else:
            self.get_logger().warning(
                f"L2 registration for {component} was refused: {response.result_code}"
            )

    def write_report(self) -> None:
        if self._report_path is None:
            return
        runs = [
            *self._completed_runs,
            {
                **self._runtime.evidence_metadata(),
                "events": [event.as_json() for event in self._runtime.events],
            },
        ]
        report = {
            "schema_version": "0.1.0",
            "kind": "cellforge.isaac_l2_adapter_evidence",
            "runs": runs,
        }
        self._report_path.parent.mkdir(parents=True, exist_ok=True)
        self._report_path.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )


def _json_object(raw: str) -> dict[str, Any]:
    if not raw.strip():
        return {}
    value = json.loads(raw)
    return value if isinstance(value, dict) else {}


def _duration_seconds(duration: Any) -> float:
    return float(duration.sec) + float(duration.nanosec) / 1_000_000_000.0


def _pose_estimate(data: dict[str, Any]) -> PoseEstimate:
    result = PoseEstimate()
    pose = PoseStamped()
    pose.header.frame_id = str(data.get("source_frame", "world"))
    values = data.get("pose", {})
    pose.pose.position.x = float(values.get("x", 0.0))
    pose.pose.position.y = float(values.get("y", 0.0))
    pose.pose.position.z = float(values.get("z", 0.0))
    pose.pose.orientation.x = float(values.get("qx", 0.0))
    pose.pose.orientation.y = float(values.get("qy", 0.0))
    pose.pose.orientation.z = float(values.get("qz", 0.0))
    pose.pose.orientation.w = float(values.get("qw", 1.0))
    result.pose = pose
    result.confidence = float(data.get("confidence", 0.0))
    result.object_id = str(data.get("object_id", ""))
    result.source_frame = str(data.get("source_frame", "world"))
    result.covariance_json = "[]"
    result.metadata_json = json.dumps(data.get("metadata", {}), sort_keys=True)
    return result


def _load_scenario(path: Path) -> dict[str, Any]:
    import yaml

    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"L2 scenario '{path}' must contain an object")
    return value


def _acceptance_scenarios(root: Path | None, initial: dict[str, Any]) -> list[dict[str, Any]]:
    documents = [initial]
    if root is None:
        return documents
    for directory in (root / "scenarios", root / "physical" / "scenarios"):
        for path in sorted(directory.glob("*.yaml")):
            candidate = _load_scenario(path)
            if candidate not in documents:
                documents.append(candidate)
    return documents


def main() -> None:
    """Start Isaac Sim headless, then serve ROS actions from its live stage."""

    from isaacsim import SimulationApp

    scene_path = Path(os.environ["CELLFORGE_L2_SCENE"]).resolve()
    scenario_raw = os.environ.get("CELLFORGE_L2_SCENARIO", "")
    scenario_root_raw = os.environ.get("CELLFORGE_L2_SCENARIO_ROOT", "")
    report_raw = os.environ.get("CELLFORGE_L2_REPORT", "")
    initial_scenario = (
        _load_scenario(Path(scenario_raw).resolve())
        if scenario_raw
        else json.loads(os.environ["CELLFORGE_L2_SCENARIO_JSON"])
    )
    scenario_documents = _acceptance_scenarios(
        Path(scenario_root_raw).resolve() if scenario_root_raw else None,
        initial_scenario,
    )
    app = SimulationApp({"headless": True})
    node: IsaacL2AdapterNode | None = None
    try:
        import omni.usd
        from isaacsim.core.api import World

        if not omni.usd.get_context().open_stage(str(scene_path)):
            raise RuntimeError(f"Isaac could not open canonical scene '{scene_path}'")
        stage = omni.usd.get_context().get_stage()
        stage_builder = IsaacPenPhysicsBackend(stage)
        for document in scenario_documents:
            seed = int(document["scenario"]["seed"])
            if bool(document.get("initial_state", {}).get("product_present", True)):
                stage_builder.spawn_pen(f"pen-{seed:08d}", sample_pen_pose(seed, DEFAULT_BOUNDS))
        world = World()
        world.reset()
        backend = IsaacPenPhysicsBackend(stage, world)
        rclpy.init()
        node = IsaacL2AdapterNode(
            backend,
            initial_scenario,
            report_path=Path(report_raw).resolve() if report_raw else None,
        )
        while app.is_running() and rclpy.ok():
            rclpy.spin_once(node, timeout_sec=0.01)
            app.update()
    finally:
        if node is not None:
            node.write_report()
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
        app.close()


async def run_in_existing_kit() -> None:
    """Serve the L2 ROS adapter inside a Kit process that already owns the app loop."""

    import omni.kit.app
    import omni.usd
    from isaacsim.core.api import World

    scene_path = Path(os.environ["CELLFORGE_L2_SCENE"]).resolve()
    scenario_raw = os.environ.get("CELLFORGE_L2_SCENARIO", "")
    scenario_root_raw = os.environ.get("CELLFORGE_L2_SCENARIO_ROOT", "")
    report_raw = os.environ.get("CELLFORGE_L2_REPORT", "")
    initial_scenario = (
        _load_scenario(Path(scenario_raw).resolve())
        if scenario_raw
        else json.loads(os.environ["CELLFORGE_L2_SCENARIO_JSON"])
    )
    scenario_documents = _acceptance_scenarios(
        Path(scenario_root_raw).resolve() if scenario_root_raw else None,
        initial_scenario,
    )
    app = omni.kit.app.get_app()
    node: IsaacL2AdapterNode | None = None
    executor: SingleThreadedExecutor | None = None
    executor_stop = threading.Event()
    executor_thread: threading.Thread | None = None
    try:
        if not omni.usd.get_context().open_stage(str(scene_path)):
            raise RuntimeError(f"Isaac could not open canonical scene '{scene_path}'")
        stage = omni.usd.get_context().get_stage()
        stage_builder = IsaacPenPhysicsBackend(stage)
        for document in scenario_documents:
            seed = int(document["scenario"]["seed"])
            if bool(document.get("initial_state", {}).get("product_present", True)):
                stage_builder.spawn_pen(f"pen-{seed:08d}", sample_pen_pose(seed, DEFAULT_BOUNDS))
        world = World()
        await world.initialize_simulation_context_async()
        await world.reset_async()
        backend = IsaacPenPhysicsBackend(stage, world)
        rclpy.init()
        node = IsaacL2AdapterNode(
            backend,
            initial_scenario,
            report_path=Path(report_raw).resolve() if report_raw else None,
            runtime_loop=asyncio.get_running_loop(),
        )
        executor = SingleThreadedExecutor()
        executor.add_node(node)
        executor_thread = threading.Thread(
            target=_spin_kit_executor,
            args=(executor, executor_stop),
            name="cellforge-isaac-rclpy",
            daemon=True,
        )
        executor_thread.start()
        while app.is_running() and rclpy.ok():
            await app.next_update_async()
    finally:
        executor_stop.set()
        if executor is not None:
            executor.wake()
        if executor_thread is not None:
            executor_thread.join(timeout=5.0)
        if executor is not None:
            executor.shutdown(timeout_sec=1.0)
        if node is not None:
            node.write_report()
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
