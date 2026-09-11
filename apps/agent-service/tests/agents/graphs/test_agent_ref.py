"""Tests for AgentRef — embedding an existing classic agent as a subgraph.

This is constraint #1's concrete proof at the compiler level: a flow can
reference a classic agent (react/supervisor/pipeline/...), and it runs
through the **unmodified** agents/graphs/builder.py, embedded exactly as
Task 0's spike proved. Read .tmp/flow-canvas-task-0-report.md before touching
this file — its three findings are this module's contract:

  1. Compile the embedded agent with checkpointer=None (parent flow owns
     persistence).
  2. Node id convention {type}-{short_id} — LangGraph puts this in the stream
     namespace for free.
  3. agents/graphs/builder.py is NOT modified. If satisfying a test here
     requires editing it, that's a stop-and-reconsider signal, not a green
     light.

AgentRef has no P1 registry template yet (P6 territory) — registered here as
a test-local fixture, the same pattern Task 3 used for agent_id/send_email
value-shapes ahead of their real templates landing.

Spec: .tmp/flow-canvas-design.md sections 4.5, 5.4.
Brief: .tmp/flow-canvas-task-12-brief.md
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from langchain_core.messages import HumanMessage

from agents.graphs.flow_builder import FlowGraphBuilder
from core.exceptions import FlowBuildError
from domain.flows.registry import ComponentRegistry, get_registry
from models.flows import (
    ComponentHandles,
    ComponentKind,
    ComponentTemplate,
    FlowSpec,
    Handle,
    PortType,
)


@pytest.fixture(autouse=True)
def _fake_model_env(monkeypatch):
    monkeypatch.setenv("USE_FAKE_MODEL", "true")


def _agent_ref_template() -> ComponentTemplate:
    return ComponentTemplate(
        type="AgentRef",
        category="test",
        display_name="Agent Reference",
        kind=ComponentKind.EXECUTION,
        handles=ComponentHandles(
            inputs=[Handle(name="input", types=[PortType.MESSAGE])],
            outputs=[Handle(name="output", types=[PortType.MESSAGE])],
        ),
    )


def _registry_with_agent_ref() -> ComponentRegistry:
    """A fresh registry: the real Core templates this test needs, plus the
    test-local AgentRef fixture. Not the shared global singleton — avoids
    cross-test pollution from registering the same type twice."""
    real = get_registry()
    registry = ComponentRegistry()
    for type_name in ("ChatInput", "ChatOutput"):
        registry.register(real.get(type_name))
    registry.register(_agent_ref_template())
    return registry


def _flow_dict(agent_id: str) -> dict:
    return {
        "nodes": [
            {"id": "in-1", "type": "ChatInput"},
            {"id": "ref-1", "type": "AgentRef", "values": {"agent_id": agent_id}},
            {"id": "out-1", "type": "ChatOutput"},
        ],
        "edges": [
            {
                "id": "e1",
                "source": "in-1",
                "sourceHandle": "message",
                "target": "ref-1",
                "targetHandle": "input",
            },
            {
                "id": "e2",
                "source": "ref-1",
                "sourceHandle": "output",
                "target": "out-1",
                "targetHandle": "message",
            },
        ],
    }


class _FakeDefinition:
    def __init__(self, id, graph_schema, config):
        self.id = id
        self.graph_schema = graph_schema
        self._config = config

    def to_config(self):
        return self._config


class _FakeRepo:
    def __init__(self, definitions: dict):
        self._definitions = definitions

    async def get_by_id(self, definition_id):
        return self._definitions.get(definition_id)


# ---------------------------------------------------------------------------
# 12.1 — compiles and runs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_ref_compiles_existing_definition_as_subgraph():
    agent_id = uuid4()
    repo = _FakeRepo(
        {
            agent_id: _FakeDefinition(
                agent_id, "react", {"system_prompt": "Be helpful.", "mcp_tools": []}
            )
        }
    )
    spec = FlowSpec.model_validate(_flow_dict(str(agent_id)))

    graph = await FlowGraphBuilder(registry=_registry_with_agent_ref(), repository=repo).build(spec)

    result = await graph.ainvoke({"messages": [HumanMessage(content="hi")], "scratch": {}})
    assert len(result["messages"]) >= 2


# ---------------------------------------------------------------------------
# 12.2 — checkpointer=None for the embedded agent
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_ref_uses_no_checkpointer_of_its_own(monkeypatch):
    captured = {}
    from agents.graphs import builder as builder_module

    original_init = builder_module.GraphBuilder.__init__

    def _spy_init(self, *args, **kwargs):
        captured["checkpointer"] = kwargs.get("checkpointer", "NOT-PASSED")
        return original_init(self, *args, **kwargs)

    monkeypatch.setattr(builder_module.GraphBuilder, "__init__", _spy_init)

    agent_id = uuid4()
    repo = _FakeRepo(
        {agent_id: _FakeDefinition(agent_id, "react", {"system_prompt": "hi", "mcp_tools": []})}
    )
    spec = FlowSpec.model_validate(_flow_dict(str(agent_id)))

    await FlowGraphBuilder(registry=_registry_with_agent_ref(), repository=repo).build(spec)

    assert captured["checkpointer"] is None


# ---------------------------------------------------------------------------
# 12.4 — rejects a flow-backed target (design spec 5.4)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_ref_rejects_flow_backed_target():
    agent_id = uuid4()
    repo = _FakeRepo({agent_id: _FakeDefinition(agent_id, "flow", {})})
    spec = FlowSpec.model_validate(_flow_dict(str(agent_id)))

    with pytest.raises(FlowBuildError, match="flow"):
        await FlowGraphBuilder(registry=_registry_with_agent_ref(), repository=repo).build(spec)


# ---------------------------------------------------------------------------
# 12.5 — nested supervisor composition survives embedding
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_ref_preserves_nested_supervisor_composition():
    agent_id = uuid4()
    repo = _FakeRepo(
        {
            agent_id: _FakeDefinition(
                agent_id,
                "supervisor",
                {
                    "supervisor_prompt": "You supervise.",
                    "sub_agents": [
                        {"name": "worker_a", "system_prompt": "You are A.", "mcp_tools": []}
                    ],
                },
            )
        }
    )
    spec = FlowSpec.model_validate(_flow_dict(str(agent_id)))

    graph = await FlowGraphBuilder(registry=_registry_with_agent_ref(), repository=repo).build(spec)

    result = await graph.ainvoke({"messages": [HumanMessage(content="hi")], "scratch": {}})
    assert len(result["messages"]) >= 2


# ---------------------------------------------------------------------------
# 12.6 — streaming and tool events survive embedding (Task 0's findings,
# now against the real FlowGraphBuilder)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_ref_streaming_survives_embedding():
    agent_id = uuid4()
    repo = _FakeRepo(
        {
            agent_id: _FakeDefinition(
                agent_id, "react", {"system_prompt": "Be helpful.", "mcp_tools": []}
            )
        }
    )
    spec = FlowSpec.model_validate(_flow_dict(str(agent_id)))
    graph = await FlowGraphBuilder(registry=_registry_with_agent_ref(), repository=repo).build(spec)

    chunks = []
    namespaces = set()
    async for ns, chunk in graph.astream(
        {"messages": [HumanMessage(content="hi")], "scratch": {}},
        stream_mode="messages",
        subgraphs=True,
    ):
        namespaces.add(str(ns))
        msg = chunk[0] if isinstance(chunk, tuple) else chunk
        if getattr(msg, "content", None):
            chunks.append(msg.content)

    assert len(chunks) > 0
    assert any("ref-1" in ns for ns in namespaces)  # node-id convention, Task 0 finding B


# ---------------------------------------------------------------------------
# 12.7 — missing definition raises clearly
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_ref_missing_definition_raises_clearly():
    agent_id = uuid4()
    repo = _FakeRepo({})  # empty — nothing registered
    spec = FlowSpec.model_validate(_flow_dict(str(agent_id)))

    with pytest.raises(FlowBuildError, match=str(agent_id)):
        await FlowGraphBuilder(registry=_registry_with_agent_ref(), repository=repo).build(spec)
