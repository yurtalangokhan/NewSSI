"""message_generator hands the run the server-resolved config: the stored
persona/definition config, overlaid by whatever the route already resolved."""

from __future__ import annotations

from uuid import uuid4

import pytest

from schemas.chat import StreamInput
from service.orchestration import agent_stream_service


class _Agent:
    async def aget_state(self, *args, **kwargs):
        class _State:
            tasks = []
            values = {}

        return _State()

    async def astream(self, *args, **kwargs):
        if False:
            yield None


class _Service:
    async def get_graph_and_config(self, _agent_id):
        return "chatbot", {"rag_config": {"document_processing": ["stored"]}, "memory_type": "long_term"}

    async def get_configured_agent(self, _agent_id, _agent_config):
        return _Agent()


@pytest.mark.asyncio
async def test_stored_config_is_overlaid_by_route_resolved_config(monkeypatch) -> None:
    seen: list[dict] = []

    async def fake_handle_input(user_input, _agent, _user_id=None):
        seen.append(dict(user_input.server_config))
        return {"input": {"messages": []}, "config": {}}, uuid4()

    monkeypatch.setattr(agent_stream_service.AssistantAgentService, "get_instance", lambda: _Service())
    monkeypatch.setattr(agent_stream_service, "_handle_input", fake_handle_input)
    user_input = StreamInput(message="hi", thread_id="t-1")
    user_input.attach_server_config({"rag_config": {"document_processing": ["route"]}})

    async for _ in agent_stream_service.message_generator(user_input, agent_id="chatbot", user_id="u-1"):
        pass

    assert seen == [{"rag_config": {"document_processing": ["route"]}, "memory_type": "long_term"}]
