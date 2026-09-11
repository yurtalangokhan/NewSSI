"""Turn Structured Output's schema table into a Pydantic model.

Langflow's ``StructuredOutputComponent`` declares its schema as a table of
``name`` / ``description`` / ``type`` / ``multiple`` rows and builds a model
from it; this is the same idea against our own row shape.

Two contracts, deliberately different:

- ``schema_errors`` is pure and **total**. The validator calls it on stored,
  possibly hand-edited rows, and a validator must never raise.
- ``build_output_model`` raises. By the time the compiler calls it the schema
  has already passed validation, so a bad one there is a programming error,
  not user input.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field, create_model

# One row per field of the model the LLM must fill in.
SCHEMA_TYPES: dict[str, type] = {
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "dict": dict,
}

# Pydantic turns these into real attributes, so a name must be an identifier.
# A leading underscore is excluded too: Pydantic treats those as private
# attributes and the field would silently not exist.
_FIELD_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


def _is_true(value: Any) -> bool:
    """A TABLE cell round-trips through JSON as a string, so "True" and True
    must mean the same thing."""
    if isinstance(value, str):
        return value.strip().lower() == "true"
    return bool(value)


def schema_errors(rows: Any) -> list[str]:
    """Everything wrong with an output schema, in human-readable form.

    Empty list means usable. Never raises: a stored spec is untrusted input.
    """
    if not isinstance(rows, list) or not rows:
        return ["the output schema needs at least one field"]

    errors: list[str] = []
    seen: set[str] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            errors.append(f"row {index + 1} is not a field definition")
            continue

        name = str(row.get("name", "") or "").strip()
        if not name:
            errors.append(f"row {index + 1} has no field name")
        elif not _FIELD_NAME_RE.match(name):
            errors.append(
                f"field name '{name}' must start with a letter and contain only "
                "letters, digits and underscores"
            )
        elif name in seen:
            errors.append(f"field name '{name}' is used more than once")
        else:
            seen.add(name)

        type_name = str(row.get("type", "") or "str").strip()
        if type_name not in SCHEMA_TYPES:
            errors.append(
                f"field type '{type_name}' is not one of {', '.join(sorted(SCHEMA_TYPES))}"
            )
    return errors


def build_output_model(schema_name: str, rows: Any) -> type[BaseModel]:
    """A Pydantic model with one field per row.

    Every field is optional. Langflow's format instructions tell the model to
    fill missing values with null rather than fail; a required field would
    make the model refuse the whole extraction instead of returning what it
    did find.

    Raises ``ValueError`` when the schema is unusable — call
    ``schema_errors`` first if the caller cannot afford that.
    """
    problems = schema_errors(rows)
    if problems:
        raise ValueError("; ".join(problems))

    fields: dict[str, Any] = {}
    for row in rows:
        name = str(row["name"]).strip()
        annotation = SCHEMA_TYPES[str(row.get("type", "") or "str").strip()]
        if _is_true(row.get("multiple")):
            annotation = list[annotation]  # type: ignore[valid-type]
        description = str(row.get("description", "") or "").strip() or None
        fields[name] = (annotation | None, Field(default=None, description=description))

    return create_model(str(schema_name or "OutputModel"), **fields)
