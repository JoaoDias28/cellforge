"""Deterministic serialization for public CellForge models."""

import json

from cellforge_domain.base import DomainModel


def to_canonical_json(model: DomainModel) -> str:
    """Serialize a model as compact UTF-8 JSON with recursively sorted object keys."""

    value = model.model_dump(mode="json", by_alias=True)
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
