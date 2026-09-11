"""_build_react must use langchain.agents.create_agent, not the deprecated
langgraph.prebuilt.create_react_agent (deprecated in LangGraph v1.0, to be
removed in v2.0), and must wire DeadEndTurnRetryMiddleware so a ReAct turn
can never silently end on a message with empty content and no tool_calls.
See tests/agents/graphs/test_dead_end_turn_retry_middleware.py for the
middleware's own behavior."""

from agents.graphs.builder import GraphBuilder
from agents.graphs.middleware import DeadEndTurnRetryMiddleware


def test_build_react_uses_create_agent_not_the_deprecated_prebuilt(monkeypatch):
    captured: dict = {}

    def fake_create_agent(**kwargs):
        captured.update(kwargs)
        return object()

    def fail_if_called(**kwargs):
        raise AssertionError(
            "_build_react must not use the deprecated langgraph.prebuilt.create_react_agent"
        )

    monkeypatch.setattr("agents.graphs.builder.create_agent", fake_create_agent)
    monkeypatch.setattr("agents.graphs.builder.create_react_agent", fail_if_called)

    builder = GraphBuilder(model=object())
    builder._build_react({"system_prompt": "Be helpful."})

    assert captured


def test_build_react_wires_the_dead_end_turn_retry_middleware(monkeypatch):
    captured: dict = {}

    def fake_create_agent(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr("agents.graphs.builder.create_agent", fake_create_agent)

    builder = GraphBuilder(model=object())
    builder._build_react({"system_prompt": "Be helpful."})

    assert any(isinstance(m, DeadEndTurnRetryMiddleware) for m in captured["middleware"])


def test_build_react_passes_system_prompt_as_a_plain_string(monkeypatch):
    """create_agent takes `system_prompt: str`, unlike create_react_agent's
    `prompt: SystemMessage`."""
    captured: dict = {}

    def fake_create_agent(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr("agents.graphs.builder.create_agent", fake_create_agent)

    builder = GraphBuilder(model=object())
    builder._build_react({"system_prompt": "Be helpful."})

    assert isinstance(captured["system_prompt"], str)
    assert "Be helpful." in captured["system_prompt"]
