"""Shared configuration for CellForge domain models."""

from pydantic import BaseModel, ConfigDict


class DomainModel(BaseModel):
    """Base for strict, user-facing CellForge data contracts."""

    model_config = ConfigDict(
        extra="forbid",
        hide_input_in_errors=True,
        populate_by_name=True,
        str_strip_whitespace=True,
        validate_assignment=True,
    )
