"""Pure immutable bundle validation used before constructing the ROS launch graph."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_SHA256_LENGTH = 64
_REQUIRED_EXECUTABLES = {
    "adapter",
    "coordinator",
    "gateway",
    "motion_l0",
    "motion_l2",
    "operator",
    "safety_status",
    "state",
    "supervisor",
    "trace",
}
_L0_EXECUTABLES = {
    "adapter": ("cellforge_mock_adapters", "mock_device_node"),
    "coordinator": ("cellforge_bringup", "runtime_coordinator"),
    "gateway": ("cellforge_job_gateway", "job_gateway"),
    "motion_l0": ("cellforge_motion", "cellforge_l0_motion_service"),
    "motion_l2": ("cellforge_motion", "cellforge_motion_service"),
    "operator": ("cellforge_operator_api", "operator_api"),
    "safety_status": ("cellforge_mock_adapters", "mock_safety_status_node"),
    "state": ("cellforge_state_trace", "state_aggregator"),
    "supervisor": ("cellforge_supervisor", "cellforge_supervisor_node"),
    "trace": ("cellforge_state_trace", "durable_event_recorder"),
}
_L2_EXECUTABLES = {
    **_L0_EXECUTABLES,
    "adapter": ("cellforge_simulation", "isaac_l2_adapter"),
    "safety_status": ("cellforge_simulation", "isaac_l2_adapter"),
}
_TOPICS = {
    "cell_state": "/cell/state",
    "events": "/events/job",
    "safety_state": "/safety/state",
    "supervisor_state": "/cell/supervisor_state",
}
_ENDPOINTS = {
    "operator_action": "/cell/operator_action",
    "run_job": "/cell/run_job",
    "supervisor_run_job": "/cell/supervisor/run_job",
    "motion.move_to_pose": "/skills/move_to_pose",
    "motion.execute_manipulation": "/skills/execute_manipulation",
    "motion.sync_planning_scene": "/motion/sync_planning_scene",
}


class BringupError(RuntimeError):
    """Stable startup refusal for invalid or unavailable immutable runtime configuration."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


@dataclass(frozen=True, slots=True)
class ExecutableIdentity:
    package: str
    executable: str


@dataclass(frozen=True, slots=True)
class RuntimeBundle:
    root: Path
    manifest_path: Path
    bundle_id: str
    source_revision: str
    cell_id: str
    fidelity: str
    topics: dict[str, str]
    endpoints: dict[str, str]
    required_devices: tuple[str, ...]
    tree_root: Path
    adapter_configuration: Path
    recovery_catalog: Path
    cell_config: Path
    scene: Path
    cell_config_sha256: str
    scene_sha256: str
    executables: dict[str, ExecutableIdentity]


def load_runtime_bundle(bundle_root: str | Path, requested_fidelity: str = "L0") -> RuntimeBundle:
    root = Path(bundle_root).resolve()
    manifest_path = root / "manifest.json"
    document = _load_object(manifest_path, "bringup.manifest.invalid")
    bundle_id = str(document.get("bundle_id", ""))
    hash_input = dict(document)
    hash_input.pop("bundle_id", None)
    if bundle_id != _digest(_canonical(hash_input)):
        raise BringupError("bringup.manifest.identity_mismatch", "Bundle ID is not canonical.")
    runtime = document.get("runtime")
    if not isinstance(runtime, dict):
        raise BringupError("bringup.runtime.missing", "Manifest has no integrated runtime graph.")
    fidelity = str(runtime.get("simulation_fidelity", ""))
    if requested_fidelity != fidelity:
        raise BringupError(
            "bringup.fidelity.identity_mismatch",
            f"Requested {requested_fidelity}, but the immutable bundle selects {fidelity}.",
        )
    if fidelity not in {"L0", "L2"}:
        raise BringupError(
            "bringup.fidelity.unavailable",
            f"Runtime fidelity {fidelity!r} is unsupported; expected L0 or genuine Isaac L2.",
        )
    topics = _string_map(runtime.get("topics"), "bringup.runtime.topics_invalid")
    endpoints = _string_map(runtime.get("endpoints"), "bringup.runtime.endpoints_invalid")
    for name, expected in _TOPICS.items():
        if topics.get(name) != expected:
            raise BringupError(
                "bringup.runtime.topics_invalid", f"Topic '{name}' is not canonical."
            )
    for name, expected in _ENDPOINTS.items():
        if endpoints.get(name) != expected:
            raise BringupError(
                "bringup.runtime.endpoints_invalid", f"Endpoint '{name}' is not canonical."
            )
    raw_devices = runtime.get("required_devices")
    if (
        not isinstance(raw_devices, list)
        or not raw_devices
        or raw_devices != sorted(set(raw_devices))
        or not all(isinstance(item, str) and item for item in raw_devices)
    ):
        raise BringupError(
            "bringup.runtime.required_devices_invalid",
            "Required devices must be sorted and unique.",
        )
    executables = _executables(runtime.get("executables"))
    if set(executables) != _REQUIRED_EXECUTABLES:
        raise BringupError(
            "bringup.runtime.executables_invalid", "Runtime executable roles are incomplete."
        )
    expected_executables = _L0_EXECUTABLES if fidelity == "L0" else _L2_EXECUTABLES
    if {
        role: (identity.package, identity.executable) for role, identity in executables.items()
    } != expected_executables:
        raise BringupError(
            "bringup.runtime.executables_invalid",
            f"Runtime executable identities do not match the supported {fidelity} graph.",
        )
    for component_id in raw_devices:
        expected_topic = f"/device/{component_id.replace('-', '_')}/state"
        if topics.get(f"device.{component_id}") != expected_topic:
            raise BringupError(
                "bringup.runtime.topics_invalid",
                f"Device topic for '{component_id}' is not canonical.",
            )
    capabilities = document.get("capabilities")
    if not isinstance(capabilities, list):
        raise BringupError("bringup.runtime.endpoints_invalid", "Capabilities are invalid.")
    for capability in capabilities:
        if not isinstance(capability, dict):
            raise BringupError("bringup.runtime.endpoints_invalid", "Capability is invalid.")
        contract = capability.get("contract")
        provider = capability.get("provider_instance")
        endpoint = capability.get("endpoint")
        if (
            not isinstance(contract, str)
            or not contract
            or not isinstance(provider, str)
            or not provider
            or not isinstance(endpoint, str)
            or not endpoint
        ):
            raise BringupError("bringup.runtime.endpoints_invalid", "Capability is invalid.")
        expected_endpoint = f"/device/{provider.replace('-', '_')}/{endpoint}"
        if endpoints.get(f"capability.{contract}") != expected_endpoint:
            raise BringupError(
                "bringup.runtime.endpoints_invalid",
                f"Capability endpoint for '{contract}' is not canonical.",
            )
    files = document.get("files")
    if not isinstance(files, list):
        raise BringupError("bringup.manifest.files_invalid", "Bundle inventory is invalid.")
    inventory = {
        str(item.get("path")): item
        for item in files
        if isinstance(item, dict) and isinstance(item.get("path"), str)
    }
    resolved = {
        name: _verified_path(root, runtime.get(field), inventory)
        for name, field in {
            "tree_root": "tree_root",
            "adapter": "adapter_configuration_path",
            "recovery": "recovery_catalog_path",
            "cell": "cell_config_path",
            "scene": "scene_path",
        }.items()
    }
    if not resolved["tree_root"].is_dir():
        raise BringupError("bringup.runtime.tree_root_invalid", "Tree root is not a directory.")
    adapter_document = _load_object(resolved["adapter"], "bringup.adapters.invalid")
    if (
        adapter_document.get("schema_version") != "0.1.0"
        or not isinstance(adapter_document.get("nodes"), dict)
        or not isinstance(adapter_document.get("safety"), dict)
    ):
        raise BringupError(
            "bringup.adapters.invalid", f"{fidelity} adapter configuration is invalid."
        )
    return RuntimeBundle(
        root=root,
        manifest_path=manifest_path,
        bundle_id=bundle_id,
        source_revision=str(document.get("source_revision", "")),
        cell_id=str(document.get("cell_id", "")),
        fidelity=fidelity,
        topics=topics,
        endpoints=endpoints,
        required_devices=tuple(raw_devices),
        tree_root=resolved["tree_root"],
        adapter_configuration=resolved["adapter"],
        recovery_catalog=resolved["recovery"],
        cell_config=resolved["cell"],
        scene=resolved["scene"],
        cell_config_sha256=_digest(resolved["cell"].read_bytes()),
        scene_sha256=_digest(resolved["scene"].read_bytes()),
        executables=executables,
    )


def _verified_path(root: Path, raw: object, inventory: dict[str, Any]) -> Path:
    if not isinstance(raw, str) or not raw or Path(raw).is_absolute() or ".." in Path(raw).parts:
        raise BringupError("bringup.runtime.path_invalid", "Runtime path is not contained.")
    path = (root / raw).resolve()
    try:
        path.relative_to(root)
    except ValueError:
        raise BringupError(
            "bringup.runtime.path_invalid", "Runtime path escapes the bundle."
        ) from None
    if path.is_dir():
        prefix = f"{Path(raw).as_posix().rstrip('/')}/"
        if not any(item.startswith(prefix) for item in inventory):
            raise BringupError("bringup.manifest.file_missing", f"'{raw}' is not inventoried.")
        return path
    entry = inventory.get(Path(raw).as_posix())
    if not isinstance(entry, dict) or not path.is_file():
        raise BringupError("bringup.manifest.file_missing", f"'{raw}' is unavailable.")
    content = path.read_bytes()
    if entry.get("sha256") != _digest(content) or entry.get("size") != len(content):
        raise BringupError("bringup.manifest.file_mismatch", f"'{raw}' failed digest validation.")
    return path


def _executables(raw: object) -> dict[str, ExecutableIdentity]:
    if not isinstance(raw, dict):
        return {}
    result: dict[str, ExecutableIdentity] = {}
    for role, value in raw.items():
        if (
            not isinstance(role, str)
            or not isinstance(value, dict)
            or set(value) != {"package", "executable"}
            or not all(isinstance(value[key], str) and value[key] for key in value)
        ):
            raise BringupError(
                "bringup.runtime.executables_invalid", "Executable identity is invalid."
            )
        result[role] = ExecutableIdentity(value["package"], value["executable"])
    return result


def _string_map(raw: object, code: str) -> dict[str, str]:
    if not isinstance(raw, dict) or not all(
        isinstance(key, str) and isinstance(value, str) and value.startswith("/")
        for key, value in raw.items()
    ):
        raise BringupError(code, "ROS name map is invalid.")
    return dict(raw)


def _load_object(path: Path, code: str) -> dict[str, Any]:
    try:
        value: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise BringupError(code, f"'{path}' is unavailable or invalid.") from None
    if not isinstance(value, dict):
        raise BringupError(code, f"'{path}' must contain a JSON object.")
    return value


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
    ).encode()


def _digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()
