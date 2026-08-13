"""Start the Task 027 ROS L2 adapter inside an existing Isaac Sim Kit app."""

import asyncio
import os
import sys
import traceback

import omni.kit.app

for path in os.environ.get("CELLFORGE_PYTHONPATH", "").split(os.pathsep):
    if path and path not in sys.path:
        sys.path.insert(0, path)

from cellforge_simulation.l2_ros_node import run_in_existing_kit

app = omni.kit.app.get_app()


async def run() -> None:
    try:
        await run_in_existing_kit()
    except BaseException:
        traceback.print_exc()
        app.post_quit(1)


asyncio.ensure_future(run())
