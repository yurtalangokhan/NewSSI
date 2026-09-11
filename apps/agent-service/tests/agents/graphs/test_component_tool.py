"""Tests for a flow component used as an agent tool.

The bridge must run the component's *own* node function — the same code the
flow would run — so a tool call and a flow step cannot drift apart. It must
also leave no trace in the flow's state: a tool call gets a fresh one.
"""

from __future__ import annotations

import pytest

from agents.graphs.flow_builder import (
    ResolvedResources,
    derive_tool_name,
    make_component_tool,
)
from models.flows import FlowNode


@pytest.fixture(autouse=True)
def _fake_model_env(monkeypatch):
    monkeypatch.setenv("USE_FAKE_MODEL", "true")


def _ops(**values) -> FlowNode:
    base = {"tool_mode": True, "operation": "Case Conversion", "case_type": "uppercase"}
    base.update(values)
    return FlowNode(id="Operations-a1b2c3d4", type="Operations", values=base)


# ---------------------------------------------------------------------------
# Naming
# ---------------------------------------------------------------------------


def test_the_tool_name_falls_back_to_the_node_id():
    """The canvas already generates ids in a `<type>-<short id>` shape."""
    assert derive_tool_name(_ops()) == "Operations-a1b2c3d4"


def test_a_configured_tool_name_wins():
    assert derive_tool_name(_ops(tool_name="metni_temizle")) == "metni_temizle"


def test_a_tool_name_is_formatted_to_the_allowed_character_set():
    """Model-facing tool names must match ^[a-zA-Z0-9_-]+$, as Langflow's
    `_format_tool_name` enforces."""
    assert derive_tool_name(_ops(tool_name="metni temizle!")) == "metni-temizle-"


def test_a_blank_tool_name_falls_back_rather_than_producing_an_empty_name():
    assert derive_tool_name(_ops(tool_name="   ")) == "Operations-a1b2c3d4"


# ---------------------------------------------------------------------------
# Calling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_calling_the_tool_runs_the_components_own_node_function():
    tool = make_component_tool(_ops(), ResolvedResources())
    assert await tool.coroutine(text_input="merhaba") == "MERHABA"


@pytest.mark.asyncio
async def test_the_arguments_override_the_stored_values_for_that_call_only():
    node = _ops(text_input="kayitli")
    tool = make_component_tool(node, ResolvedResources())
    assert await tool.coroutine(text_input="cagridan") == "CAGRIDAN"
    # The node's stored values are untouched, so the next call is unaffected.
    assert node.values["text_input"] == "kayitli"


@pytest.mark.asyncio
async def test_a_stored_value_the_call_does_not_mention_still_applies():
    tool = make_component_tool(_ops(case_type="swapcase"), ResolvedResources())
    assert await tool.coroutine(text_input="AbC") == "aBc"


@pytest.mark.asyncio
async def test_a_json_producing_operation_returns_its_object():
    node = _ops(operation="Word Count", count_words=True, count_characters=False, count_lines=False)
    tool = make_component_tool(node, ResolvedResources())
    result = await tool.coroutine(text_input="bir iki uc")
    assert result["word_count"] == 3


@pytest.mark.asyncio
async def test_two_calls_do_not_leak_into_each_other():
    """Each call builds a fresh state, so nothing from the first is visible."""
    tool = make_component_tool(_ops(), ResolvedResources())
    assert await tool.coroutine(text_input="bir") == "BIR"
    assert await tool.coroutine(text_input="iki") == "IKI"


# ---------------------------------------------------------------------------
# What the model sees
# ---------------------------------------------------------------------------


def test_the_tool_description_comes_from_the_component():
    tool = make_component_tool(_ops(), ResolvedResources())
    assert "Text, JSON" in tool.description


def test_the_tool_advertises_only_what_the_author_left_open():
    """The author pinned `operation` and `case_type`; the model supplies the
    text. Advertising the pinned fields would let the model change what the
    tool does, so the tool would no longer match its own name."""
    tool = make_component_tool(_ops(), ResolvedResources())
    assert set(tool.args_schema.model_fields) == {"text_input"}


def test_fields_belonging_to_other_operations_are_not_advertised():
    """Data Operations has thirty operations' worth of fields. Only the ones
    `show_when` makes visible for this configuration are arguments."""
    node = _ops(operation="Word Count", count_words=None, count_characters=None, count_lines=None)
    tool = make_component_tool(node, ResolvedResources())
    assert set(tool.args_schema.model_fields) == {
        "text_input",
        "count_words",
        "count_characters",
        "count_lines",
    }
    assert "merge_how" not in tool.args_schema.model_fields


def test_the_tool_does_not_advertise_the_tool_mode_fields():
    tool = make_component_tool(_ops(), ResolvedResources())
    assert "tool_mode" not in tool.args_schema.model_fields
    assert "tool_name" not in tool.args_schema.model_fields


# ---------------------------------------------------------------------------
# Reaching the agent
# ---------------------------------------------------------------------------


def _tool_flow(*, tool_name: str = "web_ara") -> dict:
    return {
        "nodes": [
            {"id": "in-1", "type": "ChatInput"},
            {
                "id": "ws-1",
                "type": "WebSearch",
                "values": {"tool_mode": True, "tool_name": tool_name},
            },
            {"id": "agent-1", "type": "ReActAgent", "values": {"system_prompt": "Ara."}},
            {"id": "out-1", "type": "ChatOutput"},
        ],
        "edges": [
            {
                "id": "e1",
                "source": "in-1",
                "sourceHandle": "message",
                "target": "agent-1",
                "targetHandle": "input",
            },
            {
                "id": "e2",
                "source": "ws-1",
                "sourceHandle": "tool",
                "target": "agent-1",
                "targetHandle": "tools",
            },
            {
                "id": "e3",
                "source": "agent-1",
                "sourceHandle": "output",
                "target": "out-1",
                "targetHandle": "message",
            },
        ],
    }


@pytest.mark.asyncio
async def test_a_tool_mode_node_reaches_the_agent_as_a_tool():
    """The agent side is untouched: it resolves tools by name from the map the
    compiler hands it, and cannot tell an MCP tool from a flow component."""
    from agents.graphs.flow_builder import FlowGraphBuilder
    from models.flows import FlowSpec

    builder = FlowGraphBuilder()
    await builder.build(FlowSpec.model_validate(_tool_flow()))
    assert "web_ara" in builder.component_tools
    assert builder.component_tools["web_ara"].name == "web_ara"


@pytest.mark.asyncio
async def test_a_tool_mode_node_is_not_a_graph_node():
    """It is the agent's capability, not a step the flow runs."""
    from agents.graphs.flow_builder import FlowGraphBuilder
    from models.flows import FlowSpec

    graph = await FlowGraphBuilder().build(FlowSpec.model_validate(_tool_flow()))
    assert "ws-1" not in graph.get_graph().nodes


@pytest.mark.asyncio
async def test_the_tools_map_is_rebuilt_per_build_not_accumulated():
    from agents.graphs.flow_builder import FlowGraphBuilder
    from models.flows import FlowSpec

    builder = FlowGraphBuilder()
    await builder.build(FlowSpec.model_validate(_tool_flow(tool_name="bir")))
    await builder.build(FlowSpec.model_validate(_tool_flow(tool_name="iki")))
    assert set(builder.component_tools) == {"iki"}
