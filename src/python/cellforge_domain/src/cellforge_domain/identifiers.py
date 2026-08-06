"""Validated scalar types shared by CellForge domain models."""

import re
from typing import Annotated

from pydantic import AfterValidator

_STABLE_IDENTIFIER = re.compile(r"^[a-z0-9](?:[a-z0-9._-]*[a-z0-9])?$")
_SEMANTIC_VERSION = re.compile(
    r"^(0|[1-9]\d*)\."
    r"(0|[1-9]\d*)\."
    r"(0|[1-9]\d*)"
    r"(?:-((?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*)"
    r"(?:\.(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*))*))?"
    r"(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)
_SHA256_DIGEST = re.compile(r"^[0-9a-f]{64}$")


def _validate_stable_identifier(value: str) -> str:
    if _STABLE_IDENTIFIER.fullmatch(value) is None:
        raise ValueError("must be a lowercase URL-safe stable identifier")
    return value


def _validate_component_type_identifier(value: str) -> str:
    _validate_stable_identifier(value)
    if value.count(".") < 2:
        raise ValueError("must use manufacturer.model.capability-family form")
    return value


def _validate_semantic_version(value: str) -> str:
    if _SEMANTIC_VERSION.fullmatch(value) is None:
        raise ValueError("must be a valid Semantic Version 2.0.0 string")
    return value


def _validate_sha256_digest(value: str) -> str:
    if _SHA256_DIGEST.fullmatch(value) is None:
        raise ValueError("must be a lowercase 64-character SHA-256 digest")
    return value


StableIdentifier = Annotated[str, AfterValidator(_validate_stable_identifier)]
ComponentTypeIdentifier = Annotated[str, AfterValidator(_validate_component_type_identifier)]
SemanticVersion = Annotated[str, AfterValidator(_validate_semantic_version)]
Sha256Digest = Annotated[str, AfterValidator(_validate_sha256_digest)]
