"""Per-message timestamps come from the checkpoint that introduced the
message.

Nothing in a LangGraph thread stores a per-message send time: the messages
themselves carry none, and thread metadata only ever reflects the most recent
turn. The one durable record is the checkpoint's own write time, and a
checkpoint's delta is exactly the messages that turn produced — so stamping a
delta's messages with their checkpoint's `ts` dates each turn to within the
time it took to write it.
"""

from langchain_core.messages import AIMessage, HumanMessage

from service.chat.chat_history_reconstruction import reconstruct_message_tree, reconstruct_messages

T1 = "2026-08-12T13:06:00.100000+00:00"
T2 = "2026-08-12T13:06:04.900000+00:00"
T3 = "2026-08-13T09:15:00.000000+00:00"


def test_each_message_is_stamped_with_its_own_checkpoint_timestamp():
    human = HumanMessage(content="Atlas nedir")
    answer = AIMessage(content="Açık kaynaklı bir platform.")

    messages, _packets = reconstruct_message_tree(
        [
            {"checkpoint_id": "c1", "parent_checkpoint_id": None, "ts": T1, "messages": [human]},
            {
                "checkpoint_id": "c2",
                "parent_checkpoint_id": "c1",
                "ts": T2,
                "messages": [human, answer],
            },
        ],
        {},
        "thread-1",
    )

    by_type = {m["message_type"]: m for m in messages}
    assert by_type["user"]["time_sent"] == T1
    assert by_type["assistant"]["time_sent"] == T2


def test_messages_from_different_days_keep_their_own_days():
    """The day separators in the transcript depend on this: a conversation
    resumed the next morning must not report every turn as same-day."""
    human = HumanMessage(content="Atlas nedir")
    answer = AIMessage(content="Açık kaynaklı bir platform.")
    follow_up = HumanMessage(content="peki fiyatı")

    messages, _packets = reconstruct_message_tree(
        [
            {"checkpoint_id": "c1", "parent_checkpoint_id": None, "ts": T1, "messages": [human]},
            {
                "checkpoint_id": "c2",
                "parent_checkpoint_id": "c1",
                "ts": T2,
                "messages": [human, answer],
            },
            {
                "checkpoint_id": "c3",
                "parent_checkpoint_id": "c2",
                "ts": T3,
                "messages": [human, answer, follow_up],
            },
        ],
        {},
        "thread-1",
    )

    assert [m["time_sent"] for m in messages] == [T1, T2, T3]


def test_a_checkpoint_without_a_timestamp_leaves_its_messages_unstamped():
    """Degrades to today's behaviour rather than inventing a time — the UI
    renders no timestamp for such a message."""
    human = HumanMessage(content="Atlas nedir")

    messages, _packets = reconstruct_message_tree(
        [{"checkpoint_id": "c1", "parent_checkpoint_id": None, "messages": [human]}],
        {},
        "thread-1",
    )

    assert messages[0]["time_sent"] is None


def test_the_flat_fallback_path_leaves_messages_unstamped():
    """`reconstruct_messages` is handed one checkpoint's message list with no
    checkpoint around it, so it has no time to stamp with."""
    messages, _packets = reconstruct_messages(
        [HumanMessage(content="Atlas nedir"), AIMessage(content="Bir platform.")],
        thread_metadata={},
        chat_session_id="thread-1",
    )

    assert all(m["time_sent"] is None for m in messages)
