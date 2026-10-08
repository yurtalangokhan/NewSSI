"""``memory.recall``: the one implementation of long-term recall around a run.

It used to be two — ``LazyLoadingAgent`` and ``ComposedAgent`` each carried a
copy, written when the second was meant to replace the first. These cover the
behaviour both relied on, and that a recall failure costs the user nothing.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import HumanMessage

from memory.recall import (
    build_memory_recall_event,
    inject_memory_into_input,
    mark_input_with_ltm_recalled,
    tag_output_with_recalled_memories,
)

RECALL_CONFIG = {"configurable": {"long_term_memory": True, "user_id": "user-1"}}


class TestBuildMemoryRecallEvent:
    def test_no_facts_produces_no_event(self):
        assert build_memory_recall_event({}) is None
        assert build_memory_recall_event({"user_facts": []}) is None

    def test_facts_produce_a_custom_event(self):
        event = build_memory_recall_event({"user_facts": ["likes tea", "lives in Ankara"]})
        assert event == {
            "type": "long_term_memory_recall",
            "fact_count": 2,
            "memories": ["likes tea", "lives in Ankara"],
        }


class TestMarkInputWithLtmRecalled:
    def test_zero_recalled_leaves_the_input_alone(self):
        payload = {"messages": [HumanMessage(content="merhaba")]}
        assert mark_input_with_ltm_recalled(payload, 0) is payload

    def test_the_count_lands_on_the_latest_human_message(self):
        payload = {"messages": [HumanMessage(content="ilk"), HumanMessage(content="son")]}
        updated = mark_input_with_ltm_recalled(payload, 3)
        assert updated["messages"][-1].additional_kwargs["_ltm_recalled"] == 3

    def test_dict_shaped_messages_are_marked_too(self):
        payload = {"messages": [{"type": "human", "content": "merhaba"}]}
        updated = mark_input_with_ltm_recalled(payload, 2)
        assert updated["messages"][-1]["additional_kwargs"]["_ltm_recalled"] == 2

    def test_an_input_without_messages_is_returned_unchanged(self):
        payload = {"something_else": 1}
        assert mark_input_with_ltm_recalled(payload, 5) is payload


class TestTagOutputWithRecalledMemories:
    def test_no_facts_leaves_the_output_alone(self):
        output = {"messages": [HumanMessage(content="x")]}
        assert tag_output_with_recalled_memories(output, {}) is output

    def test_a_values_chunk_is_tagged(self):
        memories = {"user_facts": ["likes tea"]}
        chunk = ("values", {"messages": [HumanMessage(content="cevap")]})
        with patch("memory.long_term.tag_response_with_ltm_recall") as tag:
            tag_output_with_recalled_memories(chunk, memories)
        tag.assert_called_once()


@pytest.mark.asyncio
class TestInjectMemoryIntoInput:
    async def test_memory_disabled_skips_recall_entirely(self):
        payload = {"messages": []}
        result, memories, user_id = await inject_memory_into_input(
            payload, {"configurable": {"user_id": "user-1"}}
        )
        assert result is payload
        assert memories == {}
        assert user_id == "user-1"

    async def test_no_store_skips_recall(self):
        payload = {"messages": []}
        result, memories, _ = await inject_memory_into_input(payload, RECALL_CONFIG)
        assert result is payload
        assert memories == {}

    async def test_recalled_context_is_prepended_as_a_system_message(self):
        payload = {"messages": [HumanMessage(content="merhaba")]}
        with (
            patch(
                "memory.long_term.recall_memories",
                new=AsyncMock(return_value={"user_facts": ["likes tea"]}),
            ),
            patch("memory.long_term.build_memory_context", return_value="Bilinen: likes tea"),
        ):
            result, memories, _ = await inject_memory_into_input(
                payload, RECALL_CONFIG
            )

        assert memories == {"user_facts": ["likes tea"]}
        assert result["messages"][0].content == "Bilinen: likes tea"
        assert result["messages"][-1].content == "merhaba"

    async def test_a_recall_failure_does_not_cost_the_user_their_turn(self):
        """Recall is an enhancement — a store outage must leave the run intact."""
        payload = {"messages": [HumanMessage(content="merhaba")]}
        with patch(
            "memory.long_term.recall_memories",
            new=AsyncMock(side_effect=RuntimeError("store down")),
        ):
            result, memories, user_id = await inject_memory_into_input(
                payload, RECALL_CONFIG
            )

        assert result == payload
        assert memories == {}
        assert user_id == "user-1"
