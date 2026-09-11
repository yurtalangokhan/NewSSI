"""Tests for the tool argument schema.

Mirrors Langflow's `create_input_schema`: field type to Python type, short
option lists to Literal, optional fields carrying their default, `info` as the
description the model reads.

Secrets are excluded on purpose (decision 6.1) — Langflow lets a
SecretStrInput become a tool argument, which puts an API key in the model's
context.
"""

from __future__ import annotations

import pytest

from domain.flows.tool_schema import build_args_schema, tool_argument_fields
from models.flows import (
    ComponentHandles,
    ComponentKind,
    ComponentTemplate,
    FieldType,
    Handle,
    InputField,
    PortType,
)


def _template(**inputs) -> ComponentTemplate:
    return ComponentTemplate(
        type="X",
        category="web",
        display_name="X",
        icon="SvgSearch",
        kind=ComponentKind.EXECUTION,
        inputs=inputs,
        handles=ComponentHandles(outputs=[Handle(name="output", types=[PortType.MESSAGE])]),
    )


def test_a_plain_field_becomes_a_string_argument():
    schema = build_args_schema(
        _template(
            query=InputField(type=FieldType.STR, display_name="Query", required=True),
        )
    )
    assert schema.model_fields["query"].annotation is str


def test_numeric_and_boolean_types_map_across():
    schema = build_args_schema(
        _template(
            n=InputField(type=FieldType.INT, display_name="N"),
            f=InputField(type=FieldType.FLOAT, display_name="F"),
            b=InputField(type=FieldType.BOOL, display_name="B"),
        )
    )
    assert schema.model_fields["n"].annotation is int
    assert schema.model_fields["f"].annotation is float
    assert schema.model_fields["b"].annotation is bool


def test_prompt_and_code_fields_are_strings_too():
    schema = build_args_schema(
        _template(
            p=InputField(type=FieldType.PROMPT, display_name="P"),
            c=InputField(type=FieldType.CODE, display_name="C"),
        )
    )
    assert schema.model_fields["p"].annotation is str
    assert schema.model_fields["c"].annotation is str


def test_a_short_option_list_becomes_a_literal_so_the_model_cannot_invent_a_value():
    schema = build_args_schema(
        _template(
            mode=InputField(
                type=FieldType.OPTIONS, display_name="Mode", options=["fast", "slow"], value="fast"
            ),
        )
    )
    assert set(schema.model_fields["mode"].annotation.__args__) == {"fast", "slow"}


def test_a_long_option_list_stays_a_string_to_avoid_token_waste():
    """Langflow's MAX_OPTIONS_FOR_TOOL_ENUM guard, for the same reason."""
    schema = build_args_schema(
        _template(
            model=InputField(
                type=FieldType.OPTIONS, display_name="Model", options=[f"m{i}" for i in range(50)]
            ),
        )
    )
    assert schema.model_fields["model"].annotation is str


def test_an_options_field_with_no_declared_options_is_a_string():
    """A dynamic `options_source` list is not known at build time."""
    schema = build_args_schema(
        _template(
            provider=InputField(
                type=FieldType.OPTIONS, display_name="Provider", options_source="llm.providers"
            ),
        )
    )
    assert schema.model_fields["provider"].annotation is str


def test_a_multiselect_becomes_a_list_of_strings():
    schema = build_args_schema(
        _template(
            tags=InputField(type=FieldType.MULTISELECT, display_name="Tags", options=["a", "b"]),
        )
    )
    assert schema.model_fields["tags"].annotation == list[str]


def test_json_and_table_fields_become_dicts():
    schema = build_args_schema(
        _template(
            j=InputField(type=FieldType.JSON, display_name="J"),
            t=InputField(type=FieldType.TABLE, display_name="T"),
        )
    )
    assert schema.model_fields["j"].annotation is dict
    assert schema.model_fields["t"].annotation is dict


def test_the_info_text_becomes_the_argument_description():
    schema = build_args_schema(
        _template(
            query=InputField(type=FieldType.STR, display_name="Query", info="What to search for"),
        )
    )
    assert schema.model_fields["query"].description == "What to search for"


def test_a_field_without_info_falls_back_to_its_display_name():
    schema = build_args_schema(
        _template(
            query=InputField(type=FieldType.STR, display_name="Search query"),
        )
    )
    assert schema.model_fields["query"].description == "Search query"


def test_an_optional_field_carries_its_default():
    schema = build_args_schema(
        _template(
            top_k=InputField(type=FieldType.INT, display_name="Top K", required=False, value=4),
        )
    )
    assert schema().top_k == 4


def test_a_required_field_has_no_default():
    schema = build_args_schema(
        _template(
            query=InputField(type=FieldType.STR, display_name="Query", required=True),
        )
    )
    with pytest.raises(Exception):
        schema()


def test_secret_fields_are_never_arguments():
    """Decision 6.1: an API key must not reach the model's context."""
    fields = tool_argument_fields(
        _template(
            query=InputField(type=FieldType.STR, display_name="Query"),
            api_key=InputField(type=FieldType.SECRET, display_name="API key"),
        )
    )
    assert set(fields) == {"query"}


def test_advanced_fields_are_not_arguments():
    """Advanced fields are the flow author's tuning, not something a model
    should choose per call. They keep their stored value."""
    fields = tool_argument_fields(
        _template(
            query=InputField(type=FieldType.STR, display_name="Query"),
            timeout=InputField(type=FieldType.INT, display_name="Timeout", advanced=True),
        )
    )
    assert set(fields) == {"query"}


def test_the_tool_mode_fields_are_not_arguments():
    """They configure the tool; exposing `tool_name` would let the model rename
    the thing it is calling."""
    fields = tool_argument_fields(
        _template(
            query=InputField(type=FieldType.STR, display_name="Query"),
            tool_name=InputField(type=FieldType.STR, display_name="Tool name"),
            tool_mode=InputField(type=FieldType.BOOL, display_name="Use as tool"),
        )
    )
    assert set(fields) == {"query"}


def test_a_template_with_no_eligible_fields_still_builds_an_empty_schema():
    schema = build_args_schema(
        _template(
            api_key=InputField(type=FieldType.SECRET, display_name="API key"),
        )
    )
    assert schema.model_fields == {}
