"""Pure schema-driven authoring for CellForge canonical engineering documents.

The service in this module owns schema interpretation, validation, deterministic defaults,
source/form reconciliation, and the explicit Save-after-preview boundary.  A Kit widget may
render the immutable DTOs but never needs to know JSON Schema rules or recipe/simulation policy.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

import yaml
from cellforge_domain import CellProject, Recipe, Scenario
from cellforge_domain.schemas import DRAFT_2020_12, SchemaDocumentKind
from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError
from pydantic import ValidationError

from cellforge.studio.application import ProjectContents

_MISSING = object()
_AUTHORING_VERSION = "0.1.0"
_KNOWN_PRESENTATION_KEYS = frozenset(
    {"label", "group", "order", "unit", "help", "advanced", "generated"}
)

# Draft 2020-12 keywords.  Annotation keywords are intentionally included separately so a
# misspelled validation keyword is reported instead of being silently ignored by jsonschema.
_KNOWN_SCHEMA_KEYWORDS = frozenset(
    {
        "$schema",
        "$id",
        "$anchor",
        "$ref",
        "$dynamicRef",
        "$defs",
        "$dynamicAnchor",
        "$comment",
        "title",
        "description",
        "default",
        "deprecated",
        "readOnly",
        "writeOnly",
        "examples",
        "type",
        "enum",
        "const",
        "multipleOf",
        "maximum",
        "exclusiveMaximum",
        "minimum",
        "exclusiveMinimum",
        "maxLength",
        "minLength",
        "pattern",
        "maxItems",
        "minItems",
        "uniqueItems",
        "maxContains",
        "minContains",
        "maxProperties",
        "minProperties",
        "required",
        "dependentRequired",
        "prefixItems",
        "items",
        "contains",
        "properties",
        "patternProperties",
        "additionalProperties",
        "propertyNames",
        "dependencies",
        "if",
        "then",
        "else",
        "allOf",
        "anyOf",
        "oneOf",
        "not",
        "unevaluatedItems",
        "unevaluatedProperties",
        "format",
        "contentEncoding",
        "contentMediaType",
        "contentSchema",
        "x-cellforge",
    }
)
_KNOWN_SCHEMA_DOCUMENT_KINDS = {item.value for item in SchemaDocumentKind}
_RELEASED_RECIPE_STATUSES = frozenset({"APPROVED", "RETIRED"})
_LIFECYCLE_STATUSES = frozenset({"DRAFT", "VALIDATED", "TESTED", "APPROVED", "RETIRED"})


@dataclass(frozen=True, slots=True)
class AuthoringFinding:
    """One structured, source-addressable schema authoring finding."""

    code: str
    severity: str
    path: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "severity": self.severity,
            "path": self.path,
            "message": self.message,
        }


@dataclass(frozen=True, slots=True)
class AuthoringChoice:
    """A required explicit choice left unresolved by deterministic form generation."""

    key: str
    prompt: str
    options: tuple[str, ...]
    reason: str
    source: str

    def as_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "prompt": self.prompt,
            "options": list(self.options),
            "reason": self.reason,
            "source": self.source,
        }


@dataclass(frozen=True, slots=True)
class SchemaFormField:
    """Presentation metadata for one JSON-pointer-addressable schema field."""

    path: str
    name: str
    label: str
    group: str
    order: int
    field_type: str
    widget: str
    value: Any = None
    required: bool = False
    advanced: bool = False
    generated: bool = False
    unit: str | None = None
    minimum: float | int | None = None
    maximum: float | int | None = None
    exclusive_minimum: float | int | bool | None = None
    exclusive_maximum: float | int | bool | None = None
    enum: tuple[Any, ...] = ()
    const: Any = None
    description: str | None = None
    help: str | None = None
    schema_path: str = ""
    item_schema_path: str | None = None

    @property
    def choices(self) -> tuple[Any, ...]:
        """Compatibility-friendly alias for enum presentation values."""

        return self.enum

    def as_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "name": self.name,
            "label": self.label,
            "group": self.group,
            "order": self.order,
            "field_type": self.field_type,
            "widget": self.widget,
            "value": _json_value(self.value),
            "required": self.required,
            "advanced": self.advanced,
            "generated": self.generated,
            "unit": self.unit,
            "minimum": self.minimum,
            "maximum": self.maximum,
            "exclusive_minimum": self.exclusive_minimum,
            "exclusive_maximum": self.exclusive_maximum,
            "enum": [_json_value(item) for item in self.enum],
            "const": _json_value(self.const),
            "description": self.description,
            "help": self.help,
            "schema_path": self.schema_path,
            "item_schema_path": self.item_schema_path,
        }


@dataclass(frozen=True, slots=True)
class SchemaFormGroup:
    """Stable field grouping returned to reusable renderers."""

    name: str
    order: int
    fields: tuple[SchemaFormField, ...]
    advanced: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "order": self.order,
            "advanced": self.advanced,
            "fields": [field.as_dict() for field in self.fields],
        }


@dataclass(frozen=True, slots=True)
class SchemaFormModel:
    """Complete immutable schema form model; all validation remains service-owned."""

    schema_path: str
    schema_kind: str
    schema_version: str | None
    title: str
    source_path: str
    source_format: str
    encoding: str
    fields: tuple[SchemaFormField, ...]
    groups: tuple[SchemaFormGroup, ...]
    values: Mapping[str, Any]
    base_values: Mapping[str, Any]
    source_values: Mapping[str, Any]
    choices: tuple[AuthoringChoice, ...] = ()
    generated_paths: tuple[str, ...] = ()
    findings: tuple[AuthoringFinding, ...] = ()
    allocator_seed: str = ""
    source_text: str = ""
    source_bytes: bytes = b""
    base_source_hash: str = ""
    project_path: str | None = None
    artifact_path: str | None = None
    schema_document: Mapping[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @property
    def required_choices(self) -> tuple[AuthoringChoice, ...]:
        """Compatibility alias used by Studio panels."""

        return self.choices

    @property
    def can_save(self) -> bool:
        return not self.choices and not any(item.severity == "error" for item in self.findings)

    def as_dict(self) -> dict[str, object]:
        return {
            "authoring_schema_version": _AUTHORING_VERSION,
            "schema_path": self.schema_path,
            "schema_kind": self.schema_kind,
            "schema_version": self.schema_version,
            "title": self.title,
            "source_path": self.source_path,
            "source_format": self.source_format,
            "encoding": self.encoding,
            "fields": [field.as_dict() for field in self.fields],
            "groups": [group.as_dict() for group in self.groups],
            "values": _json_value(self.values),
            "choices": [choice.as_dict() for choice in self.choices],
            "generated_paths": list(self.generated_paths),
            "findings": [finding.as_dict() for finding in self.findings],
            "can_save": self.can_save,
        }


@dataclass(frozen=True, slots=True)
class AuthoringDiffEntry:
    """One exact deterministic JSON-pointer difference."""

    path: str
    operation: str
    old_value: Any = None
    new_value: Any = None

    @property
    def before(self) -> Any:
        return self.old_value

    @property
    def after(self) -> Any:
        return self.new_value

    @property
    def change_type(self) -> str:
        return self.operation

    def as_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "operation": self.operation,
            "old_value": _json_value(self.old_value),
            "new_value": _json_value(self.new_value),
        }


@dataclass(frozen=True, slots=True)
class AuthoringCandidate:
    """A validated in-memory source/form candidate awaiting explicit Save."""

    candidate_id: str
    schema_path: str
    schema_kind: str
    schema_version: str | None
    source_path: str
    source_format: str
    encoding: str
    original_text: str
    source_text: str
    canonical_text: str
    original_bytes: bytes
    original_value: Mapping[str, Any]
    source_value: Mapping[str, Any] | None
    form_value: Mapping[str, Any]
    canonical_value: Mapping[str, Any]
    base_source_hash: str
    source_hash: str
    canonical_hash: str
    diff: tuple[AuthoringDiffEntry, ...] = ()
    choices: tuple[AuthoringChoice, ...] = ()
    generated_paths: tuple[str, ...] = ()
    findings: tuple[AuthoringFinding, ...] = ()
    can_save: bool = False
    confirmation_token: str = ""
    project_path: str | None = None
    artifact_path: str | None = None
    released_recipe: bool = False
    formatting_changed: bool = False
    schema_document: Mapping[str, Any] = field(default_factory=dict, repr=False, compare=False)
    project_contents: ProjectContents | None = field(default=None, repr=False, compare=False)

    @property
    def save_token(self) -> str:
        return self.confirmation_token

    @property
    def validation(self) -> tuple[AuthoringFinding, ...]:
        return self.findings

    @property
    def source_encoding(self) -> str:
        return self.encoding

    @property
    def source_changed(self) -> bool:
        return self.source_hash != self.base_source_hash

    def as_dict(self) -> dict[str, object]:
        return {
            "authoring_schema_version": _AUTHORING_VERSION,
            "candidate_id": self.candidate_id,
            "schema_path": self.schema_path,
            "schema_kind": self.schema_kind,
            "schema_version": self.schema_version,
            "source_path": self.source_path,
            "source_format": self.source_format,
            "encoding": self.encoding,
            "original_sha256": self.base_source_hash,
            "source_sha256": self.source_hash,
            "canonical_sha256": self.canonical_hash,
            "source_value": _json_value(self.source_value),
            "form_value": _json_value(self.form_value),
            "canonical_value": _json_value(self.canonical_value),
            "diff": [entry.as_dict() for entry in self.diff],
            "choices": [choice.as_dict() for choice in self.choices],
            "generated_paths": list(self.generated_paths),
            "findings": [finding.as_dict() for finding in self.findings],
            "can_save": self.can_save,
            "confirmation_token": self.confirmation_token,
            "project_path": self.project_path,
            "artifact_path": self.artifact_path,
            "released_recipe": self.released_recipe,
            "formatting_changed": self.formatting_changed,
        }


@dataclass(frozen=True, slots=True)
class AuthoringSaveResult:
    """Explicit Save-after-preview outcome with source hashes before and after."""

    success: bool
    candidate: AuthoringCandidate
    findings: tuple[AuthoringFinding, ...] = ()
    message: str = ""
    source_hashes_before: Mapping[str, str] = field(default_factory=dict)
    source_hashes_after: Mapping[str, str] = field(default_factory=dict)
    contents: ProjectContents | None = None

    @property
    def validation(self) -> tuple[AuthoringFinding, ...]:
        return self.findings

    def as_dict(self) -> dict[str, object]:
        return {
            "success": self.success,
            "candidate": self.candidate.as_dict(),
            "findings": [finding.as_dict() for finding in self.findings],
            "message": self.message,
            "source_hashes_before": dict(sorted(self.source_hashes_before.items())),
            "source_hashes_after": dict(sorted(self.source_hashes_after.items())),
        }


class SchemaAuthoringService:
    """Pure form/source authoring service with an explicit canonical Save boundary."""

    def __init__(
        self,
        canonical_schema_directory: Path | None = None,
        *,
        project_service: Any | None = None,
        replace_file: Callable[[str | Path, str | Path], None] = os.replace,
    ) -> None:
        self._canonical_schemas = (
            canonical_schema_directory.resolve() if canonical_schema_directory is not None else None
        )
        self._project_service = project_service
        self._replace_file = replace_file

    def BuildSchemaForm(
        self,
        schema: Mapping[str, Any] | str | Path,
        value: Mapping[str, Any] | None = None,
        *,
        source: str | bytes | Path | None = None,
        source_path: str | Path | None = None,
        schema_kind: str | SchemaDocumentKind | None = None,
        allocator_seed: str | None = None,
        required_choices: Mapping[str, Sequence[str]] | None = None,
        project_path: str | Path | None = None,
        project_contents: ProjectContents | None = None,
        artifact_path: str | None = None,
    ) -> SchemaFormModel:
        """Build a deterministic form model from one Draft 2020-12 schema."""

        schema_document, schema_file, schema_findings = self._load_schema(schema)
        source_file = _resolve_source_path(source_path, project_path, artifact_path)
        if source_file is None and isinstance(source, Path):
            source_file = source.expanduser().resolve()
        source_bytes, source_text, source_encoding, source_findings = self._source_input(
            source,
            source_file,
            project_path=project_path,
            project_contents=project_contents,
            artifact_path=artifact_path,
        )
        source_value: Mapping[str, Any] | None = None
        parse_findings: list[AuthoringFinding] = []
        if source is not None or source_file is not None:
            if source_bytes:
                source_value, parse_findings = _parse_source(
                    source_bytes,
                    source_file or Path("<memory>"),
                    source_encoding,
                )
            elif source_file is not None and not source_file.exists():
                parse_findings.append(
                    _finding(
                        "source.read-failed",
                        source_file,
                        "The authoring source could not be read.",
                    )
                )
        if value is None and source_value is not None:
            value = source_value
        if value is None:
            value = {}
        seed = _allocator_seed(
            allocator_seed,
            schema_kind,
            schema_file,
            source_file,
        )
        effective_source_path = str(source_file or Path("<memory>"))
        effective_format = _source_format(source_file, source)
        effective_encoding = source_encoding or "utf-8"
        effective_bytes = source_bytes or _encode_source(
            value, effective_format, effective_encoding
        )
        effective_text = _decode_bytes(effective_bytes, effective_encoding)
        base_value = dict(source_value) if source_value is not None else dict(value)
        return self._build_form_model(
            schema_document,
            schema_file,
            value,
            base_values=base_value,
            source_values=base_value,
            schema_kind=schema_kind,
            source_path=effective_source_path,
            source_format=effective_format,
            encoding=effective_encoding,
            source_text=effective_text,
            source_bytes=effective_bytes,
            allocator_seed=seed,
            required_choices=required_choices,
            project_path=project_path,
            artifact_path=artifact_path,
            initial_findings=(*schema_findings, *source_findings, *parse_findings),
        )

    def build_schema_form(self, *args: Any, **kwargs: Any) -> SchemaFormModel:
        """Snake-case alias for :meth:`BuildSchemaForm`."""

        return self.BuildSchemaForm(*args, **kwargs)

    def UpdateSchemaForm(
        self,
        form: SchemaFormModel,
        values: Mapping[str, Any] | None = None,
        *,
        changes: Mapping[str, Any] | None = None,
        allocator_seed: str | None = None,
    ) -> SchemaFormModel:
        """Apply field changes to a form and re-run service-owned schema validation."""

        requested = changes if changes is not None else values
        updated = _apply_form_changes(form.values, requested or {})
        return self._build_form_model(
            form.schema_document,
            Path(form.schema_path) if not form.schema_path.startswith("<") else None,
            updated,
            base_values=form.base_values,
            source_values=form.source_values,
            schema_kind=form.schema_kind,
            source_path=form.source_path,
            source_format=form.source_format,
            encoding=form.encoding,
            source_text=form.source_text,
            source_bytes=form.source_bytes,
            allocator_seed=allocator_seed or form.allocator_seed,
            required_choices=None,
            project_path=form.project_path,
            artifact_path=form.artifact_path,
            initial_findings=(),
        )

    def update_schema_form(self, *args: Any, **kwargs: Any) -> SchemaFormModel:
        """Snake-case alias for :meth:`UpdateSchemaForm`."""

        return self.UpdateSchemaForm(*args, **kwargs)

    def PreviewFormEdit(
        self,
        form: SchemaFormModel,
        values: Mapping[str, Any] | None = None,
        *,
        changes: Mapping[str, Any] | None = None,
    ) -> AuthoringCandidate:
        """Create a no-write candidate for a form edit."""

        updated_form = self.UpdateSchemaForm(form, values, changes=changes)
        return self._candidate_from_values(
            schema_document=updated_form.schema_document,
            schema_path=updated_form.schema_path,
            schema_kind=updated_form.schema_kind,
            source_path=updated_form.source_path,
            source_format=updated_form.source_format,
            encoding=updated_form.encoding,
            original_text=updated_form.source_text,
            original_bytes=updated_form.source_bytes,
            original_value=updated_form.base_values,
            source_value=updated_form.source_values,
            form_value=updated_form.values,
            canonical_value=updated_form.values,
            choices=updated_form.choices,
            generated_paths=updated_form.generated_paths,
            initial_findings=updated_form.findings,
            project_path=updated_form.project_path,
            artifact_path=updated_form.artifact_path,
            project_contents=self._project_contents(updated_form),
        )

    def preview_form_edit(self, *args: Any, **kwargs: Any) -> AuthoringCandidate:
        """Snake-case alias for :meth:`PreviewFormEdit`."""

        return self.PreviewFormEdit(*args, **kwargs)

    def PreviewSourceEdit(
        self,
        candidate_or_schema: AuthoringCandidate | SchemaFormModel | Mapping[str, Any] | str | Path,
        source: str | bytes | Path | None = None,
        *,
        schema: Mapping[str, Any] | str | Path | None = None,
        source_path: str | Path | None = None,
        value: Mapping[str, Any] | None = None,
        form: SchemaFormModel | None = None,
        schema_kind: str | SchemaDocumentKind | None = None,
        allocator_seed: str | None = None,
        project_path: str | Path | None = None,
        project_contents: ProjectContents | None = None,
        artifact_path: str | None = None,
    ) -> AuthoringCandidate:
        """Parse, validate, and preview an advanced YAML/JSON source edit."""

        if isinstance(candidate_or_schema, AuthoringCandidate):
            base = candidate_or_schema
            schema_document = base.schema_document
            schema_file = Path(base.schema_path) if not base.schema_path.startswith("<") else None
            effective_source_path = source_path or base.source_path
            source_file = _resolve_source_path(
                effective_source_path,
                project_path or base.project_path,
                artifact_path or base.artifact_path,
            )
            raw_source = source if source is not None else base.source_text
            source_bytes, source_text, encoding, input_findings = self._source_input(
                raw_source,
                source_file,
                project_path=project_path or base.project_path,
                project_contents=project_contents or base.project_contents,
                artifact_path=artifact_path or base.artifact_path,
            )
            parsed, parse_findings = _parse_source(
                source_bytes,
                source_file or Path(base.source_path),
                encoding,
            )
            choices = self._choices_for_value(
                schema_document,
                parsed or {},
                schema_kind=base.schema_kind,
                allocator_seed=allocator_seed or _seed_from_candidate(base),
            )
            return self._candidate_from_values(
                schema_document=schema_document,
                schema_path=base.schema_path,
                schema_kind=base.schema_kind,
                source_path=str(source_file or base.source_path),
                source_format=_source_format(source_file, raw_source, base.source_format),
                encoding=encoding,
                original_text=base.original_text,
                original_bytes=base.original_bytes,
                original_value=base.original_value,
                source_value=parsed,
                form_value=base.form_value,
                canonical_value=parsed or {},
                choices=choices,
                generated_paths=base.generated_paths,
                initial_findings=(
                    *input_findings,
                    *parse_findings,
                    *base.findings,
                ),
                project_path=project_path or base.project_path,
                artifact_path=artifact_path or base.artifact_path,
                project_contents=project_contents or base.project_contents,
                source_text=(
                    None
                    if source is None and parsed is not None and parsed == base.original_value
                    else source_text
                ),
            )

        if isinstance(candidate_or_schema, SchemaFormModel):
            base_form = candidate_or_schema
            schema_document = base_form.schema_document
            schema_file = (
                Path(base_form.schema_path) if not base_form.schema_path.startswith("<") else None
            )
            raw_source = source if source is not None else base_form.source_text
            source_file = _resolve_source_path(
                source_path or base_form.source_path,
                project_path or base_form.project_path,
                artifact_path or base_form.artifact_path,
            )
            source_bytes, source_text, encoding, input_findings = self._source_input(
                raw_source,
                source_file,
                project_path=project_path or base_form.project_path,
                project_contents=project_contents,
                artifact_path=artifact_path or base_form.artifact_path,
            )
            parsed, parse_findings = _parse_source(
                source_bytes,
                source_file or Path(base_form.source_path),
                encoding,
            )
            return self._candidate_from_values(
                schema_document=schema_document,
                schema_path=str(schema_file or base_form.schema_path),
                schema_kind=base_form.schema_kind,
                source_path=str(source_file or base_form.source_path),
                source_format=_source_format(source_file, raw_source, base_form.source_format),
                encoding=encoding,
                original_text=base_form.source_text,
                original_bytes=base_form.source_bytes,
                original_value=base_form.base_values,
                source_value=parsed,
                form_value=base_form.values,
                canonical_value=parsed or {},
                choices=base_form.choices,
                generated_paths=base_form.generated_paths,
                initial_findings=(*input_findings, *parse_findings, *base_form.findings),
                project_path=project_path or base_form.project_path,
                artifact_path=artifact_path or base_form.artifact_path,
                project_contents=project_contents,
                source_text=(
                    None
                    if source is None and parsed is not None and parsed == base_form.base_values
                    else source_text
                ),
            )

        schema_input = schema if schema is not None else candidate_or_schema
        schema_document, schema_file, schema_findings = self._load_schema(schema_input)
        source_file = _resolve_source_path(source_path, project_path, artifact_path)
        source_bytes, source_text, encoding, input_findings = self._source_input(
            source,
            source_file,
            project_path=project_path,
            project_contents=project_contents,
            artifact_path=artifact_path,
        )
        parsed, parse_findings = _parse_source(
            source_bytes,
            source_file or Path("<memory>"),
            encoding,
        )
        if parsed is None and value is not None and isinstance(value, Mapping):
            parsed = dict(value)
        seed = _allocator_seed(allocator_seed, schema_kind, schema_file, source_file)
        base_value = dict(value or (parsed or {}))
        base_form = form or self.BuildSchemaForm(
            schema_document,
            base_value,
            source_path=source_file,
            schema_kind=schema_kind,
            allocator_seed=seed,
            project_path=project_path,
            project_contents=project_contents,
            artifact_path=artifact_path,
        )
        choices = (
            base_form.choices
            if parsed is None
            else self._choices_for_value(
                schema_document, parsed, schema_kind=schema_kind, allocator_seed=seed
            )
        )
        return self._candidate_from_values(
            schema_document=schema_document,
            schema_path=str(schema_file or "<memory>"),
            schema_kind=_kind_name(schema_kind, schema_file),
            source_path=str(source_file or "<memory>"),
            source_format=_source_format(source_file, source),
            encoding=encoding,
            original_text=source_text,
            original_bytes=source_bytes,
            original_value=base_value,
            source_value=parsed,
            form_value=base_form.values,
            canonical_value=parsed or {},
            choices=choices,
            generated_paths=base_form.generated_paths,
            initial_findings=(
                *schema_findings,
                *input_findings,
                *parse_findings,
                *base_form.findings,
            ),
            project_path=project_path,
            artifact_path=artifact_path,
            project_contents=project_contents,
            source_text=source_text,
        )

    def preview_source_edit(self, *args: Any, **kwargs: Any) -> AuthoringCandidate:
        """Snake-case alias for :meth:`PreviewSourceEdit`."""

        return self.PreviewSourceEdit(*args, **kwargs)

    def MergeSourceEdit(
        self,
        form_or_candidate: SchemaFormModel | AuthoringCandidate,
        source_or_candidate: AuthoringCandidate | str | bytes | Path,
        *,
        project_path: str | Path | None = None,
        project_contents: ProjectContents | None = None,
    ) -> AuthoringCandidate:
        """Three-way merge form and source edits, surfacing conflicting paths explicitly."""

        if isinstance(source_or_candidate, AuthoringCandidate):
            source_candidate = source_or_candidate
        else:
            source_candidate = self.PreviewSourceEdit(
                form_or_candidate,
                source_or_candidate,
                project_path=project_path,
                project_contents=project_contents,
            )
        if isinstance(form_or_candidate, SchemaFormModel):
            form = form_or_candidate
            schema_document = form.schema_document
            schema_path = form.schema_path
            schema_kind = form.schema_kind
            original_value = form.base_values
            form_value = form.values
            source_value = source_candidate.source_value
            source_path = source_candidate.source_path
            source_format = source_candidate.source_format
            encoding = source_candidate.encoding
            original_text = form.source_text
            original_bytes = form.source_bytes
            choices = (*form.choices, *source_candidate.choices)
            generated = form.generated_paths
        else:
            base = form_or_candidate
            schema_document = base.schema_document
            schema_path = base.schema_path
            schema_kind = base.schema_kind
            original_value = base.original_value
            form_value = base.form_value
            source_value = source_candidate.source_value
            source_path = source_candidate.source_path
            source_format = source_candidate.source_format
            encoding = source_candidate.encoding
            original_text = base.original_text
            original_bytes = base.original_bytes
            choices = (*base.choices, *source_candidate.choices)
            generated = base.generated_paths
        if source_value is None:
            return replace(
                source_candidate,
                findings=_unique_findings((*source_candidate.findings,)),
                can_save=False,
            )

        merged, conflicts = _three_way_merge(
            original_value,
            form_value,
            source_value,
            path="",
        )
        conflict_findings = tuple(
            _finding(
                "authoring.merge-conflict",
                Path(source_path),
                f"Form and source edits disagree at {path or '/'}; choose one explicitly.",
                pointer=path,
            )
            for path in sorted(conflicts)
        )
        return self._candidate_from_values(
            schema_document=schema_document,
            schema_path=schema_path,
            schema_kind=schema_kind,
            source_path=source_path,
            source_format=source_format,
            encoding=encoding,
            original_text=original_text,
            original_bytes=original_bytes,
            original_value=original_value,
            source_value=source_value,
            form_value=form_value,
            canonical_value=merged,
            choices=choices,
            generated_paths=generated,
            initial_findings=(*source_candidate.findings, *conflict_findings),
            project_path=project_path or source_candidate.project_path,
            artifact_path=source_candidate.artifact_path,
            project_contents=project_contents or source_candidate.project_contents,
            source_text=source_candidate.source_text,
        )

    def merge_source_edit(self, *args: Any, **kwargs: Any) -> AuthoringCandidate:
        """Snake-case alias for :meth:`MergeSourceEdit`."""

        return self.MergeSourceEdit(*args, **kwargs)

    def SaveAuthoringCandidate(
        self,
        candidate: AuthoringCandidate,
        confirmation_token: str | None = None,
        *,
        confirmed: bool = False,
        project_path: str | Path | None = None,
        project_contents: ProjectContents | None = None,
        save_callback: Callable[[AuthoringCandidate], Any] | None = None,
    ) -> AuthoringSaveResult:
        """Persist a confirmed candidate after rechecking its source and full validation."""

        project_root = project_path if project_path is not None else candidate.project_path
        root = Path(project_root).expanduser().resolve() if project_root is not None else None
        before = self._source_hashes(candidate, root)
        guard = self._save_guard(candidate, confirmation_token, confirmed, root)
        if guard is not None:
            return AuthoringSaveResult(
                success=False,
                candidate=candidate,
                findings=(guard,),
                message=guard.message,
                source_hashes_before=before,
                source_hashes_after=self._source_hashes(candidate, root),
            )

        current_candidate = candidate
        current_contents = project_contents or candidate.project_contents
        try:
            if save_callback is not None:
                callback_result = save_callback(candidate)
                if isinstance(callback_result, AuthoringSaveResult):
                    return callback_result
                if callback_result is False:
                    failure = _finding(
                        "authoring.save-rejected",
                        Path(candidate.source_path),
                        "The authoring Save callback rejected the candidate.",
                    )
                    return AuthoringSaveResult(
                        success=False,
                        candidate=candidate,
                        findings=(failure,),
                        message=failure.message,
                        source_hashes_before=before,
                        source_hashes_after=self._source_hashes(candidate, root),
                    )
            elif root is not None and self._project_service is not None:
                current_candidate, current_contents = self._save_project_candidate(
                    candidate,
                    root,
                    current_contents,
                )
            else:
                current_candidate = self._save_direct_candidate(candidate)
        except Exception as error:
            failure = _finding(
                "authoring.save-failed",
                Path(candidate.source_path),
                (
                    f"Save-after-preview failed ({type(error).__name__}); canonical source was "
                    "not accepted."
                ),
            )
            return AuthoringSaveResult(
                success=False,
                candidate=candidate,
                findings=(failure,),
                message=failure.message,
                source_hashes_before=before,
                source_hashes_after=self._source_hashes(candidate, root),
            )
        after = self._source_hashes(current_candidate, root)
        return AuthoringSaveResult(
            success=True,
            candidate=current_candidate,
            message="Authoring candidate saved after explicit preview confirmation.",
            source_hashes_before=before,
            source_hashes_after=after,
            contents=current_contents,
        )

    def save_authoring_candidate(self, *args: Any, **kwargs: Any) -> AuthoringSaveResult:
        """Snake-case alias for :meth:`SaveAuthoringCandidate`."""

        return self.SaveAuthoringCandidate(*args, **kwargs)

    def _load_schema(
        self, schema: Mapping[str, Any] | str | Path
    ) -> tuple[dict[str, Any], Path | None, tuple[AuthoringFinding, ...]]:
        if isinstance(schema, Mapping):
            return dict(schema), None, ()
        path = Path(schema).expanduser().resolve()
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return (
                {},
                path,
                (_finding("schema.read-failed", path, "Schema source is not readable JSON."),),
            )
        if not isinstance(raw, Mapping):
            return (
                {},
                path,
                (_finding("schema.root-not-object", path, "Schema root must be an object."),),
            )
        return dict(raw), path, ()

    def _source_input(
        self,
        source: str | bytes | Path | None,
        source_file: Path | None,
        *,
        project_path: str | Path | None,
        project_contents: ProjectContents | None,
        artifact_path: str | None,
    ) -> tuple[bytes, str, str, tuple[AuthoringFinding, ...]]:
        if isinstance(source, bytes):
            encoding = "utf-8-sig" if source.startswith(b"\xef\xbb\xbf") else "utf-8"
            return source, _decode_bytes(source, encoding), encoding, ()
        if isinstance(source, str):
            encoded = source.encode("utf-8")
            return encoded, source, "utf-8", ()
        if isinstance(source, Path):
            source_file = source.expanduser().resolve()
        if project_contents is not None and artifact_path:
            content = project_contents.artifacts.get(Path(artifact_path).as_posix())
            if isinstance(content, bytes):
                encoding = "utf-8-sig" if content.startswith(b"\xef\xbb\xbf") else "utf-8"
                return content, _decode_bytes(content, encoding), encoding, ()
        if project_contents is not None and source_file is not None and project_path is not None:
            root = Path(project_path).expanduser().resolve()
            try:
                relative = source_file.relative_to(root).as_posix()
            except ValueError:
                relative = ""
            if relative == "cell.yaml":
                content = project_contents.cell_yaml.encode("utf-8")
                return content, project_contents.cell_yaml, "utf-8", ()
            content = project_contents.artifacts.get(relative)
            if isinstance(content, bytes):
                encoding = "utf-8-sig" if content.startswith(b"\xef\xbb\xbf") else "utf-8"
                return content, _decode_bytes(content, encoding), encoding, ()
        if source_file is not None:
            try:
                content = source_file.read_bytes()
            except (OSError, UnicodeError):
                return (
                    b"",
                    "",
                    "utf-8",
                    (
                        _finding(
                            "source.read-failed", source_file, "Source document is not readable."
                        ),
                    ),
                )
            encoding = "utf-8-sig" if content.startswith(b"\xef\xbb\xbf") else "utf-8"
            return content, _decode_bytes(content, encoding), encoding, ()
        return b"", "", "utf-8", ()

    def _build_form_model(
        self,
        schema_document: Mapping[str, Any],
        schema_file: Path | None,
        value: Mapping[str, Any],
        *,
        base_values: Mapping[str, Any],
        source_values: Mapping[str, Any],
        schema_kind: str | SchemaDocumentKind | None,
        source_path: str,
        source_format: str,
        encoding: str,
        source_text: str,
        source_bytes: bytes,
        allocator_seed: str,
        required_choices: Mapping[str, Sequence[str]] | None,
        project_path: str | Path | None,
        artifact_path: str | None,
        initial_findings: Sequence[AuthoringFinding],
    ) -> SchemaFormModel:
        schema = dict(schema_document)
        kind = _kind_name(schema_kind, schema_file)
        source_for_findings = Path(source_path)
        findings: list[AuthoringFinding] = list(initial_findings)
        findings.extend(_audit_schema(schema, schema_file or Path("<memory>")))
        if schema.get("$schema") != DRAFT_2020_12:
            findings.append(
                _finding(
                    "schema.version-unsupported",
                    schema_file or Path("<memory>"),
                    f"Schema must declare JSON Schema Draft 2020-12 as '{DRAFT_2020_12}'.",
                    pointer="/$schema",
                )
            )
        try:
            Draft202012Validator.check_schema(schema)
        except SchemaError as error:
            findings.append(
                _finding(
                    "schema.invalid",
                    schema_file or Path("<memory>"),
                    f"Schema is not valid Draft 2020-12 ({error.message}).",
                )
            )

        fields: list[SchemaFormField] = []
        choices: list[AuthoringChoice] = []
        generated_paths: list[str] = []
        explicit = required_choices or {}
        materialized = _materialize(
            schema,
            dict(value),
            path="",
            required=True,
            group=None,
            allocator_seed=allocator_seed,
            schema_root=schema,
            fields=fields,
            choices=choices,
            generated_paths=generated_paths,
            explicit_choices=explicit,
        )
        if materialized is _MISSING or not isinstance(materialized, Mapping):
            materialized = {}
        findings.extend(_validate_value(schema, materialized, source_for_findings))
        findings.extend(
            self._semantic_findings(
                kind,
                materialized,
                source_for_findings,
                project_path=project_path,
                project_contents=self._project_contents_from_context(project_path, source_values),
                original_value=base_values,
            )
        )
        ordered_fields = tuple(
            sorted(fields, key=lambda field: (field.group, field.order, field.path))
        )
        group_map: dict[str, list[SchemaFormField]] = {}
        for item in ordered_fields:
            group_map.setdefault(item.group, []).append(item)
        groups = tuple(
            SchemaFormGroup(
                name=name,
                order=min(field.order for field in group_fields),
                fields=tuple(group_fields),
                advanced=all(field.advanced for field in group_fields),
            )
            for name, group_fields in sorted(
                group_map.items(),
                key=lambda entry: (min(item.order for item in entry[1]), entry[0]),
            )
        )
        schema_version = _schema_version(schema)
        return SchemaFormModel(
            schema_path=str(schema_file or "<memory>"),
            schema_kind=kind,
            schema_version=schema_version,
            title=str(schema.get("title", kind.replace("-", " ").title())),
            source_path=source_path,
            source_format=source_format,
            encoding=encoding,
            fields=ordered_fields,
            groups=groups,
            values=_clone_json(materialized),
            base_values=_clone_json(base_values),
            source_values=_clone_json(source_values),
            choices=tuple(sorted(_unique_choices(choices), key=lambda item: item.key)),
            generated_paths=tuple(sorted(set(generated_paths))),
            findings=_unique_findings(findings),
            allocator_seed=allocator_seed,
            source_text=source_text,
            source_bytes=source_bytes,
            base_source_hash=_sha256(source_bytes),
            project_path=str(project_path) if project_path is not None else None,
            artifact_path=Path(artifact_path).as_posix()
            if artifact_path
            else _relative_artifact(source_path, project_path),
            schema_document=_clone_json(schema),
        )

    def _semantic_findings(
        self,
        kind: str,
        value: Mapping[str, Any],
        source_path: Path,
        *,
        project_path: str | Path | None,
        project_contents: ProjectContents | None,
        original_value: Mapping[str, Any],
    ) -> tuple[AuthoringFinding, ...]:
        findings: list[AuthoringFinding] = []
        model_type: type[Any] | None = {
            "cell": CellProject,
            "recipe": Recipe,
            "scenario": Scenario,
        }.get(kind)
        if model_type is not None:
            try:
                model_type.model_validate(value)
            except ValidationError as error:
                for item in error.errors(
                    include_context=False,
                    include_input=False,
                    include_url=False,
                ):
                    location = tuple(str(part) for part in item.get("loc", ()))
                    pointer = "/" + "/".join(_escape_pointer(part) for part in location)
                    findings.append(
                        _finding(
                            f"model.{str(item.get('type', 'invalid')).replace('_', '-')}",
                            source_path,
                            str(item.get("msg", "Invalid value.")),
                            pointer=pointer,
                        )
                    )
        if kind == "recipe":
            original_status = _path_get(original_value, "/recipe/status")
            current_status = _path_get(value, "/recipe/status")
            if original_status in _RELEASED_RECIPE_STATUSES and _json_value(
                original_value
            ) != _json_value(value):
                findings.append(
                    _finding(
                        "authoring.recipe.released-immutable",
                        source_path,
                        "Released recipe versions are immutable; create a new draft/version.",
                        pointer="/recipe/status",
                    )
                )
            if (
                current_status is not _MISSING
                and current_status != original_status
                and current_status in _LIFECYCLE_STATUSES
            ):
                findings.append(
                    _finding(
                        "authoring.recipe.lifecycle-transition-required",
                        source_path,
                        (
                            "Recipe lifecycle changes must use the existing evidence-aware "
                            "lifecycle service."
                        ),
                        pointer="/recipe/status",
                    )
                )
        if kind == "scenario":
            for pointer, label in (
                ("/scenario/seed", "seed"),
                ("/faults", "fault schedule"),
                ("/simulation/requested_fidelity", "requested fidelity"),
            ):
                if (
                    _path_get(original_value, pointer) is not _MISSING
                    and _path_get(value, pointer) is _MISSING
                ):
                    findings.append(
                        _finding(
                            "authoring.scenario.fidelity-state-lost",
                            source_path,
                            f"Scenario {label} must remain explicit in the canonical source.",
                            pointer=pointer,
                        )
                    )
        return tuple(findings)

    def _choices_for_value(
        self,
        schema: Mapping[str, Any],
        value: Mapping[str, Any],
        *,
        schema_kind: str | SchemaDocumentKind | None,
        allocator_seed: str,
    ) -> tuple[AuthoringChoice, ...]:
        fields: list[SchemaFormField] = []
        choices: list[AuthoringChoice] = []
        generated: list[str] = []
        _materialize(
            schema,
            dict(value),
            path="",
            required=True,
            group=None,
            allocator_seed=allocator_seed,
            schema_root=schema,
            fields=fields,
            choices=choices,
            generated_paths=generated,
            explicit_choices={},
        )
        return tuple(sorted(_unique_choices(choices), key=lambda item: item.key))

    def _candidate_from_values(
        self,
        *,
        schema_document: Mapping[str, Any],
        schema_path: str,
        schema_kind: str,
        source_path: str,
        source_format: str,
        encoding: str,
        original_text: str,
        original_bytes: bytes,
        original_value: Mapping[str, Any],
        source_value: Mapping[str, Any] | None,
        form_value: Mapping[str, Any],
        canonical_value: Mapping[str, Any],
        choices: Sequence[AuthoringChoice],
        generated_paths: Sequence[str],
        initial_findings: Sequence[AuthoringFinding],
        project_path: str | Path | None,
        artifact_path: str | None,
        project_contents: ProjectContents | None,
        source_text: str | None = None,
    ) -> AuthoringCandidate:
        canonical_mapping = dict(canonical_value) if isinstance(canonical_value, Mapping) else {}
        source_mapping = dict(source_value) if isinstance(source_value, Mapping) else None
        if source_text is None:
            if _json_value(canonical_mapping) == _json_value(original_value):
                rendered_source = original_text
            else:
                rendered_source = _dump_source(canonical_mapping, source_format)
        else:
            rendered_source = source_text
        canonical_text = _dump_source(canonical_mapping, source_format)
        findings = list(initial_findings)
        findings.extend(_validate_value(schema_document, canonical_mapping, Path(source_path)))
        findings.extend(
            self._semantic_findings(
                schema_kind,
                canonical_mapping,
                Path(source_path),
                project_path=project_path,
                project_contents=project_contents,
                original_value=original_value,
            )
        )
        if source_mapping is None:
            findings.append(
                _finding(
                    "source.parse-failed",
                    Path(source_path),
                    "Source edits must parse to an object before Save.",
                )
            )
        if project_path is not None:
            findings.extend(
                self._project_candidate_findings(
                    project_path,
                    source_path,
                    canonical_mapping,
                    source_format,
                    project_contents,
                    artifact_path,
                )
            )
        released = (
            schema_kind == "recipe"
            and _path_get(original_value, "/recipe/status") in _RELEASED_RECIPE_STATUSES
            and _json_value(original_value) != _json_value(canonical_mapping)
        )
        if released and not any(
            item.code == "authoring.recipe.released-immutable" for item in findings
        ):
            findings.append(
                _finding(
                    "authoring.recipe.released-immutable",
                    Path(source_path),
                    "Released recipe versions are immutable; create a new draft/version.",
                    pointer="/recipe/status",
                )
            )
        preserve_original_bytes = source_text is None and _json_value(
            canonical_mapping
        ) == _json_value(original_value)
        source_encoded = (
            original_bytes if preserve_original_bytes else _encode_text(rendered_source, encoding)
        )
        canonical_encoded = _encode_text(canonical_text, encoding)
        formatting_changed = not preserve_original_bytes and rendered_source != original_text
        if formatting_changed:
            findings.append(
                _finding(
                    "authoring.source-formatting-changed",
                    Path(source_path),
                    (
                        "The preview changes source formatting or ordering; review the exact "
                        "candidate text before Save."
                    ),
                    severity="warning",
                )
            )
        diff = _diff_values(original_value, canonical_mapping)
        base_hash = _sha256(original_bytes)
        source_hash = _sha256(source_encoded)
        canonical_hash = _sha256(canonical_encoded)
        candidate_id = hashlib.sha256(
            (
                f"{schema_path}|{schema_kind}|{source_path}|{base_hash}|"
                f"{_canonical_json(form_value)}|{_canonical_json(canonical_mapping)}"
            ).encode()
        ).hexdigest()[:32]
        token = hashlib.sha256(f"{candidate_id}|{base_hash}|{canonical_hash}".encode()).hexdigest()
        unique_findings = _unique_findings(findings)
        can_save = (
            source_mapping is not None
            and not choices
            and not released
            and not any(item.severity == "error" for item in unique_findings)
        )
        return AuthoringCandidate(
            candidate_id=candidate_id,
            schema_path=schema_path,
            schema_kind=schema_kind,
            schema_version=_schema_version(schema_document),
            source_path=source_path,
            source_format=source_format,
            encoding=encoding,
            original_text=original_text,
            source_text=rendered_source,
            canonical_text=canonical_text,
            original_bytes=original_bytes,
            original_value=_clone_json(original_value),
            source_value=_clone_json(source_mapping) if source_mapping is not None else None,
            form_value=_clone_json(form_value),
            canonical_value=_clone_json(canonical_mapping),
            base_source_hash=base_hash,
            source_hash=source_hash,
            canonical_hash=canonical_hash,
            diff=tuple(diff),
            choices=tuple(sorted(_unique_choices(choices), key=lambda item: item.key)),
            generated_paths=tuple(sorted(set(generated_paths))),
            findings=unique_findings,
            can_save=can_save,
            confirmation_token=token,
            project_path=str(project_path) if project_path is not None else None,
            artifact_path=artifact_path or _relative_artifact(source_path, project_path),
            released_recipe=released,
            formatting_changed=formatting_changed,
            schema_document=_clone_json(schema_document),
            project_contents=project_contents,
        )

    def _project_candidate_findings(
        self,
        project_path: str | Path,
        source_path: str,
        value: Mapping[str, Any],
        source_format: str,
        project_contents: ProjectContents | None,
        artifact_path: str | None,
    ) -> tuple[AuthoringFinding, ...]:
        if self._project_service is None:
            return ()
        root = Path(project_path).expanduser().resolve()
        source = Path(source_path)
        try:
            relative = source.resolve().relative_to(root).as_posix()
        except ValueError:
            relative = Path(artifact_path).as_posix() if artifact_path else ""
        if not relative:
            return ()
        current = project_contents
        if current is None:
            try:
                inspected = self._project_service.inspect(root)
                current = inspected.contents
            except Exception:
                return (
                    _finding(
                        "authoring.backend-unavailable",
                        root,
                        "The project backend could not inspect the canonical project.",
                    ),
                )
        if current is None:
            return ()
        encoded = _encode_source(value, source_format, "utf-8")
        candidate_contents = (
            replace(current, cell_yaml=encoded.decode("utf-8"))
            if relative == "cell.yaml"
            else replace(current, artifacts={**current.artifacts, relative: encoded})
        )
        with tempfile.TemporaryDirectory(prefix="cellforge-authoring-check-") as temporary:
            staged = Path(temporary) / "project"
            try:
                shutil.copytree(root, staged)
                if relative == "cell.yaml":
                    (staged / relative).write_bytes(encoded)
                else:
                    target = staged / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(encoded)
                result = self._project_service.inspect_candidate(
                    staged,
                    validate_studio_extensions=False,
                )
            except Exception as error:
                return (
                    _finding(
                        "authoring.backend-failed",
                        root,
                        f"Project semantic validation failed ({type(error).__name__}).",
                    ),
                )
        findings: list[AuthoringFinding] = []
        for item in result.validation:
            findings.append(
                AuthoringFinding(
                    code=str(item.code),
                    severity=str(item.severity),
                    path=_remap_path(item.path, staged if "staged" in locals() else root, root),
                    message=str(item.message),
                )
            )
        return tuple(findings)

    def _project_contents_from_context(
        self, project_path: str | Path | None, source_values: Mapping[str, Any]
    ) -> ProjectContents | None:
        del project_path, source_values
        return None

    def _project_contents(self, form: SchemaFormModel) -> ProjectContents | None:
        del form
        return None

    def _save_guard(
        self,
        candidate: AuthoringCandidate,
        confirmation_token: str | None,
        confirmed: bool,
        project_path: Path | None,
    ) -> AuthoringFinding | None:
        source = Path(candidate.source_path)
        if not confirmed:
            return _finding(
                "authoring.save-confirmation-required",
                source,
                "Preview is complete; explicit Save confirmation is required.",
            )
        if confirmation_token != candidate.confirmation_token:
            return _finding(
                "authoring.save-token-invalid",
                source,
                "The Save token does not match the reviewed authoring preview.",
            )
        if not candidate.can_save:
            return _finding(
                "authoring.save-blocked",
                source,
                "The authoring candidate has unresolved choices or validation findings.",
            )
        current = self._read_current_source(candidate, project_path)
        if current is not None and _sha256(current) != candidate.base_source_hash:
            return _finding(
                "authoring.source-changed",
                source,
                "Canonical source changed after preview; rebuild the candidate before Save.",
            )
        return None

    def _read_current_source(
        self, candidate: AuthoringCandidate, project_path: Path | None
    ) -> bytes | None:
        if project_path is not None:
            source = Path(candidate.source_path)
            try:
                relative = source.resolve().relative_to(project_path).as_posix()
            except ValueError:
                relative = candidate.artifact_path or ""
            if relative == "cell.yaml":
                path = project_path / "cell.yaml"
            else:
                path = project_path / relative if relative else source
        else:
            path = Path(candidate.source_path)
        try:
            return path.read_bytes()
        except OSError:
            if candidate.project_contents is not None and candidate.artifact_path:
                return candidate.project_contents.artifacts.get(candidate.artifact_path)
            return candidate.original_bytes if candidate.original_bytes else None

    def _save_project_candidate(
        self,
        candidate: AuthoringCandidate,
        root: Path,
        contents: ProjectContents | None,
    ) -> tuple[AuthoringCandidate, ProjectContents | None]:
        del contents
        project_service = self._project_service
        if project_service is None:
            raise RuntimeError("Project backend is unavailable for project authoring Save.")
        current_result = project_service.inspect(root)
        current_contents = current_result.contents
        if current_contents is None:
            raise RuntimeError("Project inspection rejected the canonical source before Save.")
        source = Path(candidate.source_path)
        try:
            relative = source.resolve().relative_to(root).as_posix()
        except ValueError:
            relative = candidate.artifact_path or ""
        if not relative:
            raise RuntimeError("Authoring source path is not project-relative.")
        encoded = (
            candidate.original_bytes
            if candidate.source_hash == candidate.base_source_hash
            else _encode_text(candidate.source_text, candidate.encoding)
        )
        if relative == "cell.yaml":
            updated_contents = replace(current_contents, cell_yaml=encoded.decode("utf-8"))
        elif relative == "scene.usda":
            updated_contents = replace(current_contents, scene_usda=encoded.decode("utf-8"))
        else:
            artifacts = dict(current_contents.artifacts)
            artifacts[relative] = encoded
            updated_contents = replace(current_contents, artifacts=artifacts)
        result = project_service.save(root, updated_contents)
        if result.project is None or result.contents is None or result.validation:
            message = (
                result.validation[0].message
                if result.validation
                else "Project Save rejected the candidate."
            )
            raise RuntimeError(message)
        updated_candidate = replace(
            candidate,
            original_text=candidate.source_text,
            original_bytes=encoded,
            base_source_hash=_sha256(encoded),
            source_hash=_sha256(encoded),
            project_contents=result.contents,
            confirmation_token="",
        )
        return updated_candidate, result.contents

    def _save_direct_candidate(self, candidate: AuthoringCandidate) -> AuthoringCandidate:
        target = Path(candidate.source_path).expanduser().resolve()
        if not target.is_file():
            raise FileNotFoundError(str(target))
        content = (
            candidate.original_bytes
            if candidate.source_hash == candidate.base_source_hash
            else _encode_text(candidate.source_text, candidate.encoding)
        )
        temporary: Path | None = None
        try:
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{target.name}.cellforge-authoring-",
                dir=target.parent,
            )
            temporary = Path(temporary_name)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            self._replace_file(temporary, target)
            temporary = None
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        return replace(
            candidate,
            original_text=candidate.source_text,
            original_bytes=content,
            base_source_hash=_sha256(content),
            source_hash=_sha256(content),
            confirmation_token="",
        )

    def _source_hashes(
        self, candidate: AuthoringCandidate, project_path: Path | None
    ) -> dict[str, str]:
        if project_path is None:
            current = self._read_current_source(candidate, None)
            return {candidate.source_path: _sha256(current or candidate.original_bytes)}
        result: dict[str, str] = {}
        for relative in ("cell.yaml", "scene.usda", candidate.artifact_path or ""):
            if not relative or relative in result:
                continue
            target = project_path / relative
            try:
                result[relative] = _sha256(target.read_bytes())
            except OSError:
                continue
        return result


# Public command-style aliases mirror the readiness/guided Studio services and make the pure
# service discoverable to headless callers without adding domain rules to widgets.
BuildSchemaForm = SchemaAuthoringService
UpdateSchemaForm = SchemaAuthoringService
PreviewSourceEdit = SchemaAuthoringService
MergeSourceEdit = SchemaAuthoringService
SaveAuthoringCandidate = SchemaAuthoringService
SchemaFinding = AuthoringFinding


def _materialize(
    node: Mapping[str, Any],
    current: Any,
    *,
    path: str,
    required: bool,
    group: str | None,
    allocator_seed: str,
    schema_root: Mapping[str, Any],
    fields: list[SchemaFormField],
    choices: list[AuthoringChoice],
    generated_paths: list[str],
    explicit_choices: Mapping[str, Sequence[str]],
) -> Any:
    resolved = _resolve_schema(node, schema_root)
    annotation = _annotation(resolved)
    field_type = _field_type(resolved)
    field_name = _pointer_name(path)
    top_group = group or (_humanize(field_name) if field_name else "General")
    if path and isinstance(annotation.get("group"), str):
        top_group = annotation["group"]
    missing = current is _MISSING
    generated = False
    if missing:
        chosen = _default_for(
            resolved,
            path,
            required=required,
            allocator_seed=allocator_seed,
            schema_kind=None,
            explicit_choices=explicit_choices,
        )
        if chosen is not _MISSING:
            current = chosen
            missing = False
            generated = _is_generated_default(resolved, path, chosen, allocator_seed)
            if generated:
                generated_paths.append(path)
        elif required and field_type == "object":
            current = {}
            missing = False
    field_index: int | None = None
    if path:
        order_raw = annotation.get("order")
        order = (
            int(order_raw)
            if isinstance(order_raw, int) and not isinstance(order_raw, bool)
            else len(fields)
        )
        label_value = annotation.get("label")
        label = label_value if isinstance(label_value, str) else _humanize(field_name)
        enum = tuple(resolved.get("enum", ())) if isinstance(resolved.get("enum"), list) else ()
        const = resolved.get("const") if "const" in resolved else None
        widget = _widget_for(field_type, enum, const)
        item_path = (
            _child_pointer(path, "*")
            if field_type == "array" and isinstance(resolved.get("items"), Mapping)
            else None
        )
        field_index = len(fields)
        fields.append(
            SchemaFormField(
                path=path,
                name=field_name,
                label=label,
                group=top_group,
                order=order,
                field_type=field_type,
                widget=widget,
                value=None if missing else _json_value(current),
                required=required,
                advanced=bool(annotation.get("advanced", False)),
                generated=generated or bool(annotation.get("generated", False)),
                unit=annotation.get("unit") if isinstance(annotation.get("unit"), str) else None,
                minimum=_number_or_none(resolved.get("minimum")),
                maximum=_number_or_none(resolved.get("maximum")),
                exclusive_minimum=resolved.get("exclusiveMinimum"),
                exclusive_maximum=resolved.get("exclusiveMaximum"),
                enum=enum,
                const=const,
                description=resolved.get("description")
                if isinstance(resolved.get("description"), str)
                else None,
                help=annotation.get("help") if isinstance(annotation.get("help"), str) else None,
                schema_path=path,
                item_schema_path=item_path,
            )
        )
    if missing:
        if (
            required
            and isinstance(explicit_choices.get(path), Sequence)
            and not isinstance(explicit_choices.get(path), (str, bytes))
        ):
            options = tuple(str(item) for item in explicit_choices[path])
            if len(options) > 1:
                choices.append(
                    AuthoringChoice(
                        key=path,
                        prompt=f"Choose a value for {_humanize(field_name)}",
                        options=options,
                        reason="Multiple valid authoring choices were supplied.",
                        source=path,
                    )
                )
        elif required and isinstance(resolved.get("enum"), list) and len(resolved["enum"]) > 1:
            choices.append(
                AuthoringChoice(
                    key=path,
                    prompt=f"Choose a value for {_humanize(field_name)}",
                    options=tuple(str(item) for item in resolved["enum"]),
                    reason=(
                        "The required enum has multiple valid values and no deterministic default."
                    ),
                    source=path,
                )
            )
        return _MISSING

    if field_type == "object" and isinstance(current, Mapping):
        result: dict[str, Any] = {}
        properties = resolved.get("properties")
        required_properties = (
            set(resolved.get("required", ()))
            if isinstance(resolved.get("required"), list)
            else set()
        )
        if isinstance(properties, Mapping):
            for name, child in properties.items():
                if not isinstance(name, str) or not isinstance(child, Mapping):
                    continue
                child_path = _child_pointer(path, name)
                child_value = current.get(name, _MISSING)
                materialized = _materialize(
                    child,
                    child_value,
                    path=child_path,
                    required=name in required_properties,
                    group=top_group,
                    allocator_seed=allocator_seed,
                    schema_root=schema_root,
                    fields=fields,
                    choices=choices,
                    generated_paths=generated_paths,
                    explicit_choices=explicit_choices,
                )
                if materialized is not _MISSING:
                    result[name] = materialized
        for key, child_value in current.items():
            if key not in result and (not isinstance(properties, Mapping) or key not in properties):
                result[str(key)] = _clone_json(child_value)
        if field_index is not None:
            fields[field_index] = replace(fields[field_index], value=_json_value(result))
        return result

    if field_type == "array" and isinstance(current, list):
        result_list: list[Any] = []
        item_schema = resolved.get("items")
        for index, item in enumerate(current):
            if isinstance(item_schema, Mapping):
                item_value = _materialize(
                    item_schema,
                    item,
                    path=_child_pointer(path, str(index)),
                    required=True,
                    group=top_group,
                    allocator_seed=allocator_seed,
                    schema_root=schema_root,
                    fields=fields,
                    choices=choices,
                    generated_paths=generated_paths,
                    explicit_choices=explicit_choices,
                )
                result_list.append(None if item_value is _MISSING else item_value)
            else:
                result_list.append(_clone_json(item))
        if field_index is not None:
            fields[field_index] = replace(fields[field_index], value=_json_value(result_list))
        return result_list
    return _clone_json(current)


def _default_for(
    schema: Mapping[str, Any],
    path: str,
    *,
    required: bool,
    allocator_seed: str,
    schema_kind: str | None,
    explicit_choices: Mapping[str, Sequence[str]],
) -> Any:
    del schema_kind
    supplied_choices = explicit_choices.get(path)
    if (
        required
        and isinstance(supplied_choices, Sequence)
        and not isinstance(supplied_choices, (str, bytes))
    ):
        if len(supplied_choices) == 1:
            return _clone_json(supplied_choices[0])
        if len(supplied_choices) > 1:
            return _MISSING
    if "default" in schema:
        return _clone_json(schema["default"])
    if "const" in schema:
        return _clone_json(schema["const"])
    enum = schema.get("enum")
    if isinstance(enum, list) and len(enum) == 1:
        return _clone_json(enum[0])
    if not required or path in explicit_choices:
        return _MISSING
    if isinstance(enum, list) and len(enum) > 1:
        return _MISSING
    return _allocated_default(schema, path, allocator_seed)


def _allocated_default(schema: Mapping[str, Any], path: str, seed: str) -> Any:
    name = _pointer_name(path).lower()
    if not _is_allocatable_path(path):
        return _MISSING
    digest = hashlib.sha256(f"cellforge-authoring:{seed}:{path}".encode()).hexdigest()
    schema_format = schema.get("format")
    if schema_format == "uuid" or name.endswith("_uuid"):
        return str(uuid5(NAMESPACE_URL, f"cellforge-authoring:{seed}:{path}"))
    if name in {"usd_prim", "prim", "root_prim"}:
        return f"/World/Components/authoring_{digest[:12]}"
    if name in {"path", "source_path"}:
        if "scenario" in seed:
            return f"scenarios/authoring-{digest[:12]}.yaml"
        if "recipe" in seed:
            return f"recipes/authoring-{digest[:12]}.yaml"
        return f"authoring/{digest[:12]}.yaml"
    if name == "id" and "/cell/" in path:
        return str(uuid5(NAMESPACE_URL, f"cellforge-authoring:{seed}:{path}"))
    if name in {"id", "component_id", "component_instance_id"} or name.endswith("_id"):
        return f"authoring-{digest[:16]}"
    return _MISSING


def _is_allocatable_path(path: str) -> bool:
    name = _pointer_name(path).lower()
    return name in {
        "id",
        "cell_id",
        "component_id",
        "component_instance_id",
        "usd_prim",
        "path",
        "source_path",
    } or name.endswith("_id")


def _is_generated_default(schema: Mapping[str, Any], path: str, value: Any, seed: str) -> bool:
    if bool(_annotation(schema).get("generated", False)):
        return True
    return _allocated_default(schema, path, seed) is not _MISSING and value == _allocated_default(
        schema, path, seed
    )


def _field_type(schema: Mapping[str, Any]) -> str:
    raw = schema.get("type")
    if isinstance(raw, list):
        types = [str(item) for item in raw if item != "null"]
        return types[0] if types else "value"
    if isinstance(raw, str):
        return raw
    if isinstance(schema.get("properties"), Mapping):
        return "object"
    if "items" in schema:
        return "array"
    if "enum" in schema or "const" in schema:
        return "string"
    return "value"


def _widget_for(field_type: str, enum: Sequence[Any], const: Any) -> str:
    if enum and len(enum) > 1:
        return "enum"
    if const is not None:
        return "constant"
    return {
        "boolean": "checkbox",
        "integer": "integer",
        "number": "number",
        "array": "array",
        "object": "object",
        "string": "text",
    }.get(field_type, "json")


def _annotation(schema: Mapping[str, Any]) -> Mapping[str, Any]:
    raw = schema.get("x-cellforge")
    return raw if isinstance(raw, Mapping) else {}


def _resolve_schema(node: Mapping[str, Any], root: Mapping[str, Any]) -> dict[str, Any]:
    ref = node.get("$ref")
    if not isinstance(ref, str) or not ref.startswith("#/"):
        return dict(node)
    current: Any = root
    try:
        for token in ref[2:].split("/"):
            current = current[token.replace("~1", "/").replace("~0", "~")]
    except (KeyError, TypeError):
        return dict(node)
    if not isinstance(current, Mapping):
        return dict(node)
    resolved = dict(current)
    resolved.update({key: value for key, value in node.items() if key != "$ref"})
    return resolved


def _audit_schema(schema: Mapping[str, Any], source: Path) -> tuple[AuthoringFinding, ...]:
    findings: list[AuthoringFinding] = []

    def walk(node: Any, pointer: str) -> None:
        if not isinstance(node, Mapping):
            return
        for key, child in node.items():
            if not isinstance(key, str):
                continue
            if key not in _KNOWN_SCHEMA_KEYWORDS and not key.startswith("x-"):
                findings.append(
                    _finding(
                        "schema.unknown-keyword",
                        source,
                        f"Unknown JSON Schema validation keyword '{key}' is not supported.",
                        pointer=_child_pointer(pointer, key),
                    )
                )
            if key in {"properties", "patternProperties", "$defs", "definitions"} and isinstance(
                child, Mapping
            ):
                for name, subnode in child.items():
                    walk(subnode, _child_pointer(_child_pointer(pointer, key), str(name)))
            elif key in {"allOf", "anyOf", "oneOf", "prefixItems"} and isinstance(child, list):
                for index, subnode in enumerate(child):
                    walk(subnode, _child_pointer(_child_pointer(pointer, key), str(index)))
            elif key in {
                "items",
                "contains",
                "additionalProperties",
                "unevaluatedItems",
                "unevaluatedProperties",
                "propertyNames",
                "if",
                "then",
                "else",
                "not",
                "contentSchema",
            }:
                walk(child, _child_pointer(pointer, key))

    walk(schema, "")
    return tuple(findings)


def _validate_value(
    schema: Mapping[str, Any], value: Mapping[str, Any], source: Path
) -> tuple[AuthoringFinding, ...]:
    try:
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        errors = sorted(
            validator.iter_errors(value),
            key=lambda error: (tuple(str(item) for item in error.absolute_path), error.message),
        )
    except SchemaError as schema_error:
        return (
            _finding(
                "schema.invalid",
                source,
                f"Schema is not valid Draft 2020-12 ({schema_error.message}).",
            ),
        )
    except Exception as reference_error:
        return (
            _finding(
                "schema.reference-invalid",
                source,
                f"Schema reference could not be resolved ({type(reference_error).__name__}).",
            ),
        )
    findings: list[AuthoringFinding] = []
    for error in errors:
        pointer = "/" + "/".join(_escape_pointer(str(item)) for item in error.absolute_path)
        if error.validator == "required" and isinstance(error.validator_value, list):
            missing = [item for item in error.validator_value if item not in error.instance]
            if missing:
                pointer = _child_pointer(pointer, str(missing[0]))
        findings.append(
            _finding(
                f"schema.{str(error.validator).replace('_', '-')}",
                source,
                error.message,
                pointer=pointer,
            )
        )
    return tuple(findings)


def _parse_source(
    content: bytes,
    source: Path,
    encoding: str,
) -> tuple[Mapping[str, Any] | None, list[AuthoringFinding]]:
    try:
        text = content.decode(encoding)
    except (UnicodeDecodeError, LookupError):
        return None, [
            _finding("source.encoding-invalid", source, "Source must be valid UTF-8 text.")
        ]
    try:
        if source.suffix.lower() == ".json":
            raw = json.loads(text)
        else:
            raw = yaml.safe_load(text)
    except (json.JSONDecodeError, yaml.YAMLError):
        return None, [_finding("source.parse-failed", source, "Document syntax is invalid.")]
    if not isinstance(raw, Mapping):
        return None, [
            _finding("source.root-not-object", source, "Document root must be an object.")
        ]
    return dict(raw), []


def _dump_source(value: Mapping[str, Any], source_format: str) -> str:
    normalized = _json_value(value)
    if source_format == "json":
        return json.dumps(normalized, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    return yaml.safe_dump(normalized, allow_unicode=True, sort_keys=True, default_flow_style=False)


def _encode_source(value: Mapping[str, Any], source_format: str, encoding: str) -> bytes:
    return _encode_text(_dump_source(value, source_format), encoding)


def _encode_text(text: str, encoding: str) -> bytes:
    return text.encode("utf-8-sig" if encoding == "utf-8-sig" else "utf-8")


def _decode_bytes(content: bytes, encoding: str) -> str:
    decoded = content.decode("utf-8-sig" if encoding == "utf-8-sig" else "utf-8", errors="replace")
    return decoded.replace("\r\n", "\n").replace("\r", "\n")


def _source_format(
    source_path: Path | None,
    source: str | bytes | Path | None,
    fallback: str = "yaml",
) -> str:
    candidate = source_path
    if isinstance(source, Path):
        candidate = source
    if candidate is not None and candidate.suffix.lower() == ".json":
        return "json"
    if candidate is not None and candidate.suffix.lower() in {".yaml", ".yml"}:
        return "yaml"
    return fallback


def _resolve_source_path(
    source_path: str | Path | None,
    project_path: str | Path | None,
    artifact_path: str | None,
) -> Path | None:
    if artifact_path and project_path is not None:
        return (Path(project_path).expanduser().resolve() / artifact_path).resolve()
    if source_path is None:
        return None
    path = Path(source_path).expanduser()
    if project_path is not None and not path.is_absolute():
        path = Path(project_path).expanduser().resolve() / path
    return path.resolve()


def _allocator_seed(
    seed: str | None,
    schema_kind: str | SchemaDocumentKind | None,
    schema_path: Path | None,
    source_path: Path | None,
) -> str:
    if seed:
        return str(seed)
    kind = _kind_name(schema_kind, schema_path)
    location = str(source_path or schema_path or "memory")
    return f"{kind}:{location}"


def _seed_from_candidate(candidate: AuthoringCandidate) -> str:
    return f"{candidate.schema_kind}:{candidate.schema_path}:{candidate.source_path}"


def _kind_name(
    schema_kind: str | SchemaDocumentKind | None,
    schema_path: Path | None,
) -> str:
    if schema_kind is not None:
        return str(
            schema_kind.value if isinstance(schema_kind, SchemaDocumentKind) else schema_kind
        )
    if schema_path is not None:
        name = schema_path.name.lower()
        for kind in _KNOWN_SCHEMA_DOCUMENT_KINDS:
            if f"{kind}.schema.json" == name:
                return kind
        if "config.schema" in name:
            return "component-config"
    return "document"


def _schema_version(schema: Mapping[str, Any]) -> str | None:
    properties = schema.get("properties")
    if isinstance(properties, Mapping):
        version = properties.get("schema_version")
        if isinstance(version, Mapping):
            constant = version.get("const")
            if isinstance(constant, str):
                return constant
    return None


def _apply_form_changes(value: Mapping[str, Any], changes: Mapping[str, Any]) -> dict[str, Any]:
    result = _clone_json(value)
    if not isinstance(result, dict):
        result = {}
    if not changes:
        return result
    pointer_changes = any(str(key).startswith("/") for key in changes)
    for raw_key, changed_value in changes.items():
        key = str(raw_key)
        if pointer_changes or key.startswith("/"):
            _path_set(result, key if key.startswith("/") else "/" + key, changed_value)
        elif "." in key:
            _path_set(
                result,
                "/" + "/".join(_escape_pointer(part) for part in key.split(".")),
                changed_value,
            )
        elif isinstance(changed_value, Mapping) and isinstance(result.get(key), Mapping):
            result[key] = _deep_merge(dict(result[key]), changed_value)
        else:
            result[key] = _clone_json(changed_value)
    return result


def _deep_merge(base: Mapping[str, Any], update: Mapping[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {str(key): _clone_json(value) for key, value in base.items()}
    for key, value in update.items():
        if isinstance(value, Mapping) and isinstance(merged.get(key), Mapping):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = _clone_json(value)
    return merged


def _three_way_merge(
    base: Any,
    form: Any,
    source: Any,
    *,
    path: str,
) -> tuple[Any, set[str]]:
    if form == base:
        return _clone_json(source), set()
    if source == base or form == source:
        return _clone_json(form), set()
    if isinstance(base, Mapping) and isinstance(form, Mapping) and isinstance(source, Mapping):
        merged: dict[str, Any] = {}
        conflicts: set[str] = set()
        for key in sorted(set(base) | set(form) | set(source), key=str):
            child_path = _child_pointer(path, str(key))
            base_child = base.get(key, _MISSING)
            form_child = form.get(key, _MISSING)
            source_child = source.get(key, _MISSING)
            child, child_conflicts = _three_way_merge(
                base_child,
                form_child,
                source_child,
                path=child_path,
            )
            if child is not _MISSING:
                merged[str(key)] = child
            conflicts.update(child_conflicts)
        return merged, conflicts
    return _clone_json(form), {path or "/"}


def _diff_values(old: Any, new: Any, path: str = "") -> list[AuthoringDiffEntry]:
    if old is _MISSING and new is _MISSING:
        return []
    if old is _MISSING:
        return [AuthoringDiffEntry(path or "/", "add", None, _clone_json(new))]
    if new is _MISSING:
        return [AuthoringDiffEntry(path or "/", "remove", _clone_json(old), None)]
    if isinstance(old, Mapping) and isinstance(new, Mapping):
        result: list[AuthoringDiffEntry] = []
        for key in sorted(set(old) | set(new), key=str):
            result.extend(
                _diff_values(
                    old.get(key, _MISSING),
                    new.get(key, _MISSING),
                    _child_pointer(path, str(key)),
                )
            )
        return result
    if isinstance(old, list) and isinstance(new, list):
        result = []
        for index in range(max(len(old), len(new))):
            result.extend(
                _diff_values(
                    old[index] if index < len(old) else _MISSING,
                    new[index] if index < len(new) else _MISSING,
                    _child_pointer(path, str(index)),
                )
            )
        return result
    if old != new:
        return [AuthoringDiffEntry(path or "/", "replace", _clone_json(old), _clone_json(new))]
    return []


def _path_get(value: Any, pointer: str) -> Any:
    if pointer in {"", "/"}:
        return value
    current = value
    for token in pointer.lstrip("/").split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        if isinstance(current, Mapping) and token in current:
            current = current[token]
        elif isinstance(current, list) and token.isdigit() and int(token) < len(current):
            current = current[int(token)]
        else:
            return _MISSING
    return current


def _path_set(value: dict[str, Any], pointer: str, changed: Any) -> None:
    tokens = [
        token.replace("~1", "/").replace("~0", "~")
        for token in pointer.lstrip("/").split("/")
        if token
    ]
    if not tokens:
        if isinstance(changed, Mapping):
            value.clear()
            value.update(_clone_json(changed))
        return
    current: Any = value
    for token in tokens[:-1]:
        if isinstance(current, dict):
            if not isinstance(current.get(token), (dict, list)):
                current[token] = {}
            current = current[token]
        elif isinstance(current, list) and token.isdigit():
            index = int(token)
            while len(current) <= index:
                current.append({})
            current = current[index]
        else:
            return
    final = tokens[-1]
    if isinstance(current, dict):
        current[final] = _clone_json(changed)
    elif isinstance(current, list) and final.isdigit():
        index = int(final)
        while len(current) <= index:
            current.append(None)
        current[index] = _clone_json(changed)


def _child_pointer(pointer: str, child: str) -> str:
    if pointer in {"", "/"}:
        return f"/{_escape_pointer(child)}"
    return f"{pointer}/{_escape_pointer(child)}"


def _escape_pointer(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def _pointer_name(pointer: str) -> str:
    if not pointer:
        return ""
    return pointer.rsplit("/", 1)[-1].replace("~1", "/").replace("~0", "~")


def _relative_artifact(source_path: str, project_path: str | Path | None) -> str | None:
    if project_path is None or source_path.startswith("<"):
        return None
    try:
        return Path(source_path).resolve().relative_to(Path(project_path).resolve()).as_posix()
    except ValueError:
        return None


def _humanize(value: str) -> str:
    if not value:
        return "General"
    value = value.replace("_", " ").replace("-", " ")
    return value[:1].upper() + value[1:]


def _number_or_none(value: Any) -> float | int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    return None


def _finding(
    code: str,
    source: Path,
    message: str,
    *,
    pointer: str = "",
    severity: str = "error",
) -> AuthoringFinding:
    return AuthoringFinding(
        code=code,
        severity=severity,
        path=f"{source}#{pointer}",
        message=message,
    )


def _unique_findings(findings: Sequence[AuthoringFinding]) -> tuple[AuthoringFinding, ...]:
    unique = {(item.code, item.severity, item.path, item.message): item for item in findings}
    return tuple(sorted(unique.values(), key=lambda item: (item.path, item.code, item.message)))


def _unique_choices(choices: Sequence[AuthoringChoice]) -> tuple[AuthoringChoice, ...]:
    unique = {
        (item.key, item.prompt, item.options, item.reason, item.source): item for item in choices
    }
    return tuple(unique.values())


def _clone_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _clone_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_clone_json(item) for item in value]
    if isinstance(value, tuple):
        return [_clone_json(item) for item in value]
    return value


def _json_value(value: Any) -> Any:
    if value is _MISSING:
        return None
    return _clone_json(value)


def _canonical_json(value: Any) -> str:
    return json.dumps(_json_value(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _remap_path(path: str, source: Path, destination: Path) -> str:
    return path.replace(str(source.resolve()), str(destination.resolve()), 1)


__all__ = [
    "AuthoringCandidate",
    "AuthoringChoice",
    "AuthoringDiffEntry",
    "AuthoringFinding",
    "AuthoringSaveResult",
    "BuildSchemaForm",
    "MergeSourceEdit",
    "PreviewSourceEdit",
    "SaveAuthoringCandidate",
    "SchemaFinding",
    "SchemaAuthoringService",
    "SchemaFormField",
    "SchemaFormGroup",
    "SchemaFormModel",
    "UpdateSchemaForm",
]
