"""Expose the ROS-free Task 027 adapter suite to the repository pytest target."""

from __future__ import annotations

import sys
from pathlib import Path

SIMULATION = Path(__file__).resolve().parents[1] / "ros_ws" / "src" / "cellforge_simulation"
sys.path.insert(0, str(SIMULATION))
sys.path.insert(0, str(SIMULATION / "test"))

from test_l2_runtime import *  # type: ignore[import-not-found]  # noqa: E402,F403
