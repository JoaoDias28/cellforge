from action_msgs.srv import CancelGoal
from cellforge_interfaces.action import (
    ExecuteFrozenJob,
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
    RequestOperatorAction,
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
        ExecuteFrozenJob,
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
        RequestOperatorAction,
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


def test_job_event_carries_frozen_execution_identity() -> None:
    event = JobEvent(bundle_id="b" * 64, recipe_sha256="c" * 64, task_sha256="d" * 64)

    assert event.bundle_id == "b" * 64
    assert event.recipe_sha256 == "c" * 64
    assert event.task_sha256 == "d" * 64


def test_operator_action_is_semantic_and_reports_outcome_certainty() -> None:
    request = RequestOperatorAction.Request(
        action_id="acknowledge-timeout",
        action_kind="acknowledge_fault",
        fault_id="laser-1:laser.timeout",
        principal_id="operator-1",
    )
    response = RequestOperatorAction.Response(
        accepted=False,
        result_code="operator.recovery.state_changed",
        result_message="Fault is no longer active.",
        outcome_certain=True,
    )

    assert request.action_kind == "acknowledge_fault"
    assert response.accepted is False
    assert response.outcome_certain is True
