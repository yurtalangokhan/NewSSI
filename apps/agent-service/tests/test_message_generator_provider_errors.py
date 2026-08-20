import json
from uuid import uuid4

import httpx
import pytest
from langgraph.errors import GraphRecursionError

from models.chat import StreamInput


class _ProviderFailureAgent:
    async def aget_state(self, *args, **kwargs):
        class _State:
            tasks = []
            values = {}

        return _State()

    async def astream(self, *args, **kwargs):
        if False:
            yield None
        raise httpx.ConnectError("All connection attempts failed")


class _RecursionLimitAgent:
    async def aget_state(self, *args, **kwargs):
        class _State:
            tasks = []
            values = {}

        return _State()

    async def astream(self, *args, **kwargs):
        if False:
            yield None
        raise GraphRecursionError(
            "Recursion limit of 25 reached without hitting a stop condition."
        )


class _FakeAssistantService:
    def __init__(self, agent=None):
        self._agent = agent or _ProviderFailureAgent()

    async def get_graph_and_config(self, _agent_id):
        return "chatbot", {}

    async def get_configured_agent(self, _agent_id, _agent_config):
        return self._agent


@pytest.mark.asyncio
async def test_message_generator_reports_provider_connection_failure(monkeypatch):
    from api.routes import AgentsRoute

    async def fake_handle_input(_user_input, _agent, _user_id=None):
        return {"input": {"messages": []}, "config": {}}, uuid4()

    monkeypatch.setattr(
        AgentsRoute.AssistantAgentService,
        "get_instance",
        lambda: _FakeAssistantService(),
    )
    monkeypatch.setattr(AgentsRoute, "_handle_input", fake_handle_input)

    chunks = [
        chunk
        async for chunk in AgentsRoute.message_generator(
            StreamInput(message="hello"),
            agent_id="chatbot",
            user_id="user-1",
        )
    ]

    error_chunk = next(chunk for chunk in chunks if '"type": "error"' in chunk)
    payload = json.loads(error_chunk.removeprefix("data: ").strip())

    assert payload["error_code"] == "provider_unavailable"
    assert payload["is_retryable"] is True
    assert "LLM provider" in payload["error"]


@pytest.mark.asyncio
async def test_message_generator_reports_recursion_limit_exceeded(monkeypatch):
    """A deep-research turn doing many sequential search/fetch rounds can hit
    LangGraph's step budget — the client must get a clear error frame, not a
    silently dropped connection."""
    from api.routes import AgentsRoute

    async def fake_handle_input(_user_input, _agent, _user_id=None):
        return {"input": {"messages": []}, "config": {}}, uuid4()

    monkeypatch.setattr(
        AgentsRoute.AssistantAgentService,
        "get_instance",
        lambda: _FakeAssistantService(_RecursionLimitAgent()),
    )
    monkeypatch.setattr(AgentsRoute, "_handle_input", fake_handle_input)

    chunks = [
        chunk
        async for chunk in AgentsRoute.message_generator(
            StreamInput(message="hello"),
            agent_id="chatbot",
            user_id="user-1",
        )
    ]

    error_chunk = next(chunk for chunk in chunks if '"type": "error"' in chunk)
    payload = json.loads(error_chunk.removeprefix("data: ").strip())

    assert payload["error_code"] == "recursion_limit_exceeded"
    assert payload["is_retryable"] is True
