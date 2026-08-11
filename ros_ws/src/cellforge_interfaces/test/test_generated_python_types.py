from action_msgs.srv import CancelGoal
from cellforge_interfaces.action import (
    ExecuteManipulation,
    ExecuteProcess,
    ExecuteSkill,
    InspectObject,
    LocateObject,
    MoveToPose,
    RunJob,
)
from cellforge_interfaces.msg import (
    CellState,
    DeviceState,
    JobEvent,
    PoseEstimate,
    SafetyState,
)
from cellforge_interfaces.srv import (
    ConfigureSimulation,
    ControlSimulation,
    FinalizeSimulation,
    GetDeviceState,
    InjectSimulationFault,
    RegisterSimulationAdapter,
    SetDiscreteOutput,
    SyncPlanningScene,
    ValidateRecipe,
)


def test_generated_python_types_are_importable() -> None:
    generated_types = (
        CellState,
        ConfigureSimulation,
        ControlSimulation,
        DeviceState,
        ExecuteProcess,
        ExecuteManipulation,
        ExecuteSkill,
        FinalizeSimulation,
        GetDeviceState,
        InspectObject,
        InjectSimulationFault,
        JobEvent,
        LocateObject,
        MoveToPose,
        PoseEstimate,
        RunJob,
        RegisterSimulationAdapter,
        SafetyState,
        SetDiscreteOutput,
        SyncPlanningScene,
        ValidateRecipe,
    )

    assert all(generated_type is not None for generated_type in generated_types)


def test_actions_represent_success_invalid_input_timeout_and_failure() -> None:
    success = ExecuteSkill.Result(success=True, result_code="skill.success")
    invalid_recipe = ValidateRecipe.Response(
        valid=False, validation_report_json='{"code":"recipe.invalid"}'
    )
    timeout_goal = RunJob.Goal()
    timeout_goal.timeout.sec = 30
    failure = ExecuteProcess.Result(
        success=False,
        result_code="process.communication.timeout",
        outcome_certain=False,
    )

    assert success.success is True
    assert invalid_recipe.valid is False
    assert "recipe.invalid" in invalid_recipe.validation_report_json
    assert timeout_goal.timeout.sec == 30
    assert failure.success is False
    assert failure.outcome_certain is False


def test_standard_action_cancellation_type_is_available() -> None:
    request = CancelGoal.Request()

    assert len(request.goal_info.goal_id.uuid) == 16


def test_job_event_carries_active_bundle_identity() -> None:
    event = JobEvent(bundle_id="b" * 64)

    assert event.bundle_id == "b" * 64
