"""Launch the complete immutable offline CellForge L0 runtime."""

import json
from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from cellforge_bringup.runtime import RuntimeBundle, load_runtime_bundle
from launch import LaunchContext, LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, OpaqueFunction
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import EnvironmentVariable, LaunchConfiguration
from launch.conditions import IfCondition
from launch_ros.actions import Node


def _node(bundle: RuntimeBundle, role: str, **kwargs: object) -> Node:
    identity = bundle.executables[role]
    return Node(package=identity.package, executable=identity.executable, **kwargs)


def _launch(context: LaunchContext) -> list[object]:
    bundle_root = LaunchConfiguration("bundle_root").perform(context)
    fidelity = LaunchConfiguration("fidelity").perform(context)
    local_state = Path(LaunchConfiguration("local_state_root").perform(context)).resolve()
    auth_path = Path(LaunchConfiguration("operator_auth").perform(context)).resolve()
    operator_port = LaunchConfiguration("operator_port").perform(context)
    l2_scenario = LaunchConfiguration("l2_scenario").perform(context)
    l2_scenario_root = LaunchConfiguration("l2_scenario_root").perform(context)
    l2_report = LaunchConfiguration("l2_report").perform(context)
    l2_launch_adapter = LaunchConfiguration("l2_launch_adapter")
    local_state.mkdir(parents=True, exist_ok=True)
    bundle = load_runtime_bundle(bundle_root, fidelity)
    adapter_document = json.loads(bundle.adapter_configuration.read_text(encoding="utf-8"))
    nodes: list[object] = []
    if bundle.fidelity == "L2":
        nodes.append(
            _node(
                bundle,
                "adapter",
                name="isaac_l2_adapter",
                additional_env={
                    "CELLFORGE_L2_SCENE": str(bundle.scene),
                    "CELLFORGE_L2_SCENARIO": l2_scenario,
                    "CELLFORGE_L2_SCENARIO_ROOT": l2_scenario_root,
                    "CELLFORGE_L2_SCENARIO_JSON": json.dumps(
                        adapter_document.get("scenario", {}), sort_keys=True
                    ),
                    "CELLFORGE_L2_REPORT": l2_report,
                },
                output="screen",
                condition=IfCondition(l2_launch_adapter),
            )
        )
    else:
        for name, scenario in sorted(adapter_document["nodes"].items()):
            component_id = scenario["component_instance_id"]
            nodes.append(
                _node(
                    bundle,
                    "adapter",
                    name=name,
                    parameters=[
                        {
                            "scenario_json": json.dumps(scenario, sort_keys=True),
                            "endpoint_root": f"/device/{component_id.replace('-', '_')}",
                        }
                    ],
                    output="screen",
                )
            )
        safety = adapter_document["safety"]
        nodes.append(
            _node(
                bundle,
                "safety_status",
                parameters=[safety],
                output="screen",
            )
        )
    if bundle.fidelity == "L2":
        motion_launch = (
            Path(get_package_share_directory("cellforge_motion"))
            / "launch"
            / "motion_service.launch.py"
        )
        nodes.append(
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(str(motion_launch)),
                launch_arguments={"isaac_l2_direct": "true"}.items(),
            )
        )
    else:
        nodes.append(
            _node(
                bundle,
                "motion_l0",
                parameters=[{"bundle_id": bundle.bundle_id}],
                output="screen",
            )
        )
    nodes.append(
        _node(
            bundle,
            "coordinator",
            parameters=[{"bundle_root": str(bundle.root), "requested_fidelity": fidelity}],
            output="screen",
        )
    )
    device_topics = [
        bundle.topics[f"device.{component_id}"] for component_id in bundle.required_devices
    ]
    nodes.append(
        _node(
            bundle,
            "state",
            parameters=[
                {
                    "cell_id": bundle.cell_id,
                    "bundle_id": bundle.bundle_id,
                    "device_topics": device_topics,
                    "required_device_ids": list(bundle.required_devices),
                    "safety_topic": bundle.topics["safety_state"],
                    "supervisor_state_topic": bundle.topics["supervisor_state"],
                    "publish_rate_hz": 5.0,
                }
            ],
            output="screen",
        )
    )
    nodes.append(
        _node(
            bundle,
            "trace",
            parameters=[
                {
                    "db_path": str(local_state / "traces.db"),
                    "event_topic": bundle.topics["events"],
                }
            ],
            output="screen",
        )
    )
    nodes.append(
        _node(
            bundle,
            "supervisor",
            parameters=[
                {
                    "tree_root": str(bundle.tree_root),
                    "cell_id": bundle.cell_id,
                    "bundle_id": bundle.bundle_id,
                    "bundle_manifest_path": str(bundle.manifest_path),
                    "action_name": bundle.endpoints["supervisor_run_job"],
                }
            ],
            output="screen",
        )
    )
    nodes.append(
        _node(
            bundle,
            "gateway",
            parameters=[
                {
                    "bundle_root": str(bundle.root),
                    "manifest_path": "manifest.json",
                    "database_path": str(local_state / "jobs.db"),
                    "action_name": bundle.endpoints["run_job"],
                    "supervisor_action_name": bundle.endpoints["supervisor_run_job"],
                }
            ],
            output="screen",
        )
    )
    nodes.append(
        _node(
            bundle,
            "operator",
            additional_env={
                "CELLFORGE_BUNDLE_ROOT": str(bundle.root),
                "CELLFORGE_BUNDLE_ID": bundle.bundle_id,
                "CELLFORGE_MANIFEST": str(bundle.manifest_path),
                "CELLFORGE_OPERATOR_AUTH": str(auth_path),
                "CELLFORGE_RECOVERY_CATALOG": str(bundle.recovery_catalog),
                "CELLFORGE_OPERATOR_AUDIT": str(local_state / "operator-audit.db"),
                "CELLFORGE_TRACE_DATABASE": str(local_state / "traces.db"),
                "CELLFORGE_OPERATOR_HOST": "127.0.0.1",
                "CELLFORGE_OPERATOR_PORT": operator_port,
            },
            output="screen",
        )
    )
    return nodes


def generate_launch_description() -> LaunchDescription:
    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "bundle_root", default_value=EnvironmentVariable("CELLFORGE_BUNDLE_ROOT")
            ),
            DeclareLaunchArgument("fidelity", default_value="L0"),
            DeclareLaunchArgument("local_state_root", default_value="/var/lib/cellforge"),
            DeclareLaunchArgument(
                "operator_auth", default_value="/etc/cellforge/operator-auth.json"
            ),
            DeclareLaunchArgument("operator_port", default_value="9080"),
            DeclareLaunchArgument(
                "l2_scenario",
                default_value=EnvironmentVariable("CELLFORGE_L2_SCENARIO", default_value=""),
            ),
            DeclareLaunchArgument(
                "l2_scenario_root",
                default_value=EnvironmentVariable("CELLFORGE_L2_SCENARIO_ROOT", default_value=""),
            ),
            DeclareLaunchArgument("l2_report", default_value=""),
            DeclareLaunchArgument("l2_launch_adapter", default_value="true"),
            OpaqueFunction(function=_launch),
        ]
    )
