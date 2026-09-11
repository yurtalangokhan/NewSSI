"""Tests for SetVariable — the named-variable space over scratch.

This is our own component, not a Langflow port: Langflow's Notify/Listen are a
pub-sub pair whose point is waking a disconnected vertex, which LangGraph's
static graph does not do. Named storage is a narrower, honestly-named job.

Node functions are exercised directly, as in test_execution_nodes.py.
"""

from __future__ import annotations

import pytest
from langchain_core.messages import HumanMessage

from agents.graphs.flow_builder import (
    FlowGraphBuilder,
    _make_prompt_template_node,
    _make_set_variable_node,
)
from models.flows import FlowNode, FlowSpec


@pytest.fixture(autouse=True)
def _fake_model_env(monkeypatch):
    monkeypatch.setenv("USE_FAKE_MODEL", "true")


@pytest.mark.asyncio
async def test_stores_the_configured_value_under_its_name():
    node = FlowNode(id="set-1", type="SetVariable", values={"name": "tone", "value": "cheerful"})
    result = await _make_set_variable_node(node)({"messages": [], "scratch": {}}, None)
    assert result == {"scratch": {"tone": "cheerful"}}


@pytest.mark.asyncio
async def test_falls_back_to_the_latest_message_text_when_value_is_blank():
    node = FlowNode(id="set-1", type="SetVariable", values={"name": "echo", "value": ""})
    state = {"messages": [HumanMessage(content="hello there")], "scratch": {}}
    result = await _make_set_variable_node(node)(state, None)
    assert result == {"scratch": {"echo": "hello there"}}


@pytest.mark.asyncio
async def test_a_blank_name_stores_nothing():
    """The validator rejects this, but the compiler must not crash on a spec
    that reached it unvalidated."""
    node = FlowNode(id="set-1", type="SetVariable", values={"name": "", "value": "x"})
    assert await _make_set_variable_node(node)({"messages": [], "scratch": {}}, None) == {}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("current", "expected"),
    [(None, ["a"]), (["z"], ["z", "a"]), ("z", ["z", "a"])],
)
async def test_append_accumulates_into_a_list(current, expected):
    node = FlowNode(
        id="set-1", type="SetVariable", values={"name": "seen", "value": "a", "append": True}
    )
    scratch = {} if current is None else {"seen": current}
    result = await _make_set_variable_node(node)({"messages": [], "scratch": scratch}, None)
    assert result == {"scratch": {"seen": expected}}


@pytest.mark.asyncio
async def test_a_stored_variable_resolves_as_a_prompt_placeholder():
    """The whole point of named variables: {name} resolves in a template,
    alongside the node-id keys scratch already holds."""
    set_node = FlowNode(id="set-1", type="SetVariable", values={"name": "tone", "value": "warm"})
    written = await _make_set_variable_node(set_node)({"messages": [], "scratch": {}}, None)

    tpl_node = FlowNode(id="tpl-1", type="PromptTemplate", values={"template": "be {tone}"})
    rendered = await _make_prompt_template_node(tpl_node)(
        {"messages": [], "scratch": written["scratch"]}, None
    )
    assert rendered["scratch"] == {"tpl-1": "be warm"}


@pytest.mark.asyncio
async def test_set_variable_compiles_and_forwards_the_conversation():
    """ChatInput -> SetVariable -> ChatOutput is a type-valid shape
    (MESSAGE throughout); the node must be a transparent passthrough."""
    spec = FlowSpec.model_validate(
        {
            "nodes": [
                {"id": "in-1", "type": "ChatInput"},
                {"id": "set-1", "type": "SetVariable", "values": {"name": "tone", "value": "warm"}},
                {"id": "out-1", "type": "ChatOutput"},
            ],
            "edges": [
                {
                    "id": "e1",
                    "source": "in-1",
                    "sourceHandle": "message",
                    "target": "set-1",
                    "targetHandle": "input",
                },
                {
                    "id": "e2",
                    "source": "set-1",
                    "sourceHandle": "output",
                    "target": "out-1",
                    "targetHandle": "message",
                },
            ],
        }
    )
    graph = await FlowGraphBuilder().build(spec)

    result = await graph.ainvoke({"messages": [HumanMessage(content="hi")], "scratch": {}})

    assert result["scratch"]["tone"] == "warm"
    assert [m.content for m in result["messages"]] == ["hi"]
