"""Non-Kit structural checks for extension discovery and thin UI boundaries."""

import ast
import tomllib
from pathlib import Path

EXTENSION_ROOT = Path(__file__).resolve().parents[1]


def test_extension_manifest_declares_supported_module_and_ui_dependency() -> None:
    manifest = tomllib.loads(
        (EXTENSION_ROOT / "config" / "extension.toml").read_text(encoding="utf-8")
    )

    assert manifest["package"]["version"] == "0.5.0"
    assert manifest["dependencies"] == {"omni.ui": {}, "omni.usd": {}}
    assert manifest["python"]["module"] == [{"name": "cellforge.studio.extension"}]


def test_application_layer_has_no_kit_ros_or_write_dependencies() -> None:
    source = "\n".join(
        (EXTENSION_ROOT / "cellforge" / "studio" / filename).read_text(encoding="utf-8")
        for filename in ("application.py", "simulation_application.py")
    )
    tree = ast.parse(source)
    imported_roots = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported_roots.update(
        node.module.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    )

    assert imported_roots.isdisjoint({"omni", "carb", "rclpy", "pxr"})
    assert ".write_text(" not in source
    assert ".write_bytes(" not in source
    assert "open(" not in source


def test_ui_callbacks_delegate_to_application_services() -> None:
    source = (EXTENSION_ROOT / "cellforge" / "studio" / "extension.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    expected = {
        "_on_create_project": "create_project",
        "_on_open_project": "open_project",
        "_on_save_project": "save_project",
        "_on_refresh_components": "refresh_components",
        "_on_place_component": "place_component",
        "_on_remove_component": "remove_component",
        "_on_undo": "undo",
        "_on_redo": "redo",
        "_on_refresh_connections": "refresh_connections",
        "_on_preview_mechanical_connection": "preview_mechanical_connection",
        "_on_connect_ports": "connect_ports",
        "_on_set_transform": "set_component_transform",
        "_on_set_configuration": "set_component_configuration",
        "_on_set_variants": "set_component_variants",
        "_on_create_calibration": "create_calibration",
        "_on_configure_simulation": "configure",
        "_on_simulation_control": "control",
        "_on_inject_simulation_fault": "inject_fault",
        "_on_finalize_simulation": "finalize",
    }
    for callback_name, command_name in expected.items():
        callback = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == callback_name
        )
        called_attributes = {
            node.func.attr
            for node in ast.walk(callback)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        assert command_name in called_attributes
        assert called_attributes.isdisjoint(
            {"validate_project", "inspect_project", "load_document", "write_text"}
        )


def test_safety_connections_have_distinct_non_executable_presentation() -> None:
    source = (EXTENSION_ROOT / "cellforge" / "studio" / "extension.py").read_text(encoding="utf-8")

    assert "MODELED SAFETY (NON-EXECUTABLE)" in source
    assert "MODELED-ONLY SAFETY" in source
    assert "Modeled safety dependencies are never executable wiring." in source


def test_simulation_host_spins_ros_from_kit_update_stream() -> None:
    source = (EXTENSION_ROOT / "cellforge" / "studio" / "simulation_host.py").read_text(
        encoding="utf-8"
    )

    assert "get_update_event_stream" in source
    assert "create_subscription_to_pop" in source
    assert "spin_once" in source
    assert "IsaacSimulationBackend" in source
    assert "SimulationControlService" in source
