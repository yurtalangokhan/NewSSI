"""Spec T7/Task 36: a failed DynamicAgent load must fail loudly, not degrade
into a cached "helpful assistant" graph that silently answered every future
turn as if nothing were wrong.
"""

import pytest

from agents.implementations.dynamic_agent import DynamicAgent


@pytest.mark.asyncio
async def test_load_raises_instead_of_falling_back(monkeypatch):
    agent = DynamicAgent(agent_config={"name": "broken-agent"})

    async def failing_load_mcp_tools():
        raise RuntimeError("MCP server unreachable")

    monkeypatch.setattr(agent, "_load_mcp_tools", failing_load_mcp_tools)

    with pytest.raises(RuntimeError, match="MCP server unreachable"):
        await agent.load()

    # No placeholder graph was cached in place of the real one.
    assert agent._default_graph is None
    assert agent._graph is None
    assert agent._loaded is False


@pytest.mark.asyncio
async def test_a_failed_load_can_be_retried(monkeypatch):
    """A transient failure must not be permanent: the next load() attempt
    (e.g. after the dependency recovers) should try again, not stay stuck."""
    agent = DynamicAgent(agent_config={"name": "recovering-agent"})

    call_count = 0

    async def flaky_load_mcp_tools():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("transient failure")

    monkeypatch.setattr(agent, "_load_mcp_tools", flaky_load_mcp_tools)

    async def fake_create_graph():
        return object()

    monkeypatch.setattr(agent, "_create_graph_from_config_async", fake_create_graph)

    class _FakeComposed:
        async def load(self):
            return None

    monkeypatch.setattr(
        "agents.implementations.dynamic_agent.AgentComposer.assemble",
        lambda **_kwargs: _FakeComposed(),
    )

    with pytest.raises(RuntimeError):
        await agent.load()

    await agent.load()  # retried after the transient failure clears
    assert agent._loaded is True
    assert agent._graph is not None
