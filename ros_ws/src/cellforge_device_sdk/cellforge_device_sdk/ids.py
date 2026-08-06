"""Traceable UUID helpers shared by skills, adapters, and result records."""

from uuid import UUID, uuid4


def new_command_id() -> str:
    """Create a canonical UUID command identifier."""

    return str(uuid4())


def new_trace_id() -> str:
    """Create a canonical UUID trace identifier."""

    return str(uuid4())


def validate_uuid(value: str, *, field_name: str) -> str:
    """Return a canonical UUID or raise a safe input-validation error."""

    try:
        parsed = UUID(value)
    except (AttributeError, ValueError) as error:
        raise ValueError(f"{field_name} must be a UUID") from error

    canonical = str(parsed)
    if value != canonical:
        raise ValueError(f"{field_name} must use canonical lowercase UUID form")
    return canonical
