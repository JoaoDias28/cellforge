"""Draft 2020-12 schema registry and instance validation."""

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

from cellforge_domain.findings import FindingSeverity, ValidationFinding

DRAFT_2020_12 = "https://json-schema.org/draft/2020-12/schema"


class SchemaDocumentKind(StrEnum):
    """Canonical document families backed by repository schemas."""

    COMPONENT = "component"
    CELL = "cell"
    RECIPE = "recipe"
    SCENARIO = "scenario"
    DEPLOYMENT_PROFILE = "deployment-profile"
    CAPABILITY_CONTRACT = "capability-contract"
    SKILL = "skill"
    FAULT_CATALOG = "fault-catalog"
    CALIBRATION = "calibration"
    EVIDENCE = "evidence"


_MODEL_KIND_BY_NAME: dict[str, SchemaDocumentKind] = {
    "ComponentType": SchemaDocumentKind.COMPONENT,
    "CellProject": SchemaDocumentKind.CELL,
    "Recipe": SchemaDocumentKind.RECIPE,
    "Scenario": SchemaDocumentKind.SCENARIO,
    "DeploymentProfile": SchemaDocumentKind.DEPLOYMENT_PROFILE,
}


def schema_kind_for_model(model_type: type[object]) -> SchemaDocumentKind:
    """Return the canonical schema kind associated with a public domain model."""

    try:
        return _MODEL_KIND_BY_NAME[model_type.__name__]
    except KeyError:
        raise TypeError(
            f"No document schema is registered for model {model_type.__name__}."
        ) from None


_SCHEMA_FILENAMES: dict[SchemaDocumentKind, str] = {
    SchemaDocumentKind.COMPONENT: "component.schema.json",
    SchemaDocumentKind.CELL: "cell.schema.json",
    SchemaDocumentKind.RECIPE: "recipe.schema.json",
    SchemaDocumentKind.SCENARIO: "scenario.schema.json",
    SchemaDocumentKind.DEPLOYMENT_PROFILE: "deployment-profile.schema.json",
    SchemaDocumentKind.CAPABILITY_CONTRACT: "capability-contract.schema.json",
    SchemaDocumentKind.SKILL: "skill.schema.json",
    SchemaDocumentKind.FAULT_CATALOG: "fault-catalog.schema.json",
    SchemaDocumentKind.CALIBRATION: "calibration.schema.json",
    SchemaDocumentKind.EVIDENCE: "evidence.schema.json",
}

# Diagnostic/report contracts are validated by their owning application service and are not
# document kinds that Cell Runtime loads as canonical project schemas.
_AUXILIARY_SCHEMA_FILENAMES = frozenset({"studio_project_preview.schema.json"})


@dataclass(frozen=True, slots=True)
class SchemaKey:
    """Collision-free schema key for one document family and version."""

    kind: SchemaDocumentKind
    version: str


@dataclass(frozen=True, slots=True)
class RegisteredSchema:
    """One checked schema and its reusable validator."""

    key: SchemaKey
    path: Path
    identifier: str
    document: Mapping[str, Any]
    validator: Draft202012Validator


class SchemaRegistryError(Exception):
    """A source-aware failure while building a schema registry."""

    def __init__(self, source_path: Path, message: str) -> None:
        self.source_path = source_path
        self.message = message
        super().__init__(f"{source_path}: {message}")


def _json_pointer(source_path: Path, parts: Sequence[str | int]) -> str:
    if not parts:
        return f"{source_path}#"
    pointer = "/".join(str(part).replace("~", "~0").replace("/", "~1") for part in parts)
    return f"{source_path}#/{pointer}"


def _rule_code(keyword: object) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", str(keyword).lower()).strip("-")
    return f"schema.{normalized or 'invalid'}"


class SchemaRegistry:
    """Explicit registry of checked Draft 2020-12 schemas."""

    def __init__(self, schemas: Mapping[SchemaKey, RegisteredSchema]) -> None:
        self._schemas = dict(schemas)
        self._paths = {schema.path: schema.key for schema in schemas.values()}

    @classmethod
    def from_directory(cls, schema_directory: str | Path) -> "SchemaRegistry":
        """Load and meta-validate every JSON schema in ``schema_directory``."""

        directory = Path(schema_directory).resolve()
        expected_by_name = {filename: kind for kind, filename in _SCHEMA_FILENAMES.items()}
        schemas: dict[SchemaKey, RegisteredSchema] = {}
        found_kinds: set[SchemaDocumentKind] = set()

        try:
            schema_paths = sorted(directory.glob("*.json"))
        except OSError as error:
            raise SchemaRegistryError(directory, "Could not enumerate schema directory.") from error

        for schema_path in schema_paths:
            kind = expected_by_name.get(schema_path.name)
            if kind is None:
                if schema_path.name in _AUXILIARY_SCHEMA_FILENAMES:
                    _load_schema(schema_path)
                    continue
                raise SchemaRegistryError(
                    schema_path, "Schema filename is not registered to a document kind."
                )
            document = _load_schema(schema_path)
            version = _schema_version(schema_path, document)
            identifier = document.get("$id")
            if not isinstance(identifier, str) or not identifier:
                raise SchemaRegistryError(schema_path, "Schema must declare a non-empty '$id'.")

            key = SchemaKey(kind=kind, version=version)
            if key in schemas:
                raise SchemaRegistryError(schema_path, f"Duplicate schema registry key {key!r}.")
            schemas[key] = RegisteredSchema(
                key=key,
                path=schema_path.resolve(),
                identifier=identifier,
                document=document,
                validator=Draft202012Validator(document),
            )
            found_kinds.add(kind)

        missing = set(_SCHEMA_FILENAMES) - found_kinds
        if missing:
            names = ", ".join(
                _SCHEMA_FILENAMES[kind] for kind in sorted(missing, key=lambda item: item.value)
            )
            raise SchemaRegistryError(directory, f"Required schemas are missing: {names}.")
        return cls(schemas)

    def __len__(self) -> int:
        return len(self._schemas)

    @property
    def keys(self) -> tuple[SchemaKey, ...]:
        """Return deterministic registry keys."""

        return tuple(sorted(self._schemas, key=lambda key: (key.kind.value, key.version)))

    def get(self, kind: SchemaDocumentKind, version: str) -> RegisteredSchema:
        """Return the registered schema for an exact document kind and version."""

        return self._schemas[SchemaKey(kind=kind, version=version)]

    def key_for_path(self, schema_path: str | Path) -> SchemaKey | None:
        """Resolve a source schema path back to its registry key, if registered."""

        return self._paths.get(Path(schema_path).resolve())

    def validate(
        self,
        kind: SchemaDocumentKind,
        instance: Mapping[str, Any],
        source_path: str | Path,
    ) -> tuple[ValidationFinding, ...]:
        """Validate a JSON-compatible mapping and return every sorted finding."""

        resolved_source = Path(source_path).resolve()
        version = instance.get("schema_version")
        if not isinstance(version, str):
            return (
                ValidationFinding(
                    code="schema.version-not-registered",
                    severity=FindingSeverity.ERROR,
                    path=_json_pointer(resolved_source, ("schema_version",)),
                    message="Document schema_version must be a registered string value.",
                ),
            )

        try:
            registered = self.get(kind, version)
        except KeyError:
            return (
                ValidationFinding(
                    code="schema.version-not-registered",
                    severity=FindingSeverity.ERROR,
                    path=_json_pointer(resolved_source, ("schema_version",)),
                    message=(
                        f"No {kind.value} schema is registered for schema_version '{version}'."
                    ),
                ),
            )

        errors = sorted(
            registered.validator.iter_errors(instance),
            key=lambda error: (tuple(str(part) for part in error.absolute_path), error.message),
        )
        return tuple(
            ValidationFinding(
                code=_rule_code(error.validator),
                severity=FindingSeverity.ERROR,
                path=_json_pointer(resolved_source, tuple(error.absolute_path)),
                message=error.message,
            )
            for error in errors
        )


def _load_schema(schema_path: Path) -> Mapping[str, Any]:
    try:
        raw_document = json.loads(schema_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SchemaRegistryError(schema_path, "Could not read valid schema JSON.") from error
    if not isinstance(raw_document, Mapping):
        raise SchemaRegistryError(schema_path, "Schema root must be a JSON object.")
    document = dict(raw_document)
    if document.get("$schema") != DRAFT_2020_12:
        raise SchemaRegistryError(
            schema_path, f"Schema must declare JSON Schema Draft 2020-12 as '{DRAFT_2020_12}'."
        )
    try:
        Draft202012Validator.check_schema(document)
    except SchemaError as error:
        raise SchemaRegistryError(
            schema_path, f"Invalid Draft 2020-12 schema: {error.message}"
        ) from error
    return document


def _schema_version(schema_path: Path, document: Mapping[str, Any]) -> str:
    properties = document.get("properties")
    version_schema = properties.get("schema_version") if isinstance(properties, Mapping) else None
    version = version_schema.get("const") if isinstance(version_schema, Mapping) else None
    if not isinstance(version, str) or not version:
        raise SchemaRegistryError(
            schema_path, "Schema must declare properties.schema_version.const as a string."
        )
    return version
