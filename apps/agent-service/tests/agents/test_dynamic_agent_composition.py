"""Tests for DynamicAgent composition graph loading."""

import pytest


@pytest.mark.asyncio
async def test_dynamic_agent_load_uses_async_builder_for_sub_agent_ids(monkeypatch):
    """DynamicAgent.load should use GraphBuilder.build_async for referenced sub-agents."""
    from agents.dynamic_agent import DynamicAgent

    calls = {}

    class FakeGraph:
        pass

    class FakeBuilder:
        def __init__(self, **kwargs):
            calls["builder_kwargs"] = kwargs
            self.repository = None

        async def build_async(self, schema_type, config):
            calls["schema_type"] = schema_type
            calls["config"] = config
            calls["repository_set"] = self.repository is not None
            return FakeGraph()

        def build(self, *_args, **_kwargs):
            raise AssertionError("DynamicAgent.load should not use sync build")

    async def fake_load_mcp_tools(self):
        self._mcp_tools_map = {}

    monkeypatch.setattr("agents.dynamic_agent.GraphBuilder", FakeBuilder)
    monkeypatch.setattr(DynamicAgent, "_load_mcp_tools", fake_load_mcp_tools)

    agent = DynamicAgent(
        {
            "name": "team",
            "graph_schema": "supervisor",
            "sub_agent_ids": ["00000000-0000-0000-0000-000000000001"],
        }
    )

    await agent.load()

    assert isinstance(agent.get_graph(), FakeGraph)
    assert calls["config"]["sub_agent_ids"] == ["00000000-0000-0000-0000-000000000001"]
    assert calls["repository_set"] is True
