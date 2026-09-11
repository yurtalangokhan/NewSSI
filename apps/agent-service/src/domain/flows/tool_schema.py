"""The argument schema a flow component exposes when used as an agent tool.

Langflow's ``create_input_schema`` builds this from inputs individually marked
``tool_mode=True``. We derive the set instead — every visible, non-secret,
non-advanced field — so a template does not have to flag each field and then
drift from the flag.

Two rules are Langflow's and kept verbatim: a short ``options`` list becomes a
``Literal`` so the model cannot invent a value, and a long one stays a plain
string because a fifty-member enum is token waste.

One deliberate divergence (decision 6.1): ``SECRET`` fields are **never**
arguments. Langflow lets a ``SecretStrInput`` become one, which puts an API
key in the model's context. Same family as ``comparison.py``'s refusal to
``eval()`` — a security stance, not a parity gap.

Pure and total, like ``handles.py``: no I/O, one answer per input.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, create_model

from domain.flows.handles import visible_inputs
from models.flows import ComponentTemplate, FieldType, InputField

#: Beyond this many options an enum costs more tokens than it saves.
MAX_OPTIONS_FOR_TOOL_ENUM = 12

#: Fields that configure tool mode itself rather than being arguments to it.
_TOOL_CONFIG_FIELDS = frozenset({"tool_mode", "tool_name"})

_FIELD_TYPE_TO_PYTHON: dict[FieldType, type] = {
    FieldType.STR: str,
    FieldType.PROMPT: str,
    FieldType.CODE: str,
    FieldType.FILE: str,
    FieldType.INT: int,
    FieldType.FLOAT: float,
    FieldType.SLIDER: float,
    FieldType.BOOL: bool,
    FieldType.JSON: dict,
    FieldType.TABLE: dict,
    FieldType.OPTIONS: str,
    FieldType.MULTISELECT: list,
}


def tool_argument_fields(
    template: ComponentTemplate, values: dict[str, Any] | None = None
) -> dict[str, InputField]:
    """The fields a caller may set per tool call.

    Four exclusions, each with a reason:

    - ``SECRET`` — decision 6.1: a key must not enter the model's context.
    - ``advanced`` — the flow author's tuning, not a per-call choice.
    - ``tool_mode`` / ``tool_name`` — they configure the tool itself; exposing
      the name would let the model rename what it is calling.
    - **anything the node already stores a value for** — the author pinned it.
      Data Operations is the case that makes this matter: without it a tool
      configured as "count words" would advertise all thirty operations and
      every field of each, and the model could flip ``operation`` to something
      else, so the tool would no longer do what its own name says.

    Visibility is honoured too: a field hidden by ``show_when`` for these
    values is not an argument, because it does not apply to this
    configuration.
    """
    stored = values or {}
    visible = visible_inputs(template, stored)
    return {
        name: field
        for name, field in visible.items()
        if field.type is not FieldType.SECRET
        and not field.advanced
        and name not in _TOOL_CONFIG_FIELDS
        and stored.get(name) in (None, "")
    }


def _annotation(field: InputField) -> Any:
    if field.type is FieldType.MULTISELECT:
        return list[str]
    if (
        field.type is FieldType.OPTIONS
        and field.options
        and len(field.options) <= MAX_OPTIONS_FOR_TOOL_ENUM
    ):
        return Literal[tuple(field.options)]  # type: ignore[return-value]
    return _FIELD_TYPE_TO_PYTHON.get(field.type, str)


def build_args_schema(
    template: ComponentTemplate, values: dict[str, Any] | None = None
) -> type[BaseModel]:
    """A Pydantic model describing this component's tool arguments.

    ``values`` are the node's stored values: they decide which fields are
    visible and which the author has already pinned.
    """
    fields: dict[str, Any] = {}
    for name, field in tool_argument_fields(template, values).items():
        annotation = _annotation(field)
        description = field.info or field.display_name
        if field.required:
            fields[name] = (annotation, Field(description=description))
        else:
            fields[name] = (annotation, Field(default=field.value, description=description))
    return create_model(f"{template.type}Args", **fields)
