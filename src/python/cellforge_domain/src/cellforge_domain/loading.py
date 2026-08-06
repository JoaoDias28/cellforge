"""Source-aware YAML and JSON loading for CellForge domain documents."""

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

import yaml
from pydantic import ValidationError

from cellforge_domain.base import DomainModel
from cellforge_domain.findings import FindingSeverity, SourceLoadError, ValidationFinding


def _source_location(source_path: Path, location: tuple[str | int, ...]) -> str:
    if not location:
        return f"{source_path}#"
    pointer = "/".join(str(part).replace("~", "~0").replace("/", "~1") for part in location)
    return f"{source_path}#/{pointer}"


def _validation_findings(
    source_path: Path, validation_error: ValidationError
) -> tuple[ValidationFinding, ...]:
    findings: list[ValidationFinding] = []
    for error in validation_error.errors(
        include_context=False,
        include_input=False,
        include_url=False,
    ):
        raw_location = cast(tuple[str | int, ...], tuple(error.get("loc", ())))
        error_type = str(error.get("type", "invalid")).replace("_", "-")
        findings.append(
            ValidationFinding(
                code=f"model.{error_type}",
                severity=FindingSeverity.ERROR,
                path=_source_location(source_path, raw_location),
                message=str(error.get("msg", "Invalid value")),
            )
        )
    return tuple(findings)


def _parse_document(source_path: Path, text: str) -> Any:
    suffix = source_path.suffix.lower()
    if suffix == ".json":
        return json.loads(text)
    if suffix in {".yaml", ".yml"}:
        return yaml.safe_load(text)
    raise SourceLoadError(
        source_path=source_path,
        code="source.unsupported-format",
        message=f"Unsupported document format '{suffix or '<none>'}'.",
    )


def load_document[ModelT: DomainModel](source: str | Path, model_type: type[ModelT]) -> ModelT:
    """Load one YAML/JSON mapping and validate it as ``model_type``.

    Public error messages include the resolved source path but never parser, filesystem, or
    validation input details. Structured findings retain precise model paths for user interfaces.
    """

    source_path = Path(source).resolve()
    try:
        text = source_path.read_text(encoding="utf-8")
    except OSError as error:
        raise SourceLoadError(
            source_path=source_path,
            code="source.read-failed",
            message="Could not read source document.",
            cause=error,
        ) from None

    try:
        value = _parse_document(source_path, text)
    except SourceLoadError:
        raise
    except (json.JSONDecodeError, yaml.YAMLError) as error:
        finding = ValidationFinding(
            code="source.parse-failed",
            severity=FindingSeverity.ERROR,
            path=f"{source_path}#",
            message="Document syntax is invalid.",
        )
        raise SourceLoadError(
            source_path=source_path,
            code="source.parse-failed",
            message="Could not parse source document.",
            findings=(finding,),
            cause=error,
        ) from None

    if not isinstance(value, Mapping):
        finding = ValidationFinding(
            code="source.root-not-object",
            severity=FindingSeverity.ERROR,
            path=f"{source_path}#",
            message="Document root must be an object.",
        )
        raise SourceLoadError(
            source_path=source_path,
            code="source.root-not-object",
            message="Source document has an invalid root value.",
            findings=(finding,),
        )

    try:
        return model_type.model_validate(dict(value))
    except ValidationError as error:
        raise SourceLoadError(
            source_path=source_path,
            code="source.validation-failed",
            message="Source document failed model validation.",
            findings=_validation_findings(source_path, error),
            cause=error,
        ) from None
