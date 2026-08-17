"""Validate repository example documents and their Task 003 cross-file references."""

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

from cellforge_domain.base import DomainModel
from cellforge_domain.findings import FindingSeverity, SourceLoadError, ValidationFinding
from cellforge_domain.loading import load_document
from cellforge_domain.models import CellProject, ComponentType, DeploymentProfile, Recipe, Scenario
from cellforge_domain.schemas import (
    DRAFT_2020_12,
    SchemaDocumentKind,
    SchemaRegistry,
    SchemaRegistryError,
)


@dataclass(frozen=True, slots=True)
class ExampleValidationReport:
    """Deterministic summary for CI, Make, and future CLI callers."""

    documents_checked: int
    auxiliary_schemas_checked: int
    findings: tuple[ValidationFinding, ...]

    @property
    def is_valid(self) -> bool:
        return not self.findings


_MODEL_BY_KIND: dict[SchemaDocumentKind, type[DomainModel]] = {
    SchemaDocumentKind.COMPONENT: ComponentType,
    SchemaDocumentKind.CELL: CellProject,
    SchemaDocumentKind.RECIPE: Recipe,
    SchemaDocumentKind.SCENARIO: Scenario,
    SchemaDocumentKind.DEPLOYMENT_PROFILE: DeploymentProfile,
}


def _source_path(source: Path, *parts: str | int) -> str:
    if not parts:
        return f"{source.resolve()}#"
    pointer = "/".join(str(part).replace("~", "~0").replace("/", "~1") for part in parts)
    return f"{source.resolve()}#/{pointer}"


def _classify_document(path: Path) -> SchemaDocumentKind | None:
    if path.name == "component.yaml":
        return SchemaDocumentKind.COMPONENT
    if path.name == "cell.yaml":
        return SchemaDocumentKind.CELL
    if path.parent.name == "scenarios":
        return SchemaDocumentKind.SCENARIO
    if path.name.startswith("deployment"):
        return SchemaDocumentKind.DEPLOYMENT_PROFILE
    if path.name.startswith("recipe") or path.parent.name == "recipes":
        return SchemaDocumentKind.RECIPE
    return None


def _load_checked_document(
    source: Path,
    kind: SchemaDocumentKind,
    registry: SchemaRegistry,
) -> tuple[DomainModel | None, tuple[ValidationFinding, ...]]:
    try:
        document = load_document(
            source,
            _MODEL_BY_KIND[kind],
            schema_registry=registry,
            schema_kind=kind,
        )
    except SourceLoadError as error:
        if error.findings:
            return None, error.findings
        return None, (
            ValidationFinding(
                code=error.code,
                severity=FindingSeverity.ERROR,
                path=f"{error.source_path}#",
                message=error.message,
            ),
        )
    return document, ()


def validate_example_tree(
    example_directory: str | Path,
    registry: SchemaRegistry,
) -> ExampleValidationReport:
    """Validate every example YAML plus recipe/deployment references from each cell."""

    root = Path(example_directory).resolve()
    findings: list[ValidationFinding] = []
    documents: dict[Path, DomainModel] = {}

    yaml_paths = sorted((*root.rglob("*.yaml"), *root.rglob("*.yml")))
    for source in yaml_paths:
        kind = _classify_document(source)
        if kind is None:
            findings.append(
                ValidationFinding(
                    code="example.unclassified-document",
                    severity=FindingSeverity.ERROR,
                    path=_source_path(source),
                    message="Example YAML does not map to a registered document schema.",
                )
            )
            continue
        document, document_findings = _load_checked_document(source, kind, registry)
        findings.extend(document_findings)
        if document is not None:
            documents[source.resolve()] = document

    auxiliary_schemas_checked = 0
    for schema_path in sorted(root.rglob("config.schema.json")):
        auxiliary_schemas_checked += 1
        findings.extend(_validate_auxiliary_schema(schema_path))

    for cell_path, document in sorted(documents.items(), key=lambda item: str(item[0])):
        if isinstance(document, CellProject):
            findings.extend(_validate_cell_references(cell_path, document, documents, registry))

    return ExampleValidationReport(
        documents_checked=len(yaml_paths),
        auxiliary_schemas_checked=auxiliary_schemas_checked,
        findings=tuple(
            sorted(findings, key=lambda finding: (finding.path, finding.code, finding.message))
        ),
    )


def _validate_auxiliary_schema(schema_path: Path) -> tuple[ValidationFinding, ...]:
    try:
        document = json.loads(schema_path.read_text(encoding="utf-8"))
        if not isinstance(document, dict):
            raise ValueError("Schema root must be an object.")
        if document.get("$schema") != DRAFT_2020_12:
            raise ValueError("Schema does not declare Draft 2020-12.")
        Draft202012Validator.check_schema(document)
    except (OSError, json.JSONDecodeError, SchemaError, ValueError) as error:
        return (
            ValidationFinding(
                code="schema.invalid",
                severity=FindingSeverity.ERROR,
                path=_source_path(schema_path),
                message=f"Invalid Draft 2020-12 schema: {error}",
            ),
        )
    return ()


def _validate_cell_references(
    cell_path: Path,
    cell: CellProject,
    documents: dict[Path, DomainModel],
    registry: SchemaRegistry,
) -> tuple[ValidationFinding, ...]:
    findings: list[ValidationFinding] = []
    for index, binding in enumerate(cell.recipes):
        recipe_path = (cell_path.parent / binding.path).resolve()
        schema_path = (cell_path.parent / binding.schema_).resolve()
        schema_key = registry.key_for_path(schema_path)
        if schema_key is None or schema_key.kind is not SchemaDocumentKind.RECIPE:
            findings.append(
                ValidationFinding(
                    code="reference.recipe-schema-not-registered",
                    severity=FindingSeverity.ERROR,
                    path=_source_path(cell_path, "recipes", index, "schema"),
                    message=(
                        "Recipe schema reference does not resolve to a registered recipe schema."
                    ),
                )
            )
        recipe = documents.get(recipe_path)
        if not isinstance(recipe, Recipe):
            findings.append(
                ValidationFinding(
                    code="reference.recipe-not-found",
                    severity=FindingSeverity.ERROR,
                    path=_source_path(cell_path, "recipes", index, "path"),
                    message=f"Recipe reference does not resolve to a valid recipe: {binding.path}",
                )
            )
            continue
        if schema_key is not None and schema_key.version != recipe.schema_version:
            findings.append(
                ValidationFinding(
                    code="reference.recipe-schema-version-mismatch",
                    severity=FindingSeverity.ERROR,
                    path=_source_path(cell_path, "recipes", index, "schema"),
                    message=(
                        "Recipe schema reference version does not match the recipe schema_version."
                    ),
                )
            )
        if cell.cell.id not in recipe.compatibility.cell_ids:
            findings.append(
                ValidationFinding(
                    code="reference.recipe-cell-incompatible",
                    severity=FindingSeverity.ERROR,
                    path=_source_path(recipe_path, "compatibility", "cell_ids"),
                    message=f"Recipe does not declare compatibility with cell '{cell.cell.id}'.",
                )
            )

    for index, reference in enumerate(cell.deployment_profiles):
        deployment_path = (cell_path.parent / reference).resolve()
        if not isinstance(documents.get(deployment_path), DeploymentProfile):
            findings.append(
                ValidationFinding(
                    code="reference.deployment-profile-not-found",
                    severity=FindingSeverity.ERROR,
                    path=_source_path(cell_path, "deployment_profiles", index),
                    message=(
                        "Deployment profile reference does not resolve to a valid profile: "
                        f"{reference}"
                    ),
                )
            )
    return tuple(findings)


def format_finding(finding: ValidationFinding) -> str:
    """Render the required file, data path, schema rule/code, and human message."""

    return f"{finding.path} rule={finding.code} message={finding.message}"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--schemas", type=Path, required=True, help="Directory of canonical schemas"
    )
    parser.add_argument("--examples", type=Path, required=True, help="Example project directory")
    arguments = parser.parse_args(argv)

    try:
        registry = SchemaRegistry.from_directory(arguments.schemas)
    except SchemaRegistryError as error:
        print(
            f"{error.source_path.resolve()}# rule=schema.registry message={error.message}",
            file=sys.stderr,
        )
        return 1

    report = validate_example_tree(arguments.examples, registry)
    if report.findings:
        for finding in report.findings:
            print(format_finding(finding), file=sys.stderr)
        return 1

    print(
        f"Validated {len(registry)} canonical schemas, {report.auxiliary_schemas_checked} "
        f"component config schemas, and {report.documents_checked} example YAML documents."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
