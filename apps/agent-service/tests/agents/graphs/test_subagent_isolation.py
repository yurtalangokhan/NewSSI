"""AgentRef / Supervisor subgraphs return ONLY their final answer.

Added straight as a node, a subgraph merges its whole message list into the
parent flow (``add_messages``). For a Supervisor that meant its own system
prompt, its internal "transfer to / transfer back" handoff notices, and the
roster of sub-agents (with their prompts and tool status) all surfaced as
user-visible turns (B16); the real answer often arrived only as a trailing
fragment (B17). ``_isolate_subagent_node`` wraps the subgraph so its
transcript stays inside it.
"""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from agents.graphs.flow import _final_answer_message, _isolate_subagent_node


class _FakeChild:
    """Stands in for a compiled AgentRef / Supervisor subgraph."""

    def __init__(self, produced: list) -> None:
        self._produced = produced

    async def ainvoke(self, state, config=None):
        # a real subgraph returns the seed plus everything it produced
        return {"messages": list(state["messages"]) + self._produced, "scratch": {}}


# --- _final_answer_message ------------------------------------------------


def test_final_answer_message_skips_tool_calls_and_handoff_notices():
    msgs = [
        HumanMessage(content="Sen kurumsal yardim masasi supervizorusun ..."),  # leaked prompt
        AIMessage(content="", tool_calls=[{"name": "transfer_to_ik", "args": {}, "id": "1"}]),
        ToolMessage(content="Transferring back to supervisor", tool_call_id="1"),
        AIMessage(content="İzin bakiyeniz 12 gün."),
    ]
    assert _final_answer_message(msgs).content == "İzin bakiyeniz 12 gün."


def test_final_answer_message_is_none_when_there_is_no_ai_answer():
    msgs = [
        HumanMessage(content="hi"),
        AIMessage(content="", tool_calls=[{"name": "x", "args": {}, "id": "1"}]),
    ]
    assert _final_answer_message(msgs) is None


# --- _isolate_subagent_node --------------------------------------------


@pytest.mark.asyncio
async def test_only_the_final_answer_crosses_into_the_parent():
    child = _FakeChild(
        [
            HumanMessage(content="Available agents:\n- persona-2: BT ... (tools: no tools)"),
            AIMessage(
                content="", tool_calls=[{"name": "transfer_to_finance", "args": {}, "id": "1"}]
            ),
            ToolMessage(content="Successfully transferred", tool_call_id="1"),
            AIMessage(content="Masraf beyanınız onaylandı."),
        ]
    )
    node = _isolate_subagent_node(child, "sup-1")

    seed = [HumanMessage(content="masraf beyanımı kontrol et")]
    out = await node({"messages": seed, "scratch": {}}, None)

    # exactly one message crosses back, and it is the answer
    assert [m.content for m in out["messages"]] == ["Masraf beyanınız onaylandı."]
    # none of the internal transcript leaks
    joined = " ".join(m.content for m in out["messages"])
    assert "Available agents" not in joined
    assert "transfer" not in joined.lower()
    # the plain-text answer is also stored for {node-id} interpolation
    assert out["scratch"]["sup-1"] == "Masraf beyanınız onaylandı."


@pytest.mark.asyncio
async def test_falls_back_to_a_wrapped_ai_message_when_child_ends_oddly():
    # child ends on a ToolMessage (no closing AIMessage) — still give the
    # parent something rather than nothing.
    child = _FakeChild([ToolMessage(content="raw tool text", tool_call_id="1")])
    node = _isolate_subagent_node(child, "ref-1")

    out = await node({"messages": [HumanMessage(content="q")], "scratch": {}}, None)
    assert len(out["messages"]) == 1
    assert isinstance(out["messages"][0], AIMessage)
    assert out["messages"][0].content == "raw tool text"


@pytest.mark.asyncio
async def test_child_that_produces_nothing_yields_no_message():
    child = _FakeChild([])
    node = _isolate_subagent_node(child, "ref-1")
    out = await node({"messages": [HumanMessage(content="q")], "scratch": {}}, None)
    assert "messages" not in out or out["messages"] == []
    assert out["scratch"]["ref-1"] == ""  # nothing produced beyond the seed
