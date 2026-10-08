import json

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage

from agents.graphs.flow import _resolve_final_stage_nodes
from agents.implementations.flow_agent import FlowAgent
from schemas.chat import StreamInput
from schemas.flows import FlowSpec


def _mchunk(content: str = "", reasoning: str = "", cid: str = "c1", ns: str = "") -> tuple:
    additional = {}
    if reasoning:
        additional["reasoning_content"] = reasoning
    chunk = AIMessageChunk(id=cid, content=content, additional_kwargs=additional)
    meta = {"tags": []}
    if ns:
        meta["langgraph_checkpoint_ns"] = ns
    return ("messages", (chunk, meta))


def test_final_stage_node_ids_excludes_message_suppressed_runflow_nodes():
    """When parallel RunFlow nodes feed a Merge node, their output is suppressed from
    becoming top-level messages (Merge aggregates their state instead).
    _resolve_final_stage_nodes must NOT treat the parallel RunFlow nodes as final stages
    simply because Merge is a passthrough node.
    """
    flow_spec = FlowSpec.model_validate(
        {
            "nodes": [
                {"id": "n_in", "type": "ChatInput", "values": {}},
                {"id": "n_var", "type": "Variables", "values": {}},
                {
                    "id": "n_ekipman",
                    "type": "RunFlow",
                    "values": {"flow_definition_id": "flow-sub-1"},
                },
                {
                    "id": "n_hesap",
                    "type": "RunFlow",
                    "values": {"flow_definition_id": "flow-sub-2"},
                },
                {
                    "id": "n_merge",
                    "type": "Merge",
                    "values": {"merge_strategy": "last"},
                },
                {"id": "n_birlestir", "type": "ReActAgent", "values": {}},
                {"id": "n_out", "type": "ChatOutput", "values": {}},
            ],
            "edges": [
                {
                    "id": "e1",
                    "source": "n_in",
                    "target": "n_var",
                    "sourceHandle": "",
                    "targetHandle": "",
                },
                {
                    "id": "e2",
                    "source": "n_var",
                    "target": "n_ekipman",
                    "sourceHandle": "",
                    "targetHandle": "",
                },
                {
                    "id": "e3",
                    "source": "n_var",
                    "target": "n_hesap",
                    "sourceHandle": "",
                    "targetHandle": "",
                },
                {
                    "id": "e4",
                    "source": "n_ekipman",
                    "target": "n_merge",
                    "sourceHandle": "",
                    "targetHandle": "",
                },
                {
                    "id": "e5",
                    "source": "n_hesap",
                    "target": "n_merge",
                    "sourceHandle": "",
                    "targetHandle": "",
                },
                {
                    "id": "e6",
                    "source": "n_merge",
                    "target": "n_birlestir",
                    "sourceHandle": "",
                    "targetHandle": "",
                },
                {
                    "id": "e7",
                    "source": "n_birlestir",
                    "target": "n_out",
                    "sourceHandle": "",
                    "targetHandle": "",
                },
            ],
        }
    )

    # In flow_builder.py, RunFlow nodes that feed Merge are added to message_suppressed_ids
    message_suppressed_ids = {"n_ekipman", "n_hesap"}
    final_ids = _resolve_final_stage_nodes(
        flow_spec, set(), message_suppressed_ids=message_suppressed_ids
    )

    # Crucially, neither parallel RunFlow node must be considered a final stage!
    assert "n_ekipman" not in final_ids
    assert "n_hesap" not in final_ids
    assert final_ids == {"n_birlestir"}


class _ParallelRunFlowAgent(FlowAgent):
    """Simulates parallel execution of n_ekipman and n_hesap followed by n_merge and n_birlestir."""

    def __init__(self) -> None:
        super().__init__(flow_spec=None, definition_id="parallel-flow-def")
        self._flow_spec_raw = {
            "nodes": [
                {"id": "n_in", "type": "ChatInput"},
                {"id": "n_var", "type": "Variables"},
                {"id": "n_ekipman", "type": "RunFlow"},
                {"id": "n_hesap", "type": "RunFlow"},
                {"id": "n_merge", "type": "Merge"},
                {"id": "n_birlestir", "type": "ReActAgent"},
                {"id": "n_out", "type": "ChatOutput"},
            ],
            "edges": [],
        }
        # Only n_birlestir is final! Parallel RunFlow branches are NOT final.
        self._final_stage_node_ids = {"n_birlestir"}

    async def aget_state(self, *args, **kwargs):
        class _State:
            values = {
                "messages": [
                    HumanMessage(content="Start", id="h1"),
                    AIMessage(content="MERGED FINAL ANSWER", id="ai-final"),
                ]
            }

        return _State()

    async def astream(self, *args, **kwargs):
        # 1. Start n_ekipman
        yield ("debug", {"type": "task", "payload": {"id": "t_ekip", "name": "n_ekipman"}})
        # 2. Start n_hesap 1ms later concurrently
        yield ("debug", {"type": "task", "payload": {"id": "t_hesap", "name": "n_hesap"}})

        # 3. Both stream thinking concurrently with their respective checkpoint namespaces
        yield _mchunk(
            reasoning="Ekipman düşünüyor...", cid="c_ekip_1", ns="n_ekipman:task1|chatbot:sub1"
        )
        yield _mchunk(
            reasoning="Hesap düşünüyor...", cid="c_hesap_1", ns="n_hesap:task2|chatbot:sub2"
        )
        yield _mchunk(
            reasoning="Ekipman detaylandırıyor.", cid="c_ekip_2", ns="n_ekipman:task1|chatbot:sub1"
        )
        yield _mchunk(
            reasoning="Hesap hesaplıyor.", cid="c_hesap_2", ns="n_hesap:task2|chatbot:sub2"
        )

        # 4. n_hesap finishes first at t=49s and emits output
        yield _mchunk("HESAP SONUCU", cid="c_hesap_out", ns="n_hesap:task2|chatbot:sub2")
        yield ("debug", {"type": "task_result", "payload": {"id": "t_hesap", "name": "n_hesap"}})

        # 5. n_ekipman is still thinking / running, finishes at t=91s and emits output
        yield _mchunk("EKIPMAN SONUCU", cid="c_ekip_out", ns="n_ekipman:task1|chatbot:sub1")
        yield ("debug", {"type": "task_result", "payload": {"id": "t_ekip", "name": "n_ekipman"}})

        # 6. Final stage n_birlestir runs
        yield ("debug", {"type": "task", "payload": {"id": "t_bir", "name": "n_birlestir"}})
        yield _mchunk("MERGED FINAL ANSWER", cid="c_final", ns="n_birlestir:task3")
        yield ("debug", {"type": "task_result", "payload": {"id": "t_bir", "name": "n_birlestir"}})


class _FakeAssistantService:
    def __init__(self, agent) -> None:
        self._agent = agent

    async def get_graph_and_config(self, _agent_id):
        return "parallel-flow-def", {}

    async def get_configured_agent(self, _agent_id, _agent_config):
        return self._agent


async def _fake_handle_input(_user_input, _agent, _user_id=None):
    return {"input": {"messages": []}, "config": {}}, "run-parallel"


@pytest.mark.asyncio
async def test_parallel_stages_keep_independent_thinking_and_no_premature_streaming(monkeypatch):
    """Verify that:

    1. n_ekipman and n_hesap both get independent reasoning blocks tagged with their stage key.
    2. n_hesap finishing first does NOT prematurely stream tokens to the chat bubble.
    3. Both branches fold their output into flow_stage_output_delta.
    4. Only n_birlestir streams tokens to the chat bubble.
    5. The persisted flow_timelines blob has steps and output for BOTH branches.
    """
    import service.runtime.store_service as StoreService
    from service.orchestration import agent_stream_service as agents_route

    agent = _ParallelRunFlowAgent()
    monkeypatch.setattr(
        agents_route.AssistantAgentService, "get_instance", lambda: _FakeAssistantService(agent)
    )
    monkeypatch.setattr(agents_route, "_handle_input", _fake_handle_input)

    writes: list[tuple] = []

    async def _fake_get_thread(_thread_id):
        return {"metadata": {}}

    async def _fake_update(thread_id, updates, update_timestamp=True):
        writes.append((thread_id, updates, update_timestamp))
        return {}

    monkeypatch.setattr(StoreService, "get_thread_from_store", _fake_get_thread)
    monkeypatch.setattr(StoreService, "update_thread_in_store", _fake_update)

    packets = []
    async for chunk in agents_route.message_generator(
        StreamInput(message="q", thread_id="t1"),
        agent_id="parallel-flow-def",
        user_id="u1",
    ):
        body = chunk.removeprefix("data: ").strip()
        if body and body != "[DONE]" and not chunk.startswith(":"):
            packets.append(json.loads(body))

    # 1. Reasoning verification: both stages must have reasoning deltas with their stage keys
    ekip_reasoning = "".join(
        p.get("reasoning", "")
        for p in packets
        if p.get("type") == "reasoning_delta" and p.get("stage_key") == "n_ekipman#1"
    )
    hesap_reasoning = "".join(
        p.get("reasoning", "")
        for p in packets
        if p.get("type") == "reasoning_delta" and p.get("stage_key") == "n_hesap#1"
    )
    assert "Ekipman düşünüyor" in ekip_reasoning
    assert "Ekipman detaylandırıyor" in ekip_reasoning
    assert "Hesap düşünüyor" in hesap_reasoning
    assert "Hesap hesaplıyor" in hesap_reasoning

    # 2. No premature answer streaming!
    # Tokens (answer bubble) must ONLY contain the final answer, NOT n_hesap or n_ekipman
    tokens = "".join(p.get("content", "") for p in packets if p.get("type") == "token")
    assert "HESAP SONUCU" not in tokens
    assert "EKIPMAN SONUCU" not in tokens
    assert "MERGED FINAL ANSWER" in tokens

    # 3. Intermediate outputs must be folded into flow_stage_output_delta
    ekip_folded = "".join(
        p.get("content", "")
        for p in packets
        if p.get("type") == "flow_stage_output_delta" and p.get("stage_key") == "n_ekipman#1"
    )
    hesap_folded = "".join(
        p.get("content", "")
        for p in packets
        if p.get("type") == "flow_stage_output_delta" and p.get("stage_key") == "n_hesap#1"
    )
    assert "EKIPMAN SONUCU" in ekip_folded
    assert "HESAP SONUCU" in hesap_folded

    # 4. Check persisted blob in thread metadata
    timeline_writes = [w for w in writes if "flow_timelines" in w[1].get("metadata", {})]
    assert len(timeline_writes) == 1
    _, updates, _ = timeline_writes[0]
    blob = updates["metadata"]["flow_timelines"]["ai-final"]
    stages_by_key = {s["stage_key"]: s for s in blob["stages"]}

    assert "n_ekipman#1" in stages_by_key
    assert "n_hesap#1" in stages_by_key
    assert "n_birlestir#1" in stages_by_key

    ekip_stage = stages_by_key["n_ekipman#1"]
    hesap_stage = stages_by_key["n_hesap#1"]

    assert len(ekip_stage["steps"]) > 0, "n_ekipman steps must not be empty!"
    assert len(hesap_stage["steps"]) > 0, "n_hesap steps must not be empty!"
    assert "Ekipman" in ekip_stage["reasoning_text"]
    assert "Hesap" in hesap_stage["reasoning_text"]
    assert "EKIPMAN SONUCU" in ekip_stage["output_text"]
    assert "HESAP SONUCU" in hesap_stage["output_text"]
