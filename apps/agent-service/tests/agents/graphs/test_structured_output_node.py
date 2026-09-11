"""Tests for Structured Output — an LLM forced to answer in a schema.

A faithful port of Langflow's StructuredOutputComponent: a schema table
becomes a Pydantic model, the model is bound with ``with_structured_output``,
and the result lands in ``scratch[node.id]``.

Langflow wraps the schema in ``objects: list[Model]`` on purpose — its own
format instructions say "Extract ALL relevant instances" — so the stored value
is always a **list** of objects, even when the text yields one.
"""

from __future__ import annotations

import json

import pytest
from langchain_core.messages import HumanMessage

from agents.graphs.flow_builder import _make_structured_output_node
from core.exceptions import FlowBuildError
from models.flows import FlowNode


@pytest.fixture(autouse=True)
def _fake_model_env(monkeypatch):
    monkeypatch.setenv("USE_FAKE_MODEL", "true")


SCHEMA = [
    {"name": "baslik", "description": "Faturanin basligi", "type": "str", "multiple": False},
    {"name": "tutar", "description": "Toplam tutar", "type": "float", "multiple": False},
]


def _node(**values) -> FlowNode:
    base = {"output_schema": SCHEMA, "schema_name": "Fatura"}
    base.update(values)
    return FlowNode(id="so-1", type="StructuredOutput", values=base)


class _StructuredSpy:
    """Stands in for a bound chat model.

    ``with_structured_output`` returns a runnable that yields an instance of
    the wrapper model, so the spy builds one from the schema it is handed —
    which is also how the test asserts the wrapper really was a list wrapper.
    """

    def __init__(self, objects=None):
        self._objects = (
            objects if objects is not None else [{"baslik": "Nisan faturasi", "tutar": 120.5}]
        )
        self.bound_to = None
        self.prompts: list[list] = []

    def with_structured_output(self, schema):
        self.bound_to = schema
        return self

    async def ainvoke(self, messages):
        self.prompts.append(messages)
        return self.bound_to(objects=self._objects)


async def _run(node, model, text="Nisan faturasi 120.5 TL", scratch=None, port_sources=None):
    fn = _make_structured_output_node(node, model, port_sources)
    return await fn({"messages": [HumanMessage(content=text)], "scratch": scratch or {}}, None)


# ---------------------------------------------------------------------------
# The extraction itself
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_extracted_objects_land_under_the_node_id():
    spy = _StructuredSpy()
    result = await _run(_node(), spy)
    assert result["scratch"]["so-1"] == [{"baslik": "Nisan faturasi", "tutar": 120.5}]


@pytest.mark.asyncio
async def test_the_result_is_always_a_list_even_for_one_object():
    """Langflow wraps the schema in `objects: list[Model]` so an extraction can
    return every match. A caller can rely on the shape."""
    spy = _StructuredSpy(objects=[{"baslik": "Tek", "tutar": 1.0}])
    result = await _run(_node(), spy)
    assert isinstance(result["scratch"]["so-1"], list)


@pytest.mark.asyncio
async def test_several_objects_all_survive():
    spy = _StructuredSpy(
        objects=[
            {"baslik": "Bir", "tutar": 1.0},
            {"baslik": "Iki", "tutar": 2.0},
        ]
    )
    result = await _run(_node(), spy)
    assert [o["baslik"] for o in result["scratch"]["so-1"]] == ["Bir", "Iki"]


@pytest.mark.asyncio
async def test_the_json_also_flows_on_as_a_message():
    """The structured value rides in scratch; the message keeps the branch
    readable and lets the result reach an agent or Chat Output."""
    spy = _StructuredSpy()
    result = await _run(_node(), spy)
    emitted = json.loads(result["messages"][-1].content)
    assert emitted == [{"baslik": "Nisan faturasi", "tutar": 120.5}]


@pytest.mark.asyncio
async def test_the_model_is_bound_to_a_schema_built_from_the_table():
    spy = _StructuredSpy()
    await _run(_node(), spy)
    assert spy.bound_to is not None
    # The wrapper carries the list; the inner model carries the declared fields.
    from typing import get_args

    inner = get_args(spy.bound_to.model_fields["objects"].annotation)[0]
    assert set(inner.model_fields) == {"baslik", "tutar"}
    assert inner.model_fields["baslik"].description == "Faturanin basligi"


# ---------------------------------------------------------------------------
# What the model is asked
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_format_instructions_are_sent_as_the_system_message():
    spy = _StructuredSpy()
    await _run(_node(system_prompt="Sadece JSON dondur."), spy)
    assert spy.prompts[0][0].content == "Sadece JSON dondur."


@pytest.mark.asyncio
async def test_the_latest_message_is_what_gets_extracted_by_default():
    spy = _StructuredSpy()
    await _run(_node(), spy, text="Mart faturasi 9 TL")
    assert "Mart faturasi 9 TL" in spy.prompts[0][-1].content


@pytest.mark.asyncio
async def test_the_input_source_field_overrides_the_latest_message():
    spy = _StructuredSpy()
    await _run(_node(input_source="belge"), spy, text="yoksay", scratch={"belge": "asil metin"})
    assert "asil metin" in spy.prompts[0][-1].content


@pytest.mark.asyncio
async def test_a_wired_input_text_port_beats_the_field():
    """Same precedence rule as every other port: wired port, then the field,
    then the latest message."""
    spy = _StructuredSpy()
    await _run(
        _node(input_source="belge"),
        spy,
        text="yoksay",
        scratch={"belge": "alan", "up-1": "porttan"},
        port_sources={"input_text": "up-1"},
    )
    assert "porttan" in spy.prompts[0][-1].content


# ---------------------------------------------------------------------------
# Refusals
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_empty_schema_is_a_clear_build_error():
    with pytest.raises(FlowBuildError, match="output schema"):
        _make_structured_output_node(_node(output_schema=[]), _StructuredSpy())


@pytest.mark.asyncio
async def test_a_model_without_structured_output_support_is_a_clear_error():
    class _Plain:
        async def ainvoke(self, messages):
            return HumanMessage(content="nope")

    fn = _make_structured_output_node(_node(), _Plain())
    with pytest.raises(FlowBuildError, match="structured output"):
        await fn({"messages": [HumanMessage(content="x")], "scratch": {}}, None)
