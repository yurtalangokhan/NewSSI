"""Tests for FlowAgent — mirrors dynamic_agent.py's shape deliberately: same
cache pattern, same fallback-on-load-failure behavior, same LazyLoadingAgent
base. A sibling class, not a subclass, per design spec section 6.2.

Spec: .tmp/flow-canvas-design.md sections 6.2, 9.1.
Brief: .tmp/flow-canvas-task-13-brief.md
"""

from __future__ import annotations

import pytest
from langchain_core.messages import HumanMessage
from langgraph.graph.state import CompiledStateGraph

from agents.flow_agent import FlowAgent, cache_agent, get_cached_agent, invalidate_agent_cache


@pytest.fixture(autouse=True)
def _fake_model_env(monkeypatch):
    monkeypatch.setenv("USE_FAKE_MODEL", "true")


def _valid_flow_spec() -> dict:
    return {
        "nodes": [
            {"id": "in-1", "type": "ChatInput"},
            {"id": "agent-1", "type": "ZeroShotAgent", "values": {"system_prompt": "Be terse."}},
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
                "source": "agent-1",
                "sourceHandle": "output",
                "target": "out-1",
                "targetHandle": "message",
            },
        ],
    }


# ---------------------------------------------------------------------------
# 13.1 — loads and compiles a valid spec
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_flow_agent_loads_and_compiles_a_valid_spec():
    agent = FlowAgent(_valid_flow_spec(), definition_id="def-1")

    await agent.load()

    assert agent._load_failed is False
    assert isinstance(agent.get_graph(), CompiledStateGraph)


# ---------------------------------------------------------------------------
# 13.2 — falls back on invalid spec
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_flow_agent_falls_back_on_invalid_spec():
    agent = FlowAgent({"nodes": "this is not a valid spec"}, definition_id="def-2")

    await agent.load()  # must not raise

    assert agent._load_failed is True
    assert isinstance(agent.get_graph(), CompiledStateGraph)
    result = await agent.get_graph().ainvoke({"messages": [HumanMessage(content="hi")]})
    assert len(result["messages"]) >= 2  # a real, if apologetic, response


# ---------------------------------------------------------------------------
# 13.2b — structurally-invalid spec (no Chat Output) is refused, not run
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_flow_agent_refuses_a_structurally_invalid_spec():
    """A spec that never passed publish (e.g. a client that bypassed the
    create-page gate) must not compile into a graph that silently echoes
    the user's input — _build_graph runs the structural validator and the
    load falls back instead."""
    spec = {
        "nodes": [
            {"id": "in-1", "type": "ChatInput"},
            {"id": "agent-1", "type": "ZeroShotAgent", "values": {"system_prompt": "Hi."}},
        ],
        "edges": [
            {
                "id": "e1",
                "source": "in-1",
                "sourceHandle": "message",
                "target": "agent-1",
                "targetHandle": "input",
            },
        ],
    }
    agent = FlowAgent(spec, definition_id="def-no-exit")

    from core.exceptions import FlowValidationError

    with pytest.raises(FlowValidationError):
        await agent._build_graph()

    await agent.load()  # must not raise — falls back instead

    assert agent._load_failed is True
    assert isinstance(agent.get_graph(), CompiledStateGraph)


# ---------------------------------------------------------------------------
# 13.3 / 13.4 — caching mirrors dynamic_agent.py's pattern
# ---------------------------------------------------------------------------


def test_flow_agent_caches_by_definition_id():
    agent = FlowAgent(_valid_flow_spec(), definition_id="def-3")
    cache_agent("def-3", agent)

    assert get_cached_agent("def-3") is agent


def test_flow_agent_invalidate_cache_removes_entry():
    agent = FlowAgent(_valid_flow_spec(), definition_id="def-4")
    cache_agent("def-4", agent)

    invalidate_agent_cache("def-4")

    assert get_cached_agent("def-4") is None


# ---------------------------------------------------------------------------
# 13.5 — real end-to-end streaming
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_flow_agent_streams_end_to_end():
    agent = FlowAgent(_valid_flow_spec(), definition_id="def-5")
    await agent.load()

    chunks = []
    async for chunk in agent.get_graph().astream(
        {"messages": [HumanMessage(content="hi")], "scratch": {}}, stream_mode="messages"
    ):
        msg = chunk[0] if isinstance(chunk, tuple) else chunk
        if getattr(msg, "content", None):
            chunks.append(msg.content)

    assert len(chunks) > 0


# ---------------------------------------------------------------------------
# 13.6 — name falls back sensibly
# ---------------------------------------------------------------------------


def test_flow_agent_name_falls_back_sensibly_without_a_persona_name():
    agent = FlowAgent(_valid_flow_spec(), definition_id="def-6")

    assert "def-6" in agent.name


def test_flow_agent_reports_flow_graph_schema():
    agent = FlowAgent(_valid_flow_spec(), definition_id="def-7")

    assert agent.graph_schema == "flow"
    assert agent.agent_type == "flow"


# ---------------------------------------------------------------------------
# 13.10 — GraphSchemaType.FLOW is registered
# ---------------------------------------------------------------------------


def test_flow_graph_schema_type_is_registered():
    from agents.graphs.schemas import GraphSchemaType, get_all_schemas, get_schema

    schema = get_schema("flow")
    assert schema is not None
    assert schema.schema_type == GraphSchemaType.FLOW

    # Registering a new schema type must not perturb existing consumers
    # (e.g. AgentDefinitionsRoute's schemas/list endpoint) — the six classic
    # schemas are all still present alongside it.
    all_types = {s.schema_type.value for s in get_all_schemas()}
    assert all_types == {
        "zero_shot",
        "react",
        "supervisor",
        "pipeline",
        "plan_execute",
        "self_reflect",
        "flow",
    }
