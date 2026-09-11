"""A FlowAgent chat run announces which published flow version it executed.

Without this, the chat-side flow strip always renders the *currently*
published flow, so publishing a new version mid-conversation retroactively
rewrites the list/canvas shown under older messages. The run emits one
``flow_version`` packet (and persists it to thread metadata, keyed by the
final AI message id, so a reload replays the same pin).
"""

import json

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from models.chat import StreamInput
from tests.test_message_generator_flow_stage_events import (
    _fake_handle_input,
    _FakeAssistantService,
    _FakeFlowAgent,
    _FakeIdController,
)


class _VersionedFlowAgent(_FakeFlowAgent):
    def __init__(self, version_no) -> None:
        super().__init__()
        self.flow_version_no = version_no

    async def aget_state(self, *args, **kwargs):
        class _State:
            values = {
                "messages": [
                    HumanMessage(content="merhaba", id="h1"),
                    AIMessage(content="Merhaba", id="ai-final-1"),
                ]
            }

        return _State()


async def _run(monkeypatch, agent, thread_id=None):
    import controller
    from service import AgentStreamService as AgentsRoute

    monkeypatch.setattr(
        AgentsRoute.AssistantAgentService,
        "get_instance",
        lambda: _FakeAssistantService(agent),
    )
    monkeypatch.setattr(AgentsRoute, "_handle_input", _fake_handle_input)
    monkeypatch.setattr(controller, "ChatController", _FakeIdController)

    kwargs = {"message": "merhaba"}
    if thread_id is not None:
        kwargs["thread_id"] = thread_id

    packets = []
    async for chunk in AgentsRoute.message_generator(
        StreamInput(**kwargs), agent_id="flow-def-1", user_id="user-1"
    ):
        body = chunk.removeprefix("data: ").strip()
        if body and body != "[DONE]" and not chunk.startswith(":"):
            packets.append(json.loads(body))
    return packets


@pytest.mark.asyncio
async def test_emits_one_flow_version_packet_with_the_executed_version(monkeypatch):
    packets = await _run(monkeypatch, _VersionedFlowAgent(7))

    versions = [p for p in packets if p["type"] == "flow_version"]
    assert len(versions) == 1
    assert versions[0]["version_no"] == 7


@pytest.mark.asyncio
async def test_no_flow_version_packet_when_the_version_is_unknown(monkeypatch):
    packets = await _run(monkeypatch, _VersionedFlowAgent(None))

    assert not any(p["type"] == "flow_version" for p in packets)


@pytest.mark.asyncio
async def test_persists_the_executed_version_to_thread_metadata(monkeypatch):
    import service.StoreService as StoreService

    writes: list[tuple] = []

    async def _fake_get_thread(_thread_id):
        return {"metadata": {"persona_id": 3}}

    async def _fake_update(thread_id, updates, update_timestamp=True):
        writes.append((thread_id, updates))
        return {}

    monkeypatch.setattr(StoreService, "get_thread_from_store", _fake_get_thread)
    monkeypatch.setattr(StoreService, "update_thread_in_store", _fake_update)

    await _run(monkeypatch, _VersionedFlowAgent(7), thread_id="thread-1")

    assert len(writes) == 1
    _thread_id, updates = writes[0]
    assert updates["metadata"]["flow_versions"] == {"ai-final-1": 7}
