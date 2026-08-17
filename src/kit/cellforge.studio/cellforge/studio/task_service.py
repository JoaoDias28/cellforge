"""Pure BehaviorTree.CPP task authoring and compiler-equivalent validation service."""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml
from cellforge_domain import CellProject

from cellforge.studio.application import ProjectContents, ValidationItem

_BLACKBOARD_POINTER = re.compile(r"^\{([A-Za-z0-9_]+)\}$")
_SEEDED_BLACKBOARD_KEYS = frozenset(
    {
        "job_id",
        "cell_id",
        "recipe_id",
        "recipe_version",
        "input_payload_json",
        "execution_mode",
        "cell_ready",
        "idempotency_key",
        "source_revision",
        "task_id",
        "task_sha256",
        "recipe_sha256",
        "trace_id",
    }
)


class PortDirection(StrEnum):
    """Port direction in BehaviorTree.CPP manifests."""

    INPUT = "input"
    OUTPUT = "output"
    INOUT = "inout"


class NodeCategory(StrEnum):
    """BehaviorTree node classification."""

    ACTION = "action"
    CONDITION = "condition"
    CONTROL = "control"
    DECORATOR = "decorator"
    SUBTREE = "subtree"
    TRANSFORMATION = "transformation"


@dataclass(frozen=True, slots=True)
class TaskPortSpec:
    """One typed port declaration on a BehaviorTree node."""

    name: str
    direction: str
    type: str
    required: bool = False
    default: Any | None = None
    description: str | None = None


@dataclass(frozen=True, slots=True)
class TaskNodeSpec:
    """Declared metadata and port schema for one BehaviorTree node type."""

    type: str
    category: str
    ports: tuple[TaskPortSpec, ...]
    plugin_package: str = "builtin"
    plugin_library: str = "builtin"
    description: str | None = None

    @property
    def port_map(self) -> dict[str, TaskPortSpec]:
        return {port.name: port for port in self.ports}


@dataclass(frozen=True, slots=True)
class TaskNodeModel:
    """In-memory tree node with typed port mappings and non-runtime UI layout."""

    node_id: str
    type: str
    name: str | None = None
    ports: Mapping[str, str] = field(default_factory=dict)
    children: tuple[TaskNodeModel, ...] = ()
    layout: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class TaskTreeModel:
    """Complete in-memory BehaviorTree model."""

    id: str
    main_tree_to_execute: str
    root: TaskNodeModel
    format_version: str = "4"
    nodes_model: tuple[TaskNodeSpec, ...] = ()


@dataclass(frozen=True, slots=True)
class TaskSummary:
    """High-level task record displayed in Studio panels."""

    id: str
    behavior_tree_path: str
    required_capabilities: tuple[str, ...]
    node_count: int
    root_node_type: str
    valid: bool


@dataclass(frozen=True, slots=True)
class TaskBrowserResult:
    """Deterministic result of querying project tasks and available nodes."""

    tasks: tuple[TaskSummary, ...]
    available_node_specs: tuple[TaskNodeSpec, ...]
    validation: tuple[ValidationItem, ...] = ()


@dataclass(frozen=True, slots=True)
class TaskEditResult:
    """Result of saving or modifying a task tree in memory."""

    contents: ProjectContents | None
    task_id: str | None = None
    validation: tuple[ValidationItem, ...] = ()
    tree: TaskTreeModel | None = None


BUILTIN_NODE_SPECS: tuple[TaskNodeSpec, ...] = (
    # Controls
    TaskNodeSpec(
        type="Sequence",
        category=NodeCategory.CONTROL,
        ports=(),
        description="Executes children sequentially until one fails.",
    ),
    TaskNodeSpec(
        type="Fallback",
        category=NodeCategory.CONTROL,
        ports=(),
        description="Executes children sequentially until one succeeds.",
    ),
    TaskNodeSpec(
        type="Parallel",
        category=NodeCategory.CONTROL,
        ports=(
            TaskPortSpec("failure_count", PortDirection.INPUT, "int", required=False, default=1),
            TaskPortSpec("success_count", PortDirection.INPUT, "int", required=False, default=1),
        ),
        description="Ticks children concurrently.",
    ),
    TaskNodeSpec(
        type="ReactiveSequence",
        category=NodeCategory.CONTROL,
        ports=(),
        description="Reactive sequence restarting from first child on each tick.",
    ),
    TaskNodeSpec(
        type="ReactiveFallback",
        category=NodeCategory.CONTROL,
        ports=(),
        description="Reactive fallback restarting from first child on each tick.",
    ),
    # Decorators
    TaskNodeSpec(
        type="RetryUntilSuccessful",
        category=NodeCategory.DECORATOR,
        ports=(TaskPortSpec("num_attempts", PortDirection.INPUT, "int", required=True, default=2),),
        description="Retries child node up to specified attempts.",
    ),
    TaskNodeSpec(
        type="Repeat",
        category=NodeCategory.DECORATOR,
        ports=(TaskPortSpec("num_cycles", PortDirection.INPUT, "int", required=True, default=1),),
        description="Repeats child execution for specified cycle count.",
    ),
    TaskNodeSpec(
        type="Inverter",
        category=NodeCategory.DECORATOR,
        ports=(),
        description="Inverts child SUCCESS to FAILURE and vice versa.",
    ),
    TaskNodeSpec(
        type="ForceSuccess",
        category=NodeCategory.DECORATOR,
        ports=(),
        description="Returns SUCCESS regardless of child outcome.",
    ),
    TaskNodeSpec(
        type="ForceFailure",
        category=NodeCategory.DECORATOR,
        ports=(),
        description="Returns FAILURE regardless of child outcome.",
    ),
    TaskNodeSpec(
        type="Timeout",
        category=NodeCategory.DECORATOR,
        ports=(TaskPortSpec("msec", PortDirection.INPUT, "int", required=True, default=5000),),
        description="Aborts child execution if elapsed time exceeds timeout.",
    ),
    TaskNodeSpec(
        type="KeepRunningUntilFailure",
        category=NodeCategory.DECORATOR,
        ports=(),
        description="Repeats child until it returns FAILURE.",
    ),
    # SubTree
    TaskNodeSpec(
        type="SubTree",
        category=NodeCategory.SUBTREE,
        ports=(TaskPortSpec("ID", PortDirection.INPUT, "string", required=True),),
        description="Executes a referenced SubTree.",
    ),
)


class TaskAuthoringService:
    """Pure domain service for BehaviorTree graph authoring, XML generation, and validation."""

    def __init__(self, canonical_schema_directory: Path) -> None:
        self._canonical_schemas = canonical_schema_directory.resolve()

    def discover_node_specs(self, project_path: Path) -> tuple[TaskNodeSpec, ...]:
        """Load built-in control/decorator nodes and installed plugin manifests."""
        root = project_path.resolve()
        specs: dict[str, TaskNodeSpec] = {spec.type: spec for spec in BUILTIN_NODE_SPECS}

        plugins_dir = root / "behavior_tree_plugins"
        if plugins_dir.is_dir():
            for manifest_file in sorted(plugins_dir.glob("*.json")):
                try:
                    data = json.loads(manifest_file.read_text(encoding="utf-8"))
                except (OSError, UnicodeError, json.JSONDecodeError):
                    continue
                if not isinstance(data, dict) or data.get("schema_version") != "0.1.0":
                    continue
                plugin_info = data.get("plugin", {})
                package_name = plugin_info.get("package", "unknown")
                library_name = plugin_info.get("library", "unknown")
                nodes = data.get("nodes", [])
                if not isinstance(nodes, list):
                    continue
                for node_dict in nodes:
                    if not isinstance(node_dict, dict):
                        continue
                    node_type = node_dict.get("type")
                    if not isinstance(node_type, str) or not node_type:
                        continue
                    category = node_dict.get("category", NodeCategory.ACTION)
                    ports_list = node_dict.get("ports", [])
                    ports: list[TaskPortSpec] = []
                    if isinstance(ports_list, list):
                        for p in ports_list:
                            if not isinstance(p, dict):
                                continue
                            p_name = p.get("name")
                            if not isinstance(p_name, str) or not p_name:
                                continue
                            ports.append(
                                TaskPortSpec(
                                    name=p_name,
                                    direction=p.get("direction", "input"),
                                    type=p.get("type", "string"),
                                    required=bool(p.get("required", False)),
                                    default=p.get("default"),
                                    description=p.get("description"),
                                )
                            )
                    specs[node_type] = TaskNodeSpec(
                        type=node_type,
                        category=category,
                        ports=tuple(ports),
                        plugin_package=package_name,
                        plugin_library=library_name,
                        description=node_dict.get("description"),
                    )

        return tuple(specs.values())

    def parse_task_xml(
        self,
        xml_text: str,
        available_specs: Mapping[str, TaskNodeSpec] | None = None,
    ) -> TaskTreeModel:
        """Parse canonical BehaviorTree.CPP v4 XML into a TaskTreeModel with layout metadata."""
        root_element = ET.fromstring(xml_text)
        if root_element.tag != "root":
            raise ValueError("Root element must be <root>")

        bt_format = root_element.attrib.get("BTCPP_format", "4")
        main_tree = root_element.attrib.get("main_tree_to_execute", "")

        bt_elements = [child for child in root_element if child.tag == "BehaviorTree"]
        if not bt_elements:
            raise ValueError("XML does not contain any <BehaviorTree> elements")

        selected_bt = None
        if main_tree:
            for bt in bt_elements:
                if bt.attrib.get("ID") == main_tree:
                    selected_bt = bt
                    break
        if selected_bt is None:
            selected_bt = bt_elements[0]
            if not main_tree:
                main_tree = selected_bt.attrib.get("ID", "Main")

        tree_id = selected_bt.attrib.get("ID", main_tree)

        # Children of selected_bt
        children = [c for c in selected_bt if isinstance(c.tag, str)]
        if not children:
            raise ValueError("BehaviorTree element has no child root node")

        def parse_node(elem: ET.Element) -> TaskNodeModel:
            node_type = elem.tag
            node_name = elem.attrib.get("name")
            ports: dict[str, str] = {}
            layout: dict[str, Any] = {}

            for k, v in elem.attrib.items():
                if k == "name":
                    continue
                elif k.startswith("_"):
                    layout_key = k[1:]
                    try:
                        layout[layout_key] = json.loads(v)
                    except (ValueError, TypeError):
                        layout[layout_key] = v
                else:
                    ports[k] = v

            child_nodes = tuple(
                parse_node(c) for c in elem if isinstance(c.tag, str) and not c.tag.startswith("_")
            )
            return TaskNodeModel(
                node_id=f"node_{uuid4().hex[:8]}",
                type=node_type,
                name=node_name,
                ports=ports,
                children=child_nodes,
                layout=layout,
            )

        root_node = parse_node(children[0])
        return TaskTreeModel(
            id=tree_id,
            main_tree_to_execute=main_tree,
            root=root_node,
            format_version=bt_format,
        )

    def generate_task_xml(
        self,
        tree: TaskTreeModel,
        *,
        include_layout: bool = True,
    ) -> str:
        """Generate canonical BehaviorTree.CPP v4 XML with optional non-runtime layout metadata."""
        lines: list[str] = [
            (
                f'<root BTCPP_format="{tree.format_version}" '
                f'main_tree_to_execute="{tree.main_tree_to_execute}">'
            ),
            f'  <BehaviorTree ID="{tree.id}">',
        ]

        def emit_node(node: TaskNodeModel, indent: int) -> None:
            pad = "  " * indent
            attribs: list[str] = []
            if node.name:
                attribs.append(f'name="{node.name}"')
            for k, v in sorted(node.ports.items()):
                # escape XML attribute value
                escaped = (
                    str(v)
                    .replace("&", "&amp;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;")
                    .replace('"', "&quot;")
                )
                attribs.append(f'{k}="{escaped}"')

            if include_layout and node.layout:
                for lk, lv in sorted(node.layout.items()):
                    val_str = json.dumps(lv) if isinstance(lv, (dict, list, bool)) else str(lv)
                    escaped_val = (
                        val_str.replace("&", "&amp;")
                        .replace("<", "&lt;")
                        .replace(">", "&gt;")
                        .replace('"', "&quot;")
                    )
                    attribs.append(f'_{lk}="{escaped_val}"')

            attr_str = (" " + " ".join(attribs)) if attribs else ""
            if not node.children:
                lines.append(f"{pad}<{node.type}{attr_str}/>")
            else:
                lines.append(f"{pad}<{node.type}{attr_str}>")
                for child in node.children:
                    emit_node(child, indent + 1)
                lines.append(f"{pad}</{node.type}>")

        emit_node(tree.root, 2)
        lines.append("  </BehaviorTree>")
        lines.append("</root>")
        return "\n".join(lines) + "\n"

    def validate_tree(
        self,
        tree: TaskTreeModel,
        available_specs: Mapping[str, TaskNodeSpec],
        *,
        cell_model: CellProject | None = None,
        task_declaration: Any | None = None,
        source_path: str = "behavior_tree.xml",
    ) -> tuple[ValidationItem, ...]:
        """Perform compiler-equivalent static validation on a TaskTreeModel."""
        findings: list[ValidationItem] = []

        # 1. Collect produced blackboard keys
        produced: set[str] = set()

        def collect_produced(node: TaskNodeModel) -> None:
            spec = available_specs.get(node.type)
            if spec is not None:
                for port_name, value in node.ports.items():
                    port_spec = spec.port_map.get(port_name)
                    if port_spec and port_spec.direction in {
                        PortDirection.OUTPUT,
                        PortDirection.INOUT,
                    }:
                        m = _BLACKBOARD_POINTER.fullmatch(value)
                        if m:
                            produced.add(m.group(1))
            for child in node.children:
                collect_produced(child)

        collect_produced(tree.root)
        available_keys = set(_SEEDED_BLACKBOARD_KEYS) | produced

        # 2. Check process retry policy
        def check_process_retry(node: TaskNodeModel, under_retry: bool) -> None:
            is_retry = under_retry or node.type in {"RetryUntilSuccessful", "Repeat"}
            if node.type == "ExecuteProcess" and under_retry:
                findings.append(
                    ValidationItem(
                        code="compiler.behavior-tree-process-retry-forbidden",
                        severity="error",
                        path=f"{source_path}#/ExecuteProcess",
                        message="ExecuteProcess cannot be nested beneath automatic retry.",
                    )
                )
            for child in node.children:
                check_process_retry(child, is_retry)

        check_process_retry(tree.root, False)

        # 3. Validate each node against spec, ports, and blackboard mappings
        def validate_node(node: TaskNodeModel) -> None:
            spec = available_specs.get(node.type)
            if spec is None:
                findings.append(
                    ValidationItem(
                        code="compiler.behavior-tree-node-unknown",
                        severity="error",
                        path=f"{source_path}#/{node.type}",
                        message=f"Node type '{node.type}' is not declared by an immutable plugin.",
                    )
                )
            else:
                # Check unknown ports
                known_ports = set(spec.port_map.keys())
                for port_name in sorted(set(node.ports.keys()) - known_ports):
                    findings.append(
                        ValidationItem(
                            code="compiler.behavior-tree-port-unknown",
                            severity="error",
                            path=f"{source_path}#/{node.type}/@{port_name}",
                            message=f"Node '{node.type}' has unknown port '{port_name}'.",
                        )
                    )

                # Check missing required ports
                for p in spec.ports:
                    if p.required and p.name not in node.ports:
                        findings.append(
                            ValidationItem(
                                code="compiler.behavior-tree-port-missing",
                                severity="error",
                                path=f"{source_path}#/{node.type}",
                                message=f"Node '{node.type}' is missing required port '{p.name}'.",
                            )
                        )

                # Check port mappings and blackboard references
                for port_name, val in node.ports.items():
                    p_spec = spec.port_map.get(port_name)
                    if p_spec is None:
                        continue
                    m = _BLACKBOARD_POINTER.fullmatch(val)
                    looks_mapped = val.startswith("{") or val.endswith("}")

                    if (
                        p_spec.direction in {PortDirection.OUTPUT, PortDirection.INOUT}
                        and m is None
                    ):
                        findings.append(
                            ValidationItem(
                                code="compiler.behavior-tree-mapping-invalid",
                                severity="error",
                                path=f"{source_path}#/{node.type}/@{port_name}",
                                message=(
                                    f"Output port '{port_name}' must map to one blackboard key."
                                ),
                            )
                        )
                    elif looks_mapped and m is None:
                        findings.append(
                            ValidationItem(
                                code="compiler.behavior-tree-mapping-invalid",
                                severity="error",
                                path=f"{source_path}#/{node.type}/@{port_name}",
                                message=f"Port '{port_name}' has an invalid blackboard mapping.",
                            )
                        )
                    elif (
                        m
                        and p_spec.direction in {PortDirection.INPUT, PortDirection.INOUT}
                        and m.group(1) not in available_keys
                    ):
                        findings.append(
                            ValidationItem(
                                code="compiler.behavior-tree-mapping-unresolved",
                                severity="error",
                                path=f"{source_path}#/{node.type}/@{port_name}",
                                message=(
                                    f"Input port '{port_name}' maps unresolved "
                                    f"blackboard key '{m.group(1)}'."
                                ),
                            )
                        )

            for child in node.children:
                validate_node(child)

        validate_node(tree.root)

        # 4. Capability resolution against cell project
        if cell_model is not None and task_declaration is not None:
            pass

        return tuple(findings)

    def browse(
        self,
        project_path: Path,
        contents: ProjectContents,
    ) -> TaskBrowserResult:
        """Query project tasks and available BehaviorTree node manifests."""
        root = project_path.resolve()
        specs = self.discover_node_specs(root)
        spec_map = {s.type: s for s in specs}

        try:
            cell_data = yaml.safe_load(contents.cell_yaml)
        except (yaml.YAMLError, UnicodeError):
            return TaskBrowserResult(
                tasks=(),
                available_node_specs=specs,
                validation=(
                    ValidationItem(
                        code="studio.task.cell_yaml_invalid",
                        severity="error",
                        path=f"{root / 'cell.yaml'}#",
                        message="cell.yaml could not be parsed.",
                    ),
                ),
            )

        if not isinstance(cell_data, dict):
            return TaskBrowserResult(
                tasks=(),
                available_node_specs=specs,
                validation=(),
            )

        raw_tasks = cell_data.get("tasks", [])
        if not isinstance(raw_tasks, list):
            raw_tasks = []

        task_summaries: list[TaskSummary] = []
        validation_items: list[ValidationItem] = []

        for task_dict in raw_tasks:
            if not isinstance(task_dict, dict):
                continue
            task_id = str(task_dict.get("id", "unnamed"))
            bt_rel_path = str(task_dict.get("behavior_tree", "behavior_tree.xml"))
            req_caps = tuple(str(c) for c in task_dict.get("required_capabilities", []))

            # Retrieve XML either from staged artifacts or filesystem
            xml_text = None
            if bt_rel_path in contents.artifacts:
                try:
                    xml_text = contents.artifacts[bt_rel_path].decode("utf-8")
                except UnicodeError:
                    pass
            elif (root / bt_rel_path).is_file():
                try:
                    xml_text = (root / bt_rel_path).read_text(encoding="utf-8")
                except (OSError, UnicodeError):
                    pass

            if xml_text is None:
                task_summaries.append(
                    TaskSummary(
                        id=task_id,
                        behavior_tree_path=bt_rel_path,
                        required_capabilities=req_caps,
                        node_count=0,
                        root_node_type="Unknown",
                        valid=False,
                    )
                )
                validation_items.append(
                    ValidationItem(
                        code="studio.task.xml_missing",
                        severity="error",
                        path=f"{root / bt_rel_path}#",
                        message=f"Behavior-tree XML '{bt_rel_path}' could not be read.",
                    )
                )
                continue

            try:
                tree_model = self.parse_task_xml(xml_text, spec_map)
                findings = self.validate_tree(
                    tree_model,
                    spec_map,
                    source_path=str(root / bt_rel_path),
                )
                validation_items.extend(findings)

                # Count nodes
                def count_nodes(n: TaskNodeModel) -> int:
                    return 1 + sum(count_nodes(c) for c in n.children)

                node_cnt = count_nodes(tree_model.root)
                task_summaries.append(
                    TaskSummary(
                        id=task_id,
                        behavior_tree_path=bt_rel_path,
                        required_capabilities=req_caps,
                        node_count=node_cnt,
                        root_node_type=tree_model.root.type,
                        valid=len(findings) == 0,
                    )
                )
            except Exception as e:
                task_summaries.append(
                    TaskSummary(
                        id=task_id,
                        behavior_tree_path=bt_rel_path,
                        required_capabilities=req_caps,
                        node_count=0,
                        root_node_type="Error",
                        valid=False,
                    )
                )
                validation_items.append(
                    ValidationItem(
                        code="studio.task.xml_invalid",
                        severity="error",
                        path=f"{root / bt_rel_path}#",
                        message=f"Error parsing task XML: {e}",
                    )
                )

        return TaskBrowserResult(
            tasks=tuple(task_summaries),
            available_node_specs=specs,
            validation=tuple(validation_items),
        )

    def set_task_tree(
        self,
        project_path: Path,
        contents: ProjectContents,
        *,
        task_id: str,
        tree: TaskTreeModel | str,
    ) -> TaskEditResult:
        """Update or replace a task's BehaviorTree XML in staged project artifacts."""
        root = project_path.resolve()
        specs = self.discover_node_specs(root)
        spec_map = {s.type: s for s in specs}

        try:
            cell_data = yaml.safe_load(contents.cell_yaml)
        except (yaml.YAMLError, UnicodeError):
            return TaskEditResult(
                contents=None,
                task_id=task_id,
                validation=(
                    ValidationItem(
                        code="studio.task.cell_yaml_invalid",
                        severity="error",
                        path=f"{root / 'cell.yaml'}#",
                        message="cell.yaml is not valid YAML.",
                    ),
                ),
            )

        raw_tasks = cell_data.get("tasks", []) if isinstance(cell_data, dict) else []
        matching_task = None
        for t in raw_tasks:
            if isinstance(t, dict) and t.get("id") == task_id:
                matching_task = t
                break

        bt_rel_path = (
            str(matching_task.get("behavior_tree", "behavior_tree.xml"))
            if matching_task
            else "behavior_tree.xml"
        )

        if isinstance(tree, str):
            try:
                tree_model = self.parse_task_xml(tree, spec_map)
                xml_text = tree
            except Exception as e:
                return TaskEditResult(
                    contents=None,
                    task_id=task_id,
                    validation=(
                        ValidationItem(
                            code="studio.task.xml_invalid",
                            severity="error",
                            path=f"{root / bt_rel_path}#",
                            message=f"Invalid task XML: {e}",
                        ),
                    ),
                )
        else:
            tree_model = tree
            xml_text = self.generate_task_xml(tree_model, include_layout=True)

        findings = self.validate_tree(
            tree_model,
            spec_map,
            source_path=str(root / bt_rel_path),
        )

        if any(f.severity == "error" for f in findings):
            return TaskEditResult(
                contents=None,
                task_id=task_id,
                validation=findings,
                tree=tree_model,
            )

        # Stage updated XML in artifacts
        new_artifacts = dict(contents.artifacts)
        new_artifacts[bt_rel_path] = xml_text.encode("utf-8")

        new_contents = ProjectContents(
            cell_yaml=contents.cell_yaml,
            scene_usda=contents.scene_usda,
            artifacts=new_artifacts,
        )

        return TaskEditResult(
            contents=new_contents,
            task_id=task_id,
            validation=findings,
            tree=tree_model,
        )
