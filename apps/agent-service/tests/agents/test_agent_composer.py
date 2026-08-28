"""Tests for the AgentComposer / AgentFactory facade and LangGraph adapter.

These lock the new canonical composition path introduced in ASC-5:

* ``AgentComposer.assemble`` wraps a built compiled graph in a ``ComposedAgent``
  (ASC-4) that owns the runtime lifecycle.
* ``LangGraphExecutableAgent`` adapts the compiled graph to the
  ``ExecutableAgent`` protocol used by ``ComposedAgent``.
* ``AgentFactory.create`` is the resolver facade entrypoint.
"""

from __future__ import annotations

import pytest

from agent_composition.adapters.langgraph.executable_agent import LangGraphExecutableAgent
from agent_composition.application.compose_agent import AgentComposer, AgentFactory
from agent_composition.domain.definitions import RuntimePolicyConfig
from agent_composition.domain.ports import AgentRunRequest, StateRequest


class FakeGraph:
    """Minimal stand-in for a compiled LangGraph graph."""

    def __init__(self) -> None:
        self.ainvoke_calls: list[tuple[object, object]] = []
        self.closed = False

    async def ainvoke(self, inputs: object, config: object = None) -> dict:
        self.ainvoke_calls.append((inputs, config))
        return {"messages": [{"role": "ai", "content": "ok"}]}

    async def astream(self, inputs: object, config: object = None):
        yield {"chunk": 1}
        yield {"chunk": 2}

    async def aget_state(self, config: object = None) -> dict:
        return {"values": {"x": 1}, "metadata": {}}

    async def aupdate_state(self, config: object = None, values: object = None) -> dict:
        return {"values": values, "metadata": {}}

    async def aget_state_history(self, config: object = None):
        yield {"values": {"x": 1}, "metadata": {}}

    async def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_composer_assemble_wraps_graph_in_composed_agent():
    graph = FakeGraph()
    composed = AgentComposer.assemble(graph=graph, runtime_policy_config=RuntimePolicyConfig())

    assert isinstance(composed.executable_agent, LangGraphExecutableAgent)
    assert composed.executable_agent.graph is graph

    await composed.load()
    assert composed.is_loaded

    # State delegation bypasses runtime policies and reaches the graph directly.
    state = await composed.aget_state(StateRequest(thread_id="t1"))
    assert state.values == {"x": 1}

    # Streaming delegation reaches the graph directly.
    chunks = [chunk async for chunk in composed.astream(AgentRunRequest(inputs={}))]
    assert len(chunks) == 2

    await composed.close()
    assert composed.is_loaded is False
    assert graph.closed


@pytest.mark.asyncio
async def test_composed_agent_invoke_returns_domain_result():
    graph = FakeGraph()
    composed = AgentComposer.assemble(graph=graph)
    await composed.load()

    result = await composed.ainvoke(AgentRunRequest(inputs={"messages": []}))
    assert result.output == {"messages": [{"role": "ai", "content": "ok"}]}
    assert graph.ainvoke_calls


def test_factory_exposes_resolver_entrypoint():
    # AgentFactory.create is the canonical resolver facade for dynamic agents.
    assert hasattr(AgentFactory, "create")
