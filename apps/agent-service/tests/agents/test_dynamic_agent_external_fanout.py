"""A DynamicAgent only contacts the external MCP servers it actually uses.

`_load_mcp_tools` called `load_external_mcp_tools(None)` — no `wanted_names` —
so loading one agent opened a session against every CONNECTED external server
in the table, waited on each, and pulled their whole tool lists into memory.
The loader already supports narrowing; the caller just never passed anything.
"""

from __future__ import annotations

import pytest

from agents.implementations.dynamic_agent import DynamicAgent


def _agent(config: dict) -> DynamicAgent:
    agent = DynamicAgent.__new__(DynamicAgent)
    agent._config = config
    agent._mcp_tools_map = {}
    agent._gateway_tools = []
    agent._gateway = None
    return agent


@pytest.mark.asyncio
async def test_only_the_agents_own_tools_are_requested(monkeypatch):
    seen: dict = {}

    async def fake_loader(user_id, wanted_names=None):
        seen["user_id"] = user_id
        seen["wanted"] = wanted_names
        return {}

    monkeypatch.setattr("agents.tooling.mcp_external.load_external_mcp_tools", fake_loader)

    await _agent({"mcp_tools": ["deepwiki__ask", "jira__create_issue"]})._load_mcp_tools()

    assert seen["wanted"] == {"deepwiki__ask", "jira__create_issue"}


@pytest.mark.asyncio
async def test_an_agent_with_no_external_tools_opens_no_connections(monkeypatch):
    called = False

    async def fake_loader(user_id, wanted_names=None):
        nonlocal called
        called = True
        return {}

    monkeypatch.setattr("agents.tooling.mcp_external.load_external_mcp_tools", fake_loader)

    await _agent({"mcp_tools": []})._load_mcp_tools()

    assert called is False, "an agent that references no tools still dialled out"


@pytest.mark.asyncio
async def test_a_loader_failure_still_does_not_break_the_agent(monkeypatch):
    async def boom(user_id, wanted_names=None):
        raise ConnectionError("server unreachable")

    monkeypatch.setattr("agents.tooling.mcp_external.load_external_mcp_tools", boom)

    await _agent({"mcp_tools": ["deepwiki__ask"]})._load_mcp_tools()
