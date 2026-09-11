from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from agents.configurable_mcp_agent import ConfigurableMCPAgent, _append_connector_prompt


def test_missing_assigned_connector_prevents_model_and_document_execution(monkeypatch):
    build = Mock()
    monkeypatch.setattr("agents.configurable_mcp_agent.get_model", lambda _: object())
    monkeypatch.setattr("agents.configurable_mcp_agent.create_react_agent", build)
    monkeypatch.setattr("agents.configurable_mcp_agent.get_document_tools", lambda: [])
    agent = ConfigurableMCPAgent()
    with pytest.raises(ValueError, match="connector_read"):
        agent._create_agent_graph(
            system_prompt="Read roles",
            mcp_tool_names=["get_current_time", "connector_read"],
            gateway_tools=[SimpleNamespace(name="get_current_time")],
        )
    build.assert_not_called()


def test_connector_prompt_requires_real_read_and_honest_errors():
    prompt = _append_connector_prompt(
        "Help", [{"datasource_id": "saved-source", "operations": ["read", "list_resources"]}]
    )
    assert "connector_read" in prompt
    assert "Never invent" in prompt
    assert "only when the user requests" in prompt
