"""Headless USDA scene inspection and YAML/USD instance cross-reference validation."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Any

from cellforge.studio.application import ValidationItem

_PRIM_DEFINITION = re.compile(r'\b(?:def|over|class)\s+\w+\s+"([^"]+)"')
_INSTANCE_ATTRIBUTE = re.compile(r'\b(?:custom\s+)?string\s+cellforge:instanceId\s*=\s*"([^"]+)"')


@dataclass(frozen=True, slots=True)
class ScenePrim:
    """One composed prim identity needed by the project linker."""

    path: str
    instance_id: str | None


@dataclass(frozen=True, slots=True)
class SceneInspection:
    """Deterministic scene inventory independent of Kit UI state."""

    prims: tuple[ScenePrim, ...]


def inspect_scene(
    text: str, source: Path
) -> tuple[SceneInspection | None, tuple[ValidationItem, ...]]:
    """Use OpenUSD when installed, with a deterministic USDA fallback for headless CI."""

    try:
        sdf = import_module("pxr.Sdf")
        usd = import_module("pxr.Usd")
    except ImportError:
        return inspect_usda(text, source)

    try:
        layer = sdf.Layer.CreateAnonymous("cellforge-project-scene.usda")
        if not layer.ImportFromString(text):
            raise ValueError
        stage = usd.Stage.Open(layer)
        if stage is None:
            raise ValueError
        prims = tuple(
            ScenePrim(
                path=str(prim.GetPath()),
                instance_id=(
                    str(prim.GetAttribute("cellforge:instanceId").Get())
                    if prim.HasAttribute("cellforge:instanceId")
                    else None
                ),
            )
            for prim in stage.Traverse()
        )
    except Exception:
        return None, (
            _finding(
                "studio.scene-invalid",
                source,
                "OpenUSD could not compose the candidate USDA scene.",
            ),
        )
    return SceneInspection(prims=prims), ()


def inspect_usda(
    text: str, source: Path
) -> tuple[SceneInspection | None, tuple[ValidationItem, ...]]:
    """Inspect the subset of USDA needed to link component prims and immutable IDs."""

    if not text.lstrip().startswith("#usda"):
        return None, (
            _finding(
                "studio.scene-invalid",
                source,
                "Scene is not a text USDA stage with a #usda header.",
            ),
        )

    depth = 0
    stack: list[tuple[str, int]] = []
    prims: list[ScenePrim] = []
    pending_prim: str | None = None
    for line in text.splitlines():
        definition = _PRIM_DEFINITION.search(line)
        current_index: int | None = None
        if definition is not None:
            parent = stack[-1][0] if stack else ""
            path = f"{parent}/{definition.group(1)}"
            current_index = len(prims)
            prims.append(ScenePrim(path=path, instance_id=None))

        attribute = _INSTANCE_ATTRIBUTE.search(line)
        if attribute is not None:
            target = current_index if current_index is not None else len(prims) - 1
            if target < 0 or (current_index is None and not stack):
                return None, (
                    _finding(
                        "studio.scene-instance-id-orphan",
                        source,
                        "A cellforge:instanceId attribute is not authored inside a prim.",
                    ),
                )
            prim = prims[target]
            prims[target] = ScenePrim(path=prim.path, instance_id=attribute.group(1))

        opens = line.count("{")
        closes = line.count("}")
        if definition is not None and opens > closes:
            assert current_index is not None
            stack.append((prims[current_index].path, depth + 1))
            pending_prim = None
        elif definition is not None:
            assert current_index is not None
            pending_prim = prims[current_index].path
        elif pending_prim is not None and opens > closes:
            stack.append((pending_prim, depth + 1))
            pending_prim = None
        depth += opens - closes
        while stack and depth < stack[-1][1]:
            stack.pop()
        if depth < 0:
            return None, (
                _finding(
                    "studio.scene-invalid",
                    source,
                    "Scene contains unbalanced prim braces.",
                ),
            )

    if depth != 0 or stack:
        return None, (
            _finding(
                "studio.scene-invalid",
                source,
                "Scene contains unbalanced prim braces.",
            ),
        )
    return SceneInspection(prims=tuple(prims)), ()


def validate_scene_cross_references(
    cell: Mapping[str, Any],
    scene: SceneInspection,
    *,
    cell_path: Path,
    scene_path: Path,
) -> tuple[ValidationItem, ...]:
    """Validate immutable component IDs and prim paths across both canonical artifacts."""

    findings: list[ValidationItem] = []
    raw_components = cell.get("components", [])
    components = raw_components if isinstance(raw_components, Sequence) else []
    operational: list[tuple[int, str, str]] = []
    for index, raw in enumerate(components):
        if not isinstance(raw, Mapping):
            continue
        instance_id = raw.get("id")
        prim_path = raw.get("usd_prim")
        if isinstance(instance_id, str) and isinstance(prim_path, str):
            operational.append((index, instance_id, prim_path.rstrip("/")))

    for duplicate in _duplicates(item[1] for item in operational):
        findings.append(
            _finding(
                "studio.instance-id-duplicate",
                cell_path,
                f"Component instance ID '{duplicate}' appears more than once in cell.yaml.",
                fragment="/components",
            )
        )

    prim_by_path = {prim.path.rstrip("/"): prim for prim in scene.prims}
    tagged = [prim for prim in scene.prims if prim.instance_id is not None]
    for duplicate in _duplicates(
        prim.instance_id for prim in tagged if prim.instance_id is not None
    ):
        findings.append(
            _finding(
                "studio.scene-instance-id-duplicate",
                scene_path,
                f"USD instance ID '{duplicate}' is authored on more than one prim.",
            )
        )

    operational_ids = {item[1] for item in operational}
    for index, instance_id, prim_path in operational:
        prim = prim_by_path.get(prim_path)
        if prim is None:
            findings.append(
                _finding(
                    "studio.scene-prim-missing",
                    cell_path,
                    f"Component '{instance_id}' references missing USD prim '{prim_path}'.",
                    fragment=f"/components/{index}/usd_prim",
                )
            )
        elif prim.instance_id is None:
            findings.append(
                _finding(
                    "studio.scene-instance-id-missing",
                    scene_path,
                    f"USD prim '{prim_path}' has no cellforge:instanceId for '{instance_id}'.",
                    fragment=prim_path,
                )
            )
        elif prim.instance_id != instance_id:
            findings.append(
                _finding(
                    "studio.scene-instance-id-mismatch",
                    scene_path,
                    (
                        f"USD prim '{prim_path}' carries instance ID '{prim.instance_id}', "
                        f"but cell.yaml assigns '{instance_id}'."
                    ),
                    fragment=prim_path,
                )
            )

    for prim in tagged:
        if prim.instance_id not in operational_ids:
            findings.append(
                _finding(
                    "studio.scene-instance-unreferenced",
                    scene_path,
                    (
                        f"USD prim '{prim.path}' carries instance ID '{prim.instance_id}' "
                        "that is not declared in cell.yaml."
                    ),
                    fragment=prim.path,
                )
            )
    return tuple(sorted(findings, key=lambda item: (item.path, item.code, item.message)))


def _duplicates(values: Iterable[str]) -> set[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return duplicates


def _finding(
    code: str,
    source: Path,
    message: str,
    *,
    fragment: str = "",
) -> ValidationItem:
    suffix = f"#{fragment}" if fragment else "#"
    return ValidationItem(
        code=code,
        severity="error",
        path=f"{source.resolve()}{suffix}",
        message=message,
    )
