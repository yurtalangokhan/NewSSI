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


def test_dynamic_agent_runtime_system_prompt_overrides_definition(monkeypatch):
    """Project/runtime instructions should replace the stored prompt for a run."""
    from agents.dynamic_agent import DynamicAgent

    calls = {}

    class FakeBuilder:
        def __init__(self, **kwargs):
            calls["builder_kwargs"] = kwargs

    monkeypatch.setattr("agents.dynamic_agent.GraphBuilder", FakeBuilder)
    monkeypatch.setattr("agents.dynamic_agent.get_model_from_config", lambda *_args: object())

    agent = DynamicAgent(
        {
            "name": "dynamic",
            "graph_schema": "zero_shot",
            "system_prompt": "Stored prompt.",
        }
    )

    _, _, build_config = agent._prepare_graph_build(
        runtime_config={"system_prompt": "Always answer in Turkish."}
    )

    assert calls["builder_kwargs"]["system_prompt"] == "Always answer in Turkish."
    assert build_config["system_prompt"] == "Always answer in Turkish."


def test_dynamic_agent_forwards_mail_tool_config_and_runtime_user(monkeypatch):
    """DynamicAgent should pass mail binding context into GraphBuilder."""
    from agents.dynamic_agent import DynamicAgent

    calls = {}

    class FakeBuilder:
        def __init__(self, **kwargs):
            calls["builder_kwargs"] = kwargs

    monkeypatch.setattr("agents.dynamic_agent.GraphBuilder", FakeBuilder)
    monkeypatch.setattr("agents.dynamic_agent.get_model_from_config", lambda *_args: object())

    agent = DynamicAgent(
        {
            "name": "mailer",
            "graph_schema": "zero_shot",
            "mcp_tools": ["send_email"],
            "mcp_tool_configs": {"send_email": {"mail_config_id": "mail-config-1"}},
        }
    )

    _, _, build_config = agent._prepare_graph_build(runtime_config={"user_id": "user-1"})

    assert build_config["mcp_tool_configs"] == {
        "send_email": {"mail_config_id": "mail-config-1"}
    }
    assert build_config["user_id"] == "user-1"
