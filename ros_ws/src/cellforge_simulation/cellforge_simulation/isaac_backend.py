"""Isaac Sim 6 implementation of the pure simulation backend port."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from cellforge_simulation.models import FaultDefinition


class IsaacBackendUnavailableError(RuntimeError):
    """Isaac Sim 6 APIs are unavailable or no active stage exists."""


class IsaacSimulationBackend:
    """Map control to Isaac Sim timeline/World APIs and scenario metadata to USD.

    Physical component behavior remains in registered simulation adapters behind the canonical
    ROS capability contracts. This class only controls the host simulation and publishes optional
    fault setup; it is not a device adapter or a safety controller.
    """

    fidelity = "L2"

    def __init__(self, fault_sink: Callable[[dict[str, Any]], None] | None = None) -> None:
        try:
            import omni.timeline
            import omni.usd
            from isaacsim.core.api import World
        except ImportError as error:
            raise IsaacBackendUnavailableError(
                "Isaac Sim 6 timeline, USD, and core APIs are required"
            ) from error
        self._timeline = omni.timeline.get_timeline_interface()
        self._usd_context = omni.usd.get_context()
        self._world_type = World
        self._fault_sink = fault_sink

    def _world(self) -> Any:
        world = self._world_type.instance()
        return world if world is not None else self._world_type()

    def _stage(self) -> Any:
        stage = self._usd_context.get_stage()
        if stage is None:
            raise IsaacBackendUnavailableError("Isaac Sim has no active USD stage")
        return stage

    def reset(self, seed: int, initial_state: dict[str, Any]) -> None:
        self._timeline.pause()
        self._world().reset()
        root = self._stage().GetPrimAtPath("/World")
        if not root or not root.IsValid():
            raise IsaacBackendUnavailableError("active stage has no valid /World prim")
        attributes = {
            "cellforge:scenarioSeed": ("Int64", seed),
            "cellforge:scenarioInitialStateJson": (
                "String",
                json.dumps(initial_state, sort_keys=True, separators=(",", ":")),
            ),
        }
        from pxr import Sdf

        for name, (type_name, value) in attributes.items():
            type_value = getattr(Sdf.ValueTypeNames, type_name)
            attribute = root.GetAttribute(name) or root.CreateAttribute(
                name, type_value, custom=True
            )
            attribute.Set(value)

    def play(self) -> None:
        self._timeline.play()

    def pause(self) -> None:
        self._timeline.pause()

    def step(self, count: int) -> None:
        world = self._world()
        for _ in range(count):
            world.step(render=False)

    def inject_fault(self, fault: FaultDefinition) -> None:
        payload = {
            "at": fault.at,
            "component_instance_id": fault.target,
            "fault_code": fault.fault,
            "parameters": fault.parameters,
        }
        root = self._stage().GetPrimAtPath("/World")
        from pxr import Sdf

        attribute = root.GetAttribute("cellforge:lastInjectedFaultJson") or root.CreateAttribute(
            "cellforge:lastInjectedFaultJson", Sdf.ValueTypeNames.String, custom=True
        )
        attribute.Set(json.dumps(payload, sort_keys=True, separators=(",", ":")))
        if self._fault_sink is not None:
            self._fault_sink(payload)
