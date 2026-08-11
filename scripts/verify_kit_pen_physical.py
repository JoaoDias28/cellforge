"""Isaac Sim 6/OpenUSD/PhysX Task 020 probe executed through ``--exec``."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import omni.kit.app
import omni.usd
from isaacsim.core.api import World

app = omni.kit.app.get_app()


async def run() -> None:
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "ros_ws" / "src" / "cellforge_simulation"))
    from cellforge_simulation.pen_physics_backend import IsaacPenPhysicsBackend
    from cellforge_simulation.physical import PenPose, sample_pen_pose

    context = omni.usd.get_context()
    await context.open_stage_async(str(root / "examples" / "pen_engraving" / "scene.usda"))
    stage = context.get_stage()
    if stage is None:
        raise RuntimeError("Task 020 canonical USD scene did not open")
    world = World(stage_units_in_meters=1.0)
    await world.reset_async()
    backend = IsaacPenPhysicsBackend(stage, world)

    pen_path = backend.spawn_pen("pen-00001001", sample_pen_pose(1001))
    joint_path = backend.attach(pen_path)
    if not backend.is_attached(pen_path) or not stage.GetPrimAtPath(joint_path).IsValid():
        raise RuntimeError("Task 020 grasp attachment was not authored")
    backend.step(2)
    backend.detach(pen_path)
    backend.set_pen_pose(pen_path, PenPose(550.0, 0.0, 840.0, 0.0))
    if not backend.is_seated(pen_path):
        raise RuntimeError("Task 020 fixture seating signal did not become true")
    backend.set_pen_pose(pen_path, PenPose(0.0, 0.0, 700.0, 0.0))
    if not backend.is_dropped(pen_path):
        raise RuntimeError("Task 020 dropped-pen detector did not become true")
    print("Task 020 Isaac Sim 6 physical pen probe passed (actual PhysX/OpenUSD backend).")
    app.post_quit(0)


asyncio.ensure_future(run())
