"""L0 contract mock adapters for the CellForge reference device families."""

from cellforge_mock_adapters.core import MockDeviceAdapter, success_result
from cellforge_mock_adapters.devices import (
    MockFixtureAdapter,
    MockGripperAdapter,
    MockInspectionAdapter,
    MockProcessMachineAdapter,
    MockRobotMotionAdapter,
    MockVisionLocatorAdapter,
    build_device_mock,
    contract_scenario_config,
    make_contract_factory,
)
from cellforge_mock_adapters.scenarios import (
    DEVICE_CAPABILITIES,
    DEVICE_FAULT_CATALOGS,
    TEST_HOOK_CAPABILITY,
    TEST_HOOK_FAULT,
    UNCERTAIN_FAULT_CODES,
    DeviceKind,
    DeviceScenario,
    OperationBehavior,
    ScenarioConfigError,
    load_scenario_file,
    parse_device_scenario,
    parse_scenario_document,
)

__all__ = [
    "DEVICE_CAPABILITIES",
    "DEVICE_FAULT_CATALOGS",
    "TEST_HOOK_CAPABILITY",
    "TEST_HOOK_FAULT",
    "UNCERTAIN_FAULT_CODES",
    "DeviceKind",
    "DeviceScenario",
    "MockDeviceAdapter",
    "MockFixtureAdapter",
    "MockGripperAdapter",
    "MockInspectionAdapter",
    "MockProcessMachineAdapter",
    "MockRobotMotionAdapter",
    "MockVisionLocatorAdapter",
    "OperationBehavior",
    "ScenarioConfigError",
    "build_device_mock",
    "contract_scenario_config",
    "load_scenario_file",
    "make_contract_factory",
    "parse_device_scenario",
    "parse_scenario_document",
    "success_result",
]
