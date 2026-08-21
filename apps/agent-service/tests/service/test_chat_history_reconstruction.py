"""Direct unit tests for the extracted reconstruction module.

Mirrors the scenarios already covered end-to-end through
ChatController.get_chat_session (tests/controller/test_chat_controller_history.py)
but calls reconstruct_messages directly — this is the function
CheckpointBranchService also depends on for locating fork points.
"""

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from service.ChatHistoryReconstruction import reconstruct_message_tree, reconstruct_messages


def test_reconstruct_messages_builds_a_plain_chain():
    messages, packets_2d = reconstruct_messages(
        [HumanMessage(content="merhaba"), AIMessage(content="selam")],
        thread_metadata={"user_id": "user-1", "persona_id": 1},
        chat_session_id="thread-1",
    )

    assert [m["message_type"] for m in messages] == ["user", "assistant"]
    assert [m["message"] for m in messages] == ["merhaba", "selam"]
    assert messages[0]["parent_message"] is None
    assert messages[1]["parent_message"] == messages[0]["message_id"]
    assert messages[0]["latest_child_message"] == messages[1]["message_id"]
    assert len(packets_2d) == 1


def test_reconstruct_messages_treats_regenerated_response_as_a_sibling():
    messages, _ = reconstruct_messages(
        [
            HumanMessage(
                content="soru",
                additional_kwargs={"persona_id": 0, "model": "gpt-4o-mini"},
            ),
            AIMessage(content="cevap 1"),
            HumanMessage(
                content="soru",
                additional_kwargs={
                    "persona_id": 0,
                    "model": "gpt-4o",
                    "is_regenerate": True,
                },
            ),
            AIMessage(content="cevap 2"),
        ],
        thread_metadata={"user_id": "user-1", "persona_id": 0},
        chat_session_id="thread-regen",
    )

    assert [m["message_type"] for m in messages] == ["user", "assistant", "assistant"]
    user_msg, ai1, ai2 = messages
    assert ai1["parent_message"] == user_msg["message_id"]
    assert ai2["parent_message"] == user_msg["message_id"]
    assert user_msg["latest_child_message"] == ai2["message_id"]


def test_reconstruct_messages_returns_partial_results_on_internal_failure():
    class _BoomMessage:
        type = "ai"
        content = ""
        additional_kwargs: dict = {}

        @property
        def tool_calls(self):
            raise RuntimeError("boom")

    messages, _ = reconstruct_messages(
        [HumanMessage(content="merhaba"), AIMessage(content="selam"), _BoomMessage()],
        thread_metadata={"user_id": "user-1", "persona_id": 1},
        chat_session_id="thread-boom",
    )

    assert [m["message_type"] for m in messages] == ["user", "assistant"]


def test_reconstruct_message_tree_returns_empty_for_no_checkpoints():
    messages, packets_2d = reconstruct_message_tree(
        [], thread_metadata={"persona_id": 0}, chat_session_id="thread-empty"
    )

    assert messages == []
    assert packets_2d == []


def test_reconstruct_message_tree_matches_reconstruct_messages_for_a_single_checkpoint():
    """No branching at all — a single checkpoint's tree walk must produce
    exactly what the flat reconstruction produces, since real threads
    that never retried have exactly one checkpoint chain."""
    raw_messages = [HumanMessage(content="merhaba"), AIMessage(content="selam")]

    flat_messages, flat_packets = reconstruct_messages(
        raw_messages, thread_metadata={"persona_id": 1}, chat_session_id="thread-1"
    )
    tree_messages, tree_packets = reconstruct_message_tree(
        [{"checkpoint_id": "1", "parent_checkpoint_id": None, "messages": raw_messages}],
        thread_metadata={"persona_id": 1},
        chat_session_id="thread-1",
    )

    assert tree_messages == flat_messages
    assert tree_packets == flat_packets


def test_reconstruct_message_tree_gives_true_branches_distinct_non_colliding_ids():
    """This is the whole point of the tree walk: two checkpoints that fork
    from the SAME parent (a real retry branch, not the old flat
    is_regenerate marker) must produce two DISTINCT assistant messages
    sharing one parent — not a positional-counter collision where both
    independently land on the same message_id."""
    human = HumanMessage(content="soru")
    checkpoints = [
        {
            "checkpoint_id": "root",
            "parent_checkpoint_id": None,
            "messages": [human],
        },
        {
            "checkpoint_id": "branch-a",
            "parent_checkpoint_id": "root",
            "messages": [human, AIMessage(content="cevap 1")],
        },
        {
            "checkpoint_id": "branch-b",
            "parent_checkpoint_id": "root",
            "messages": [human, AIMessage(content="cevap 2")],
        },
    ]

    messages, _ = reconstruct_message_tree(
        checkpoints, thread_metadata={"persona_id": 0}, chat_session_id="thread-fork"
    )

    assert [m["message_type"] for m in messages] == ["user", "assistant", "assistant"]
    user_msg, ai1, ai2 = messages
    assert {m["message"] for m in (ai1, ai2)} == {"cevap 1", "cevap 2"}
    # No collision: two distinct ids sharing one parent.
    assert ai1["message_id"] != ai2["message_id"]
    assert ai1["parent_message"] == user_msg["message_id"]
    assert ai2["parent_message"] == user_msg["message_id"]
    # The most recently walked branch (breadth-first from the root's
    # children list) is reported as the active/latest one.
    assert user_msg["latest_child_message"] == ai2["message_id"]


def test_reconstruct_message_tree_supports_three_way_branching():
    human = HumanMessage(content="soru")
    checkpoints = [
        {"checkpoint_id": "root", "parent_checkpoint_id": None, "messages": [human]},
        {
            "checkpoint_id": "a",
            "parent_checkpoint_id": "root",
            "messages": [human, AIMessage(content="cevap 1")],
        },
        {
            "checkpoint_id": "b",
            "parent_checkpoint_id": "root",
            "messages": [human, AIMessage(content="cevap 2")],
        },
        {
            "checkpoint_id": "c",
            "parent_checkpoint_id": "root",
            "messages": [human, AIMessage(content="cevap 3")],
        },
    ]

    messages, _ = reconstruct_message_tree(
        checkpoints, thread_metadata={"persona_id": 0}, chat_session_id="thread-fork-3"
    )

    assert [m["message_type"] for m in messages] == [
        "user",
        "assistant",
        "assistant",
        "assistant",
    ]
    ids = [m["message_id"] for m in messages]
    assert len(set(ids)) == 4, "all four messages must have distinct ids"
    user_msg, ai1, ai2, ai3 = messages
    assert ai1["parent_message"] == ai2["parent_message"] == ai3["parent_message"]
    assert ai1["parent_message"] == user_msg["message_id"]


def test_reconstruct_message_tree_reconstructs_a_branch_deeper_in_a_multi_turn_thread():
    """A retry doesn't have to target the LATEST turn — branching at an
    earlier point in a longer conversation must still resolve correctly,
    while the untouched later turns on the original branch stay intact."""
    human1 = HumanMessage(content="ilk soru")
    ai1 = AIMessage(content="ilk cevap")
    human2 = HumanMessage(content="ikinci soru")
    ai2_original = AIMessage(content="ikinci cevap")

    checkpoints = [
        {"checkpoint_id": "c1", "parent_checkpoint_id": None, "messages": [human1]},
        {
            "checkpoint_id": "c2",
            "parent_checkpoint_id": "c1",
            "messages": [human1, ai1],
        },
        {
            "checkpoint_id": "c3",
            "parent_checkpoint_id": "c2",
            "messages": [human1, ai1, human2],
        },
        {
            "checkpoint_id": "c4-original",
            "parent_checkpoint_id": "c3",
            "messages": [human1, ai1, human2, ai2_original],
        },
        {
            # A retry of the FIRST turn, forked from c1 (before ai1).
            "checkpoint_id": "c2-retry",
            "parent_checkpoint_id": "c1",
            "messages": [human1, AIMessage(content="ilk cevap (retry)")],
        },
    ]

    messages, _ = reconstruct_message_tree(
        checkpoints, thread_metadata={"persona_id": 0}, chat_session_id="thread-deep-fork"
    )

    by_content = {m["message"]: m for m in messages if m["message"]}
    assert by_content["ilk cevap"]["parent_message"] == by_content["ilk cevap (retry)"][
        "parent_message"
    ]
    # The untouched second turn is unaffected by the earlier retry branch.
    assert by_content["ikinci cevap"]["parent_message"] == by_content["ikinci soru"][
        "message_id"
    ]


def test_reconstruct_message_tree_accumulates_a_tool_call_turn_split_across_checkpoints():
    """A tool-loop turn produces one checkpoint per graph step — the tool
    call, the tool result, and the final answer can each land in their own
    checkpoint. The delta-walk must accumulate these exactly like the flat
    reconstruction does when they all arrive in one list."""
    human = HumanMessage(content="hesapla")
    ai_tool_call = AIMessage(
        content="", tool_calls=[{"name": "Calculator", "args": {}, "id": "call-1"}]
    )
    tool_result = ToolMessage(content="4", tool_call_id="call-1", name="Calculator")
    ai_final = AIMessage(content="4 eder.")

    flat_messages, flat_packets = reconstruct_messages(
        [human, ai_tool_call, tool_result, ai_final],
        thread_metadata={"persona_id": 0},
        chat_session_id="thread-tool",
    )

    checkpoints = [
        {"checkpoint_id": "c1", "parent_checkpoint_id": None, "messages": [human]},
        {
            "checkpoint_id": "c2",
            "parent_checkpoint_id": "c1",
            "messages": [human, ai_tool_call],
        },
        {
            "checkpoint_id": "c3",
            "parent_checkpoint_id": "c2",
            "messages": [human, ai_tool_call, tool_result],
        },
        {
            "checkpoint_id": "c4",
            "parent_checkpoint_id": "c3",
            "messages": [human, ai_tool_call, tool_result, ai_final],
        },
    ]
    tree_messages, tree_packets = reconstruct_message_tree(
        checkpoints, thread_metadata={"persona_id": 0}, chat_session_id="thread-tool"
    )

    assert tree_messages == flat_messages
    assert tree_packets == flat_packets


def test_reconstruct_message_tree_flushes_trailing_tool_packets_only_at_leaves():
    """A mid-tree checkpoint whose tool call has no response yet (because
    a LATER checkpoint continues that same turn) must not be flushed as if
    the conversation ended there — only true leaves get that treatment."""
    human = HumanMessage(content="ara")
    ai_tool_call = AIMessage(
        content="", tool_calls=[{"name": "web_search", "args": {}, "id": "call-1"}]
    )
    tool_result = ToolMessage(content="ok", tool_call_id="call-1", name="web_search")

    checkpoints = [
        {"checkpoint_id": "c1", "parent_checkpoint_id": None, "messages": [human]},
        {
            "checkpoint_id": "c2",
            "parent_checkpoint_id": "c1",
            "messages": [human, ai_tool_call],
        },
        {
            "checkpoint_id": "c3",
            "parent_checkpoint_id": "c2",
            "messages": [human, ai_tool_call, tool_result],
        },
    ]

    messages, packets_2d = reconstruct_message_tree(
        checkpoints, thread_metadata={"persona_id": 0}, chat_session_id="thread-leaf"
    )

    # c3 (the only leaf) has no final AI message, so the trailing-tool-packet
    # flush kicks in exactly once, not once per intermediate checkpoint.
    assistant_messages = [m for m in messages if m["message_type"] == "assistant"]
    assert len(assistant_messages) == 1
    assert len(packets_2d) == 1


def test_reconstruct_messages_does_not_merge_a_document_only_turn_into_the_next_turn():
    """A turn whose only visible result is a generated file (the model calls
    a document tool and the graph's closing AI message is empty, since
    is_document_tool calls are deliberately not shown as their own tool
    step) must still become its own assistant message. Regression test for
    a real production bug: without this, the empty-content AI message was
    silently dropped and its buffered generated_file packet leaked into
    whatever the NEXT turn's assistant message happened to be, visually
    merging two unrelated turns (and their file cards) into one chat
    bubble."""
    human1 = HumanMessage(content="bir docx oluştur")
    ai_creates_doc = AIMessage(
        content="",
        tool_calls=[{"name": "create_document", "args": {}, "id": "call-1"}],
    )
    tool_result = ToolMessage(
        content=(
            '{"__generated_file__": true, "document_id": "doc-1", "version": 1, '
            '"file_id": "file-1", "filename": "rapor.docx", '
            '"mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document", '
            '"size_bytes": 123, "download_url": "/download/file-1"}'
        ),
        tool_call_id="call-1",
        name="create_document",
    )
    ai_closing_empty = AIMessage(content="")
    human2 = HumanMessage(content="teşekkürler, şimdi özetle")
    ai_reply = AIMessage(content="İşte özet.")

    messages, packets_2d = reconstruct_messages(
        [human1, ai_creates_doc, tool_result, ai_closing_empty, human2, ai_reply],
        thread_metadata={"persona_id": 0},
        chat_session_id="thread-doc-only-turn",
    )

    assert [m["message_type"] for m in messages] == [
        "user",
        "assistant",
        "user",
        "assistant",
    ]
    user1, ai1, user2, ai2 = messages
    assert ai1["parent_message"] == user1["message_id"]
    assert ai1["message"] == ""
    assert user2["parent_message"] == ai1["message_id"]
    assert ai2["message"] == "İşte özet."

    assert len(packets_2d) == 2
    ai1_packet_types = [p["obj"]["type"] for p in packets_2d[0]]
    ai2_packet_types = [p["obj"]["type"] for p in packets_2d[1]]
    assert "generated_file" in ai1_packet_types
    assert "generated_file" not in ai2_packet_types
