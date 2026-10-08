"""Pure helpers that keep evidence payloads bounded and free of secrets."""

from __future__ import annotations

from collections.abc import Mapping
import json
import math
from typing import Any

from .limits import MAX_PROPERTIES, MAX_PROPERTY_VALUE_CHARS

PropertyValue = str | int | float | bool | None

_SECRET_KEY_FRAGMENTS = ("password", "secret", "token", "api_key", "apikey", "credential")


def truncate(text: str, limit: int) -> tuple[str, bool]:
    """Return ``text`` cut to ``limit`` characters and whether it was cut."""
    if len(text) <= limit:
        return text, False
    return text[:limit], True


def finite_or_none(value: Any) -> float | None:
    """A JSON-safe score: NaN, infinities, and non-numbers become ``None``."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _is_hidden_key(key: str) -> bool:
    lowered = key.lower()
    return lowered.startswith("_") or any(part in lowered for part in _SECRET_KEY_FRAGMENTS)


def _bounded_value(value: Any) -> PropertyValue:
    if value is None or isinstance(value, bool | int):
        return value
    if isinstance(value, float):
        return finite_or_none(value)
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    return truncate(text, MAX_PROPERTY_VALUE_CHARS)[0]


def sanitize_properties(raw: Any) -> dict[str, PropertyValue]:
    """Keep at most ``MAX_PROPERTIES`` visible, primitive-valued properties.

    Secret-like and underscore-prefixed keys are dropped; nested values are
    serialised to bounded JSON strings so the browser only ever renders text.
    """
    if not isinstance(raw, Mapping):
        return {}
    cleaned: dict[str, PropertyValue] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or _is_hidden_key(key):
            continue
        cleaned[key] = _bounded_value(value)
        if len(cleaned) == MAX_PROPERTIES:
            break
    return cleaned
