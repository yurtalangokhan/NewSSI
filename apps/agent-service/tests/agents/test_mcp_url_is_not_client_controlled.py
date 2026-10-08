"""configurable.mcp_url must not let a caller point the agent at an
arbitrary host, nor reload the shared self._mcp_tools cache on account of
a value nobody legitimately configured. Spec C3/T2 (reduced scope)."""

from unittest.mock import AsyncMock

import pytest

from agents.implementations.configurable_mcp_agent import ConfigurableMCPAgent
from core.security.mcp.mcp_url_policy import default_mcp_url


class DummyGraph:
    async def ainvoke(self, input, config=None, **kwargs):
        return {"messages": []}


@pytest.mark.asyncio
async def test_ainvoke_never_reloads_tools_for_a_disallowed_mcp_url():
    agent = ConfigurableMCPAgent()
    agent._loaded = True
    agent._graph = DummyGraph()
    existing_tools = {"existing_tool": object()}
    agent._mcp_tools = existing_tools
    agent._load_mcp_tools = AsyncMock()
    agent._save_memory_from_output = AsyncMock()
    agent._prepare_memory_context = AsyncMock(return_value=({"messages": []}, {}, "user-1", ""))

    await agent.ainvoke(
        {"messages": []},
        config={
            "configurable": {
                "user_id": "user-1",
                "mcp_url": "http://attacker.example/mcp",
            }
        },
    )

    agent._load_mcp_tools.assert_not_called()
    # The pre-existing shared cache must survive untouched: a disallowed
    # URL must never trigger the "reload, replacing self._mcp_tools" path.
    assert agent._mcp_tools is existing_tools


@pytest.mark.asyncio
async def test_ainvoke_reloads_only_for_the_allowlisted_default_url_change():
    """A configurable.mcp_url that already equals the default is a no-op
    (nothing to reload); this is the common, legitimate case."""
    agent = ConfigurableMCPAgent()
    agent._loaded = True
    agent._graph = DummyGraph()
    agent._load_mcp_tools = AsyncMock()
    agent._save_memory_from_output = AsyncMock()
    agent._prepare_memory_context = AsyncMock(return_value=({"messages": []}, {}, "user-1", ""))

    await agent.ainvoke(
        {"messages": []},
        config={"configurable": {"user_id": "user-1", "mcp_url": default_mcp_url()}},
    )

    agent._load_mcp_tools.assert_not_called()
