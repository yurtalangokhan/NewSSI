"""End-to-end: a live FlowAgent run's per-stage SSE stream and the timeline
rebuilt from the persisted blob agree on stage grouping and final answer."""

import json

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from models.chat import StreamInput
from service.flow_timeline_reconstruction import emit_flow_timeline_packets
from tests.test_message_generator_flow_stage_events import (
    _fake_handle_input,
    _FakeAssistantService,
    _FakeFlowAgent,
    _mchunk,
)


class _E2EFlowAgent(_FakeFlowAgent):
    """research -> (analysis x2) -> answer. Only `answer` feeds ChatOutput."""

    def __init__(self) -> None:
        super().__init__()
        self._final_stage_node_ids = {"answer"}

    async def aget_state(self, *args, **kwargs):
        class _State:
            values = {
                "messages": [
                    HumanMessage(content="q", id="h1"),
                    AIMessage(content="THE ANSWER", id="ai-final"),
                ]
            }

        return _State()

    async def astream(self, *args, **kwargs):
        yield ("debug", {"type": "task", "payload": {"id": "r", "name": "research"}})
        yield _mchunk("research notes", cid="r1", ns="r:a|model:x")
        yield ("debug", {"type": "task_result", "payload": {"id": "r", "name": "research"}})
        for i in range(2):
            yield ("debug", {"type": "task", "payload": {"id": f"a{i}", "name": "analysis"}})
            yield _mchunk(f"analysis {i}", cid=f"a{i}", ns=f"a{i}:b|model:y")
            yield (
                "debug",
                {"type": "task_result", "payload": {"id": f"a{i}", "name": "analysis"}},
            )
        yield ("debug", {"type": "task", "payload": {"id": "f", "name": "answer"}})
        yield _mchunk("THE ANSWER", cid="f1", ns="f:c|model:z")
        yield ("debug", {"type": "task_result", "payload": {"id": "f", "name": "answer"}})


@pytest.mark.asyncio
async def test_live_and_reload_agree_on_stage_grouping(monkeypatch):
    import controller
    import service.StoreService as StoreService
    from service import AgentStreamService as AgentsRoute

    agent = _E2EFlowAgent()
    captured: dict = {}

    async def _fake_get_thread(_tid):
        return {"metadata": {}}

    async def _fake_update(_tid, updates, update_timestamp=True):
        captured.update(updates.get("metadata", {}))
        return {}

    class _FakeIdController:
        def __init__(self, *_a, **_k):
            pass

        async def get_chat_session(self, _tid):
            return {"messages": []}

    monkeypatch.setattr(StoreService, "get_thread_from_store", _fake_get_thread)
    monkeypatch.setattr(StoreService, "update_thread_in_store", _fake_update)
    monkeypatch.setattr(controller, "ChatController", _FakeIdController)
    monkeypatch.setattr(
        AgentsRoute.AssistantAgentService,
        "get_instance",
        lambda: _FakeAssistantService(agent),
    )
    monkeypatch.setattr(AgentsRoute, "_handle_input", _fake_handle_input)

    live = []
    async for chunk in AgentsRoute.message_generator(
        StreamInput(message="q", thread_id="t1"),
        agent_id="flow-def-1",
        user_id="u1",
    ):
        body = chunk.removeprefix("data: ").strip()
        if body and body != "[DONE]" and not chunk.startswith(":"):
            live.append(json.loads(body))

    live_answer = "".join(p["content"] for p in live if p["type"] == "token")
    live_stage_keys = [p["stage_key"] for p in live if p["type"] == "flow_stage_start"]

    blob = captured["flow_timelines"]["ai-final"]
    reload_packets, reload_answer = emit_flow_timeline_packets(blob)
    reload_stage_keys = [
        p["obj"]["stage_key"] for p in reload_packets if p["obj"]["type"] == "flow_stage_start"
    ]

    # Reload replays a flow_stage_start for EVERY stage, matching live, so the
    # numbered sections look identical after a refresh.
    assert reload_stage_keys == live_stage_keys
    assert reload_stage_keys == ["research#1", "analysis#1", "analysis#2", "answer#1"]
    reload_final = next(
        p["obj"]
        for p in reload_packets
        if p["obj"]["type"] == "flow_stage_start"
        and p["obj"]["stage_key"] == blob["final_stage_key"]
    )
    assert reload_final["is_final_stage"] is True
    assert reload_answer == "THE ANSWER"
    assert live_answer.strip() == reload_answer.strip()
    assert "research notes" not in live_answer  # folded, not streamed
