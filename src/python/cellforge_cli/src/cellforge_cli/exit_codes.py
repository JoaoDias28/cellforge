"""Stable process exit codes for the CellForge CLI."""

from enum import IntEnum


class ExitCode(IntEnum):
    """Public command status contract; numeric values must remain backward compatible."""

    SUCCESS = 0
    VALIDATION_FAILED = 1
    USAGE_ERROR = 2
    INPUT_NOT_FOUND = 3
    DESTINATION_EXISTS = 4
    RESOURCE_UNAVAILABLE = 5
    OPERATION_FAILED = 6
