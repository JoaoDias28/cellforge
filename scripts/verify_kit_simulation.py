"""Isaac Sim 6 Task 018 ROS/Kit bridge probe executed via ``--exec``."""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path
from typing import Any

import omni.kit.app
import omni.usd
import rclpy
from cellforge_interfaces.msg import JobEvent
from cellforge_interfaces.srv import (
    ConfigureSimulation,
    ControlSimulation,
    FinalizeSimulation,
    RegisterSimulationAdapter,
)
from pxr import UsdGeom

app = omni.kit.app.get_app()


async def call_service(client_node: Any, client: Any, request: Any) -> Any:
    for _ in range(300):
        if client.service_is_ready():
            break
        rclpy.spin_once(client_node, timeout_sec=0.0)
        await app.next_update_async()
    else:
        raise RuntimeError(f"simulation service unavailable: {client.srv_name}")
    future = client.call_async(request)
    for _ in range(600):
        rclpy.spin_once(client_node, timeout_sec=0.0)
        await app.next_update_async()
        if future.done():
            response = future.result()
            if response is None:
                raise RuntimeError(f"simulation service returned no response: {client.srv_name}")
            return response
    raise RuntimeError(f"simulation service timed out: {client.srv_name}")


async def run() -> None:
    repository_root = Path(__file__).resolve().parents[1]
    project_root = repository_root / "examples" / "pen_engraving"
    scenario_path = project_root / "scenarios" / "nominal.yaml"
    context = omni.usd.get_context()
    context.new_stage()
    stage = context.get_stage()
    if stage is None:
        raise RuntimeError("Isaac Sim did not create a USD stage")
    UsdGeom.Xform.Define(stage, "/World")

    client_node = rclpy.create_node("cellforge_task_018_kit_probe")
    register_client = client_node.create_client(
        RegisterSimulationAdapter, "/simulation/register_adapter"
    )
    configure_client = client_node.create_client(ConfigureSimulation, "/simulation/configure")
    control_client = client_node.create_client(ControlSimulation, "/simulation/control")
    finalize_client = client_node.create_client(FinalizeSimulation, "/simulation/finalize")
    event_publisher = client_node.create_publisher(JobEvent, "/events/job", 100)
    try:
        for instance_id in (
            "camera-001",
            "fixture-001",
            "gripper-001",
            "laser-001",
            "robot-001",
        ):
            response = await call_service(
                client_node,
                register_client,
                RegisterSimulationAdapter.Request(
                    component_instance_id=instance_id,
                    capabilities=["sdk.test.execute"],
                    fidelity="L2",
                    endpoint=f"/kit-probe/{instance_id}",
                    fault_codes=["sdk.test.injected_fault"],
                ),
            )
            if not response.success:
                raise RuntimeError(f"adapter registration failed: {response.result_code}")

        configured = await call_service(
            client_node,
            configure_client,
            ConfigureSimulation.Request(
                project_path=str(project_root), scenario_path=str(scenario_path)
            ),
        )
        if not configured.success or configured.seed != 1001:
            raise RuntimeError(f"scenario configure failed: {configured.result_code}")
        for command, count in (("RESET", 1), ("STEP", 1), ("START", 1), ("PAUSE", 1)):
            controlled = await call_service(
                client_node,
                control_client,
                ControlSimulation.Request(command=command, step_count=count),
            )
            if not controlled.success:
                raise RuntimeError(f"{command} failed: {controlled.result_code}")

        for event_type in ("process.command.completed", "inspection.accepted", "job.completed"):
            event_publisher.publish(JobEvent(event_type=event_type, payload_json="{}"))
            for _ in range(4):
                rclpy.spin_once(client_node, timeout_sec=0.0)
                await app.next_update_async()

        evidence_path = Path(tempfile.mkdtemp(prefix="cellforge-task-018-kit-")) / "evidence.json"
        finalized = await call_service(
            client_node,
            finalize_client,
            FinalizeSimulation.Request(final_status="SUCCESS", evidence_path=str(evidence_path)),
        )
        if not finalized.success or not finalized.scenario_passed:
            raise RuntimeError(
                f"scenario finalization failed: {finalized.result_code} {finalized.failures_json}"
            )
        report = json.loads(evidence_path.read_text(encoding="utf-8"))
        if report["fidelity"]["achieved"] != "L2":
            raise RuntimeError("Isaac probe did not record achieved L2 adapter fidelity")
        root = stage.GetPrimAtPath("/World")
        if root.GetAttribute("cellforge:scenarioSeed").Get() != 1001:
            raise RuntimeError("Isaac backend did not apply the deterministic seed")
        print("Isaac Sim 6 Task 018 ROS reset/step/start/pause/evidence probe passed.")
    finally:
        client_node.destroy_node()
    app.post_quit(0)


def completed(task: asyncio.Task[None]) -> None:
    try:
        task.result()
    except Exception as error:
        print(f"Task 018 Isaac probe failed: {error}")
        app.post_quit(1)


probe = asyncio.ensure_future(run())
probe.add_done_callback(completed)
