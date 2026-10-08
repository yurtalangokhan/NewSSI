"""The react graph must use langchain.agents.create_agent.

Not the deprecated langgraph.prebuilt.create_react_agent (deprecated in
LangGraph v1.0, to be removed in v2.0) -- and, more than deprecation, that
factory has no middleware slot, so DeadEndTurnRetryMiddleware cannot be
wired onto it and a ReAct turn can silently end on a message with empty
content and no tool_calls. See
tests/agents/graphs/test_dead_end_turn_retry_middleware.py for the
middleware's own behaviour.

These drive GraphBuilder.build_async, the entry point production uses.
They used to call GraphBuilder._build_react directly -- a method the
registry never dispatched to, while the strategy that actually ran was
still on create_react_agent with no middleware at all.
"""

import pytest

from agents.graphs.builder import GraphBuilder
from agents.graphs.middleware import DeadEndTurnRetryMiddleware


def _capture_create_agent(monkeypatch) -> dict:
    captured: dict = {}

    def fake_create_agent(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr("agents.graphs.strategies.react.create_agent", fake_create_agent)
    return captured


@pytest.mark.asyncio
async def test_the_react_graph_uses_create_agent_not_the_deprecated_prebuilt(monkeypatch):
    captured = _capture_create_agent(monkeypatch)

    def fail_if_called(**_kwargs):
        raise AssertionError(
            "the react strategy must not use the deprecated langgraph.prebuilt.create_react_agent"
        )

    monkeypatch.setattr("langgraph.prebuilt.create_react_agent", fail_if_called)

    await GraphBuilder(model=object()).build_async("react", {"system_prompt": "Be helpful."})

    assert captured


@pytest.mark.asyncio
async def test_the_react_graph_wires_the_dead_end_turn_retry_middleware(monkeypatch):
    captured = _capture_create_agent(monkeypatch)

    await GraphBuilder(model=object()).build_async("react", {"system_prompt": "Be helpful."})

    assert any(isinstance(m, DeadEndTurnRetryMiddleware) for m in captured["middleware"])


@pytest.mark.asyncio
async def test_the_react_graph_passes_system_prompt_as_a_plain_string(monkeypatch):
    """create_agent takes `system_prompt: str`, unlike create_react_agent's
    `prompt: SystemMessage`."""
    captured = _capture_create_agent(monkeypatch)

    await GraphBuilder(model=object()).build_async("react", {"system_prompt": "Be helpful."})

    assert isinstance(captured["system_prompt"], str)
    assert "Be helpful." in captured["system_prompt"]
