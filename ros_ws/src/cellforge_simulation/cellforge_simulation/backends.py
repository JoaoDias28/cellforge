"""Backend implementations without ROS dependencies."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from cellforge_simulation.models import FaultDefinition


class ContractSimulationBackend:
    """Deterministic L0 backend for CPU-only CI and contract-mock scenarios.

    This backend records control/setup calls only. It deliberately does not expose physics or
    perception and must only be paired with L0 adapter registrations.
    """

    fidelity = "L0"

    def __init__(self, fault_sink: Callable[[dict[str, Any]], None] | None = None) -> None:
        self.seed: int | None = None
        self.initial_state: dict[str, Any] = {}
        self.running = False
        self.steps = 0
        self.faults: list[FaultDefinition] = []
        self._fault_sink = fault_sink

    def reset(self, seed: int, initial_state: dict[str, Any]) -> None:
        self.seed = seed
        self.initial_state = dict(initial_state)
        self.running = False
        self.steps = 0
        self.faults = []

    def play(self) -> None:
        self.running = True

    def pause(self) -> None:
        self.running = False

    def step(self, count: int) -> None:
        self.steps += count

    def inject_fault(self, fault: FaultDefinition) -> None:
        self.faults.append(fault)
        if self._fault_sink is not None:
            self._fault_sink(
                {
                    "at": fault.at,
                    "component_instance_id": fault.target,
                    "fault_code": fault.fault,
                    "parameters": fault.parameters,
                }
            )
