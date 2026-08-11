"""Jazzy generated-action mapping smoke test for Task 020."""

from __future__ import annotations

import pytest
from cellforge_interfaces.action import ExecuteManipulation, MoveToPose
from cellforge_simulation.motion_integration import PenMotionGoalFactory
from cellforge_simulation.physical import PenCycle, PhysicalSimulationError


def test_cycle_commands_map_to_task_019_generated_actions() -> None:
    result = PenCycle(1001).run()
    factory = PenMotionGoalFactory()
    goals = [
        factory.create_goal(
            command,
            result.sampled_pose,
            command_id=f"command-{index}",
            trace_id="trace-task-020",
        )
        for index, command in enumerate(result.motion_commands)
    ]

    assert [type(goal) for goal in goals] == [
        ExecuteManipulation.Goal,
        ExecuteManipulation.Goal,
        MoveToPose.Goal,
        ExecuteManipulation.Goal,
    ]
    assert [goal.operation for goal in (goals[0], goals[1], goals[3])] == [
        "pick",
        "load",
        "unload",
    ]
    assert goals[2].named_pose == "process_safe"
    assert all(goal.component_instance_id == "robot-001" for goal in goals)


def test_goal_mapping_rejects_missing_identity() -> None:
    result = PenCycle(1).run()
    with pytest.raises(PhysicalSimulationError, match="identity_missing"):
        PenMotionGoalFactory().create_goal(
            result.motion_commands[0], result.sampled_pose, command_id="", trace_id="trace"
        )
