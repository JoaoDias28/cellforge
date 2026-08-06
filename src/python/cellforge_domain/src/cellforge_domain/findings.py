"""Structured validation findings and source-loading failures."""

from enum import StrEnum
from pathlib import Path

from pydantic import Field

from cellforge_domain.base import DomainModel
from cellforge_domain.identifiers import StableIdentifier


class FindingSeverity(StrEnum):
    """Severity levels suitable for compiler and UI validation reports."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class ValidationFinding(DomainModel):
    """One stable, source-addressable validation result."""

    code: StableIdentifier
    severity: FindingSeverity
    path: str = Field(min_length=1)
    message: str = Field(min_length=1)


class SourceLoadError(Exception):
    """Safe public error for a document that could not be loaded or validated."""

    def __init__(
        self,
        *,
        source_path: Path,
        code: StableIdentifier,
        message: str,
        findings: tuple[ValidationFinding, ...] = (),
        cause: Exception | None = None,
    ) -> None:
        self.source_path = source_path
        self.code = code
        self.message = message
        self.findings = findings
        self._diagnostic_cause = cause
        super().__init__(f"{source_path}: {message}")

    @property
    def diagnostic_cause_type(self) -> str | None:
        """Return only the cause type, without exposing traceback or exception text."""

        if self._diagnostic_cause is None:
            return None
        return type(self._diagnostic_cause).__name__
