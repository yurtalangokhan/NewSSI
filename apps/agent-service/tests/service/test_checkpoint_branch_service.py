"""CheckpointBranchService locates the LangGraph checkpoint to fork a retry
from — the point right after the target human message, before its original
response — so a retry can generate a response without seeing the rejected
answer in its context, while that rejected answer stays permanently
readable in its own branch. See
.tmp/2026-08-21-retry-checkpoint-branching-design.md.
"""

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from service.CheckpointBranchService import find_fork_point, find_fork_point_with_message


class _FakeSnapshot:
    def __init__(self, messages, checkpoint_id):
        self.values = {"messages": messages}
        self.config = {"configurable": {"thread_id": "t1", "checkpoint_id": checkpoint_id}}


class _FakeAgentWithHistory:
    def __init__(self, snapshots):
        self._snapshots = snapshots

    async def aget_state_history(self, config):
        for snapshot in self._snapshots:
            yield snapshot


@pytest.mark.asyncio
async def test_find_fork_point_locates_the_checkpoint_right_after_the_target_human_message():
    # aget_state_history yields newest-first.
    snapshots = [
        _FakeSnapshot(
            [HumanMessage(content="soru"), AIMessage(content="cevap")],
            checkpoint_id="2",
        ),
        _FakeSnapshot([HumanMessage(content="soru")], checkpoint_id="1"),
    ]
    agent = _FakeAgentWithHistory(snapshots)

    config = await find_fork_point(
        agent,
        thread_id="t1",
        target_message_id=1,
        thread_metadata={"user_id": "user-1", "persona_id": 0},
    )

    assert config == {"configurable": {"thread_id": "t1", "checkpoint_id": "1"}}


@pytest.mark.asyncio
async def test_find_fork_point_with_message_also_returns_the_raw_target_message():
    """An edit-message retry needs the raw langchain message (its real .id)
    so aupdate_state can replace it in place instead of appending a
    duplicate — this is what distinguishes editing from a plain retry."""
    target = HumanMessage(content="soru", id="h1")
    snapshots = [
        _FakeSnapshot(
            [HumanMessage(content="soru", id="h1"), AIMessage(content="cevap")],
            checkpoint_id="2",
        ),
        _FakeSnapshot([target], checkpoint_id="1"),
    ]
    agent = _FakeAgentWithHistory(snapshots)

    config, raw_message = await find_fork_point_with_message(
        agent,
        thread_id="t1",
        target_message_id=1,
        thread_metadata={"user_id": "user-1", "persona_id": 0},
    )

    assert config == {"configurable": {"thread_id": "t1", "checkpoint_id": "1"}}
    assert raw_message is target
    assert raw_message.id == "h1"


@pytest.mark.asyncio
async def test_find_fork_point_with_message_returns_none_none_when_no_match():
    agent = _FakeAgentWithHistory(
        [_FakeSnapshot([HumanMessage(content="soru")], checkpoint_id="1")]
    )

    config, raw_message = await find_fork_point_with_message(
        agent,
        thread_id="t1",
        target_message_id=99,
        thread_metadata={"user_id": "user-1", "persona_id": 0},
    )

    assert config is None
    assert raw_message is None


@pytest.mark.asyncio
async def test_find_fork_point_returns_none_when_no_matching_checkpoint_exists():
    agent = _FakeAgentWithHistory(
        [_FakeSnapshot([HumanMessage(content="soru")], checkpoint_id="1")]
    )

    config = await find_fork_point(
        agent,
        thread_id="t1",
        target_message_id=99,
        thread_metadata={"user_id": "user-1", "persona_id": 0},
    )

    assert config is None


@pytest.mark.asyncio
async def test_find_fork_point_ignores_a_checkpoint_ending_on_an_assistant_message():
    """A checkpoint whose last message is already the assistant response
    (not the human message) must never match — that's the wrong point to
    fork from (it would replay generation instead of skipping past it)."""
    snapshots = [
        _FakeSnapshot(
            [HumanMessage(content="soru"), AIMessage(content="cevap")],
            checkpoint_id="2",
        ),
    ]
    agent = _FakeAgentWithHistory(snapshots)

    config = await find_fork_point(
        agent,
        thread_id="t1",
        target_message_id=2,
        thread_metadata={"user_id": "user-1", "persona_id": 0},
    )

    assert config is None


@pytest.mark.asyncio
async def test_find_fork_point_locates_an_earlier_turn_in_a_multi_turn_thread():
    snapshots = [
        _FakeSnapshot(
            [
                HumanMessage(content="ilk soru"),
                AIMessage(content="ilk cevap"),
                HumanMessage(content="ikinci soru"),
                AIMessage(content="ikinci cevap"),
            ],
            checkpoint_id="4",
        ),
        _FakeSnapshot(
            [
                HumanMessage(content="ilk soru"),
                AIMessage(content="ilk cevap"),
                HumanMessage(content="ikinci soru"),
            ],
            checkpoint_id="3",
        ),
        _FakeSnapshot(
            [HumanMessage(content="ilk soru"), AIMessage(content="ilk cevap")],
            checkpoint_id="2",
        ),
        _FakeSnapshot([HumanMessage(content="ilk soru")], checkpoint_id="1"),
    ]
    agent = _FakeAgentWithHistory(snapshots)

    # Retry the FIRST turn, not the latest one.
    config = await find_fork_point(
        agent,
        thread_id="t1",
        target_message_id=1,
        thread_metadata={"user_id": "user-1", "persona_id": 0},
    )

    assert config == {"configurable": {"thread_id": "t1", "checkpoint_id": "1"}}
