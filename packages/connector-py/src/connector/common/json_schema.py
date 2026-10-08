"""Schema inference from sample records, for sources that have no schema to ask for."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def infer_json_type(value: Any) -> str:
    """JSON Schema type name of a decoded JSON value."""
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    if value is None:
        return "null"
    return "string"


def add_properties(properties: dict[str, Any], record: Mapping[str, Any]) -> None:
    """Add the fields of ``record`` that ``properties`` does not describe yet."""
    for key, value in record.items():
        properties.setdefault(key, {"type": infer_json_type(value)})
