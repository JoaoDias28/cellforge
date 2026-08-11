"""Standard-control runtime coordinator for scene preflight and semantic recovery."""

from __future__ import annotations

import time
from typing import Any

import rclpy
from cellforge_interfaces.msg import CellState
from cellforge_interfaces.srv import RequestOperatorAction, SyncPlanningScene
from cellforge_operator_api.core import OperatorError, RecoveryCatalog, RecoveryKind
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node

from cellforge_bringup.runtime import RuntimeBundle, load_runtime_bundle


class RuntimeCoordinator(Node):  # type: ignore[misc]
    """Coordinate fixed local standard-control services without safety authority."""

    def __init__(self, *, parameter_overrides: list[Any] | None = None) -> None:
        super().__init__("runtime_coordinator", parameter_overrides=parameter_overrides)
        bundle_root = str(self.declare_parameter("bundle_root", "").value)
        requested_fidelity = str(self.declare_parameter("requested_fidelity", "L0").value)
        self._bundle: RuntimeBundle = load_runtime_bundle(bundle_root, requested_fidelity)
        try:
            self._catalog = RecoveryCatalog.from_file(self._bundle.recovery_catalog)
        except OperatorError as error:
            raise RuntimeError(f"{error.code}: {error.message}") from error
        self._latest_state: Any | None = None
        self._state_at = 0.0
        group = ReentrantCallbackGroup()
        self.create_subscription(
            CellState,
            self._bundle.topics["cell_state"],
            self._on_state,
            10,
            callback_group=group,
        )
        self.create_service(
            RequestOperatorAction,
            self._bundle.endpoints["operator_action"],
            self._operator_action,
            callback_group=group,
        )
        self._scene_client = self.create_client(
            SyncPlanningScene,
            self._bundle.endpoints["motion.sync_planning_scene"],
            callback_group=group,
        )
        self._scene_future: Any | None = None
        self._scene_ready = False
        self.create_timer(0.25, self._synchronize_scene, callback_group=group)

    @property
    def scene_ready(self) -> bool:
        return self._scene_ready

    def _on_state(self, message: Any) -> None:
        self._latest_state = message
        self._state_at = time.monotonic()

    def _synchronize_scene(self) -> None:
        if self._scene_ready or self._scene_future is not None:
            return
        if not self._scene_client.service_is_ready():
            return
        request = SyncPlanningScene.Request()
        request.cell_id = self._bundle.cell_id
        request.scene_revision = f"bundle-{self._bundle.bundle_id[:16]}"
        request.cell_yaml_sha256 = self._bundle.cell_config_sha256
        request.usd_sha256 = self._bundle.scene_sha256
        request.component_instance_ids = list(self._bundle.required_devices)
        request.planning_scene.is_diff = True
        self._scene_future = self._scene_client.call_async(request)
        self._scene_future.add_done_callback(self._scene_synchronized)

    def _scene_synchronized(self, future: Any) -> None:
        self._scene_future = None
        try:
            response = future.result()
        except Exception as error:
            self.get_logger().error(f"L0 planning-scene synchronization failed: {error}")
            return
        self._scene_ready = bool(response.success)
        if not self._scene_ready:
            self.get_logger().error(
                f"L0 planning-scene synchronization refused: {response.result_code}"
            )

    def _operator_action(self, request: Any, response: Any) -> Any:
        try:
            return self._operator_action_checked(request, response)
        except Exception as error:
            self.get_logger().error(f"Operator-action evaluation failed: {error!r}")
            return _result(
                response,
                False,
                "operator.recovery.internal",
                "The local recovery service could not evaluate the request.",
            )

    def _operator_action_checked(self, request: Any, response: Any) -> Any:
        try:
            action = self._catalog.require(str(request.action_id))
        except OperatorError as error:
            return _result(response, False, error.code, error.message)
        if str(request.action_kind) != action.kind.value:
            return _result(
                response,
                False,
                "operator.recovery.semantic_mismatch",
                "Requested recovery kind does not match the immutable catalog.",
            )
        if not str(request.principal_id).strip():
            return _result(
                response,
                False,
                "operator.recovery.principal_invalid",
                "A local authenticated principal identity is required.",
            )
        state = self._latest_state
        if state is None or time.monotonic() - self._state_at > 3.0:
            return _result(
                response,
                False,
                "operator.recovery.state_unavailable",
                "Current local cell state is unavailable.",
            )
        fault = next(
            (
                device
                for device in state.devices
                if bool(device.faulted)
                and f"{device.component_instance_id}:{device.fault_code}" == str(request.fault_id)
            ),
            None,
        )
        if fault is None or str(fault.fault_code) not in action.fault_codes:
            return _result(
                response,
                False,
                "operator.recovery.not_applicable",
                "The approved action does not match a current fault.",
            )
        if action.kind is RecoveryKind.ACKNOWLEDGE_FAULT:
            return _result(
                response,
                True,
                "operator.recovery.acknowledged",
                "Fault acknowledgement recorded; device state was not changed.",
            )
        return _result(
            response,
            False,
            "operator.recovery.service_unavailable",
            "The required fixed local recovery service is unavailable.",
        )


def _result(response: Any, accepted: bool, code: str, message: str) -> Any:
    response.accepted = accepted
    response.result_code = code
    response.result_message = message
    response.outcome_certain = True
    return response


def main(args: list[str] | None = None) -> None:
    rclpy.init(args=args)
    node = RuntimeCoordinator()
    executor = MultiThreadedExecutor(num_threads=4)
    executor.add_node(node)
    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        executor.shutdown()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
