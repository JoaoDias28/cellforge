"""Non-Kit structural checks for extension discovery and thin UI boundaries."""

import ast
import tomllib
from pathlib import Path

EXTENSION_ROOT = Path(__file__).resolve().parents[1]


def test_extension_manifest_declares_supported_module_and_ui_dependency() -> None:
    manifest = tomllib.loads(
        (EXTENSION_ROOT / "config" / "extension.toml").read_text(encoding="utf-8")
    )

    assert manifest["package"]["version"] == "0.3.0"
    assert manifest["dependencies"] == {"omni.ui": {}}
    assert manifest["python"]["module"] == [{"name": "cellforge.studio.extension"}]


def test_application_layer_has_no_kit_ros_or_write_dependencies() -> None:
    source = (EXTENSION_ROOT / "cellforge" / "studio" / "application.py").read_text(
        encoding="utf-8"
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
