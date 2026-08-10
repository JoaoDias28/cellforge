from __future__ import annotations

from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / "ros_interfaces"
PACKAGE_ROOT = REPOSITORY_ROOT / "ros_ws" / "src" / "cellforge_interfaces"
INTERFACE_PATHS = (
    "action/ExecuteProcess.action",
    "action/ExecuteSkill.action",
    "action/InspectObject.action",
    "action/LocateObject.action",
    "action/RunJob.action",
    "msg/CellState.msg",
    "msg/DeviceState.msg",
    "msg/JobEvent.msg",
    "msg/PoseEstimate.msg",
    "msg/SafetyState.msg",
    "srv/GetDeviceState.srv",
    "srv/ConfigureSimulation.srv",
    "srv/ControlSimulation.srv",
    "srv/FinalizeSimulation.srv",
    "srv/InjectSimulationFault.srv",
    "srv/RegisterSimulationAdapter.srv",
    "srv/SetDiscreteOutput.srv",
    "srv/ValidateRecipe.srv",
)
VENDOR_SPECIFIC_TERMS = (
    "abb",
    "ethernetip",
    "fanuc",
    "kuka",
    "modbus",
    "opcua",
    "profinet",
    "ur_",
    "yaskawa",
)


def test_packaged_interfaces_match_canonical_source_definitions() -> None:
    for relative_path in INTERFACE_PATHS:
        source = SOURCE_ROOT / relative_path
        packaged = PACKAGE_ROOT / relative_path

        assert source.is_file()
        assert packaged.is_file()
        assert packaged.read_text(encoding="utf-8") == source.read_text(encoding="utf-8")


def test_actions_expose_timeout_feedback_and_stable_result_fields() -> None:
    for relative_path in INTERFACE_PATHS:
        if not relative_path.endswith(".action"):
            continue

        definition = (SOURCE_ROOT / relative_path).read_text(encoding="utf-8")
        goal, result, feedback = definition.split("---")

        assert "builtin_interfaces/Duration timeout" in goal
        assert "bool success" in result
        assert "string result_code" in result
        assert "string result_message" in result
        assert feedback.strip()


def test_interfaces_exclude_vendor_specific_fields() -> None:
    interface_text = "\n".join(
        (SOURCE_ROOT / relative_path).read_text(encoding="utf-8").lower()
        for relative_path in INTERFACE_PATHS
    )

    assert all(term not in interface_text for term in VENDOR_SPECIFIC_TERMS)
