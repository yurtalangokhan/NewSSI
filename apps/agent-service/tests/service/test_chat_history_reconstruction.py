"""Direct unit tests for the extracted reconstruction module.

Mirrors the scenarios already covered end-to-end through
ChatController.get_chat_session (tests/controller/test_chat_controller_history.py)
but calls reconstruct_messages directly — this is the function
CheckpointBranchService also depends on for locating fork points.
"""

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from service.ChatHistoryReconstruction import reconstruct_message_tree, reconstruct_messages


def test_reconstruct_messages_translates_web_search_into_search_tool_packets():
    web_search_result = (
        "TITLE: Onyx: Open Source AI Platform\n"
        "URL: https://onyx.app\n"
        "SNIPPET: Onyx is the open source generative AI platform."
    )

    messages, packets_2d = reconstruct_messages(
        [
            HumanMessage(content="Onyx nedir"),
            AIMessage(
                content="",
                tool_calls=[{"name": "web_search", "args": {"query": "Onyx"}, "id": "call-1"}],
            ),
            ToolMessage(content=web_search_result, tool_call_id="call-1", name="web_search"),
            AIMessage(content="Onyx açık kaynaklı bir platform."),
        ],
        thread_metadata={"user_id": "user-1", "persona_id": 1},
        chat_session_id="thread-web-search",
    )

    assert len(packets_2d) == 1
    packet_types = [p["obj"]["type"] for p in packets_2d[0]]
    assert "search_tool_start" in packet_types
    assert "search_tool_queries_delta" in packet_types
    assert "search_tool_documents_delta" in packet_types
    assert "custom_tool_start" not in packet_types
    assert "custom_tool_delta" not in packet_types

    docs_packet = next(
        p["obj"] for p in packets_2d[0] if p["obj"]["type"] == "search_tool_documents_delta"
    )
    assert docs_packet["documents"][0]["document_id"] == "https://onyx.app"


def test_reconstruct_messages_handles_web_search_error_cleanly_without_custom_tool_delta():
    messages, packets_2d = reconstruct_messages(
        [
            HumanMessage(content="Onyx nedir"),
            AIMessage(
                content="",
                tool_calls=[{"name": "web_search", "args": {"query": "Onyx"}, "id": "call-1"}],
            ),
            ToolMessage(
                content="Web search error: timeout", tool_call_id="call-1", name="web_search"
            ),
            AIMessage(content="Aramada bir sorun oluştu."),
        ],
        thread_metadata={"user_id": "user-1", "persona_id": 1},
        chat_session_id="thread-web-search-error",
    )

    packet_types = [p["obj"]["type"] for p in packets_2d[0]]
    assert "search_tool_start" in packet_types
    assert "search_tool_queries_delta" in packet_types
    assert "search_tool_documents_delta" in packet_types
    assert "custom_tool_delta" not in packet_types


def test_reconstruct_messages_handles_fetch_webpage_404_error_cleanly():
    messages, packets_2d = reconstruct_messages(
        [
            HumanMessage(content="Valkey oku"),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "fetch_webpage",
                        "args": {"url": "https://example.com/404"},
                        "id": "call-1",
                    }
                ],
            ),
            ToolMessage(
                content="Error fetching webpage: Client error '404 Not Found' for url 'https://example.com/404'",
                tool_call_id="call-1",
                name="fetch_webpage",
            ),
            AIMessage(content="Sayfaya ulaşılamadı."),
        ],
        thread_metadata={"user_id": "user-1", "persona_id": 1},
        chat_session_id="thread-fetch-404-error",
    )

    packet_types = [p["obj"]["type"] for p in packets_2d[0]]
    assert "open_url_start" in packet_types
    assert "open_url_urls" in packet_types
    assert "open_url_documents" in packet_types
    assert "custom_tool_delta" not in packet_types


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
    assert (
        by_content["ilk cevap"]["parent_message"]
        == by_content["ilk cevap (retry)"]["parent_message"]
    )
    # The untouched second turn is unaffected by the earlier retry branch.
    assert by_content["ikinci cevap"]["parent_message"] == by_content["ikinci soru"]["message_id"]


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


def test_reconstruct_messages_groups_web_search_and_fetch_webpage_turns_consistently_with_live_stream():
    """Verify that multiple parallel web searches group into one turn,
    reasoning steps get their own turns, and each fetch_webpage gets its own turn
    with queries, URLs, and document deltas on the correct turns."""
    web_result_1 = (
        "TITLE: Valkey vs Redis\nURL: https://example.com/valkey\nSNIPPET: Valkey comparison"
    )
    web_result_2 = "TITLE: Benchmarks\nURL: https://example.com/bench\nSNIPPET: Benchmark results"
    fetch_result_1 = (
        "TITLE: What is Valkey?\nDESCRIPTION: A deep look at Valkey\n---\nContent of Valkey page"
    )

    raw_msgs = [
        HumanMessage(content="Valkey vs Redis 8 karşılaştırması"),
        # Step 1: Initial reasoning before tools
        AIMessage(
            content="",
            additional_kwargs={"thinking": "The user is asking for a comparison..."},
            tool_calls=[
                {"name": "web_search", "args": {"query": "Valkey vs Redis 8"}, "id": "call-1"},
                {"name": "web_search", "args": {"query": "Valkey Redis benchmark"}, "id": "call-2"},
            ],
        ),
        ToolMessage(content=web_result_1, tool_call_id="call-1", name="web_search"),
        ToolMessage(content=web_result_2, tool_call_id="call-2", name="web_search"),
        # Step 2: Intermediate reasoning before fetch
        AIMessage(
            content="",
            additional_kwargs={"thinking": "Good start! Now let me fetch the page..."},
            tool_calls=[
                {
                    "name": "fetch_webpage",
                    "args": {"url": "https://example.com/valkey"},
                    "id": "call-3",
                },
            ],
        ),
        ToolMessage(content=fetch_result_1, tool_call_id="call-3", name="fetch_webpage"),
        # Final answer
        AIMessage(content="İşte Valkey ve Redis 8 karşılaştırma raporu: ..."),
    ]

    messages, packets_2d = reconstruct_messages(
        raw_msgs,
        thread_metadata={"user_id": "user-1", "persona_id": 1},
        chat_session_id="thread-search-fetch-stream-parity",
    )

    assert len(packets_2d) == 1
    packets = packets_2d[0]

    # Map packets by turn_index
    by_turn = {}
    for p in packets:
        turn = p["placement"]["turn_index"]
        by_turn.setdefault(turn, []).append(p["obj"]["type"])

    # Turn 0: reasoning
    assert by_turn[0] == ["reasoning_start", "reasoning_delta"]

    # Turn 1: both web searches grouped together with queries and documents
    assert by_turn[1] == [
        "search_tool_start",
        "search_tool_queries_delta",
        "search_tool_documents_delta",
        "search_tool_start",
        "search_tool_queries_delta",
        "search_tool_documents_delta",
    ]

    # Turn 2: intermediate reasoning
    assert by_turn[2] == ["reasoning_start", "reasoning_delta"]

    # Turn 3: fetch_webpage (start + urls + documents together on turn 3)
    assert by_turn[3] == ["open_url_start", "open_url_urls", "open_url_documents"]

    # Turn 4: final answer message_start + stop
    assert by_turn[4] == ["message_start", "stop"]


# ---------------------------------------------------------------------------
# FlowAgent: forked-tree reconstruction with multi-message super-steps, plus
# persisted graph-stage-timeline replay (.tmp/2026-08-27-flow-agent-
# checkpoint-and-stage-timeline-design.md).
# ---------------------------------------------------------------------------


def _flow_forked_checkpoints():
    """A flow turn writes several checkpoints per super-step and adds more
    than one message at a time. The retry forks from the [human]-only
    checkpoint. No subgraph-namespace checkpoints appear here — the
    ThreadController history filter already excluded them."""
    h1 = HumanMessage(content="rapor hazırla", id="h1")
    a_step1 = AIMessage(
        content="", id="a1", tool_calls=[{"name": "web_search", "args": {}, "id": "c1"}]
    )
    a_tool = ToolMessage(content="bulgular", tool_call_id="c1", name="web_search")
    a_final = AIMessage(content="ilk rapor", id="a-final")

    b_step1 = AIMessage(
        content="", id="b1", tool_calls=[{"name": "web_search", "args": {}, "id": "c2"}]
    )
    b_tool = ToolMessage(content="yeni bulgular", tool_call_id="c2", name="web_search")
    b_final = AIMessage(content="ikinci rapor", id="b-final")

    return [
        {"checkpoint_id": "root", "parent_checkpoint_id": None, "messages": []},
        {"checkpoint_id": "c-human", "parent_checkpoint_id": "root", "messages": [h1]},
        # branch A
        {
            "checkpoint_id": "a-1",
            "parent_checkpoint_id": "c-human",
            "messages": [h1, a_step1, a_tool],
        },
        {
            "checkpoint_id": "a-2",
            "parent_checkpoint_id": "a-1",
            "messages": [h1, a_step1, a_tool, a_final],
        },
        # branch B — forked from the same [human]-only checkpoint
        {
            "checkpoint_id": "b-1",
            "parent_checkpoint_id": "c-human",
            "messages": [h1, b_step1, b_tool],
        },
        {
            "checkpoint_id": "b-2",
            "parent_checkpoint_id": "b-1",
            "messages": [h1, b_step1, b_tool, b_final],
        },
    ]


def test_flow_forked_tree_reconstructs_both_answers_as_siblings():
    messages, _ = reconstruct_message_tree(
        _flow_forked_checkpoints(),
        thread_metadata={"persona_id": 7},
        chat_session_id="thread-flow-fork",
    )

    by_content = {m["message"]: m for m in messages if m["message"]}
    user = next(m for m in messages if m["message_type"] == "user")
    assert by_content["ilk rapor"]["parent_message"] == user["message_id"]
    assert by_content["ikinci rapor"]["parent_message"] == user["message_id"]
    # distinct, non-colliding ids
    assert by_content["ilk rapor"]["message_id"] != by_content["ikinci rapor"]["message_id"]
    # newest branch is the active one
    assert user["latest_child_message"] == by_content["ikinci rapor"]["message_id"]


def test_flow_stage_timeline_is_replayed_as_graph_stage_packets_on_the_matching_turn():
    checkpoints = _flow_forked_checkpoints()
    metadata = {
        "persona_id": 7,
        "flow_stage_timelines": {
            "a-final": [
                {"stage_name": "ChatInput-1", "event": "start", "timestamp": 1000},
                {"stage_name": "ChatInput-1", "event": "end", "timestamp": 1200},
                {"stage_name": "ReActAgent-x", "event": "start", "timestamp": 1200},
                {"stage_name": "ReActAgent-x", "event": "end", "timestamp": 2600},
            ]
        },
    }
    messages, packets_2d = reconstruct_message_tree(
        checkpoints, thread_metadata=metadata, chat_session_id="thread-flow-fork"
    )

    assistants = [m for m in messages if m["message_type"] == "assistant"]
    first_idx = next(i for i, m in enumerate(assistants) if m["message"] == "ilk rapor")
    second_idx = next(i for i, m in enumerate(assistants) if m["message"] == "ikinci rapor")

    first_types = [p["obj"]["type"] for p in packets_2d[first_idx]]
    assert first_types[:4] == [
        "graph_stage_start",
        "graph_stage_end",
        "graph_stage_start",
        "graph_stage_end",
    ]
    replayed = packets_2d[first_idx][:4]
    assert replayed[0]["obj"] == {
        "type": "graph_stage_start",
        "stage_name": "ChatInput-1",
        "timestamp": 1000,
    }
    assert replayed[3]["obj"]["timestamp"] == 2600

    # The other branch has no timeline entry — its packet list is untouched.
    assert not any(p["obj"]["type"].startswith("graph_stage_") for p in packets_2d[second_idx])


def test_flow_stage_timeline_replay_works_in_the_flat_reconstruct_messages_path():
    h1 = HumanMessage(content="soru", id="h1")
    a_final = AIMessage(content="cevap", id="a-final")
    messages, packets_2d = reconstruct_messages(
        [h1, a_final],
        thread_metadata={
            "persona_id": 0,
            "flow_stage_timelines": {
                "a-final": [
                    {"stage_name": "Node-1", "event": "start", "timestamp": 5},
                    {"stage_name": "Node-1", "event": "end", "timestamp": 9},
                ]
            },
        },
        chat_session_id="thread-flat",
    )

    assert [p["obj"]["type"] for p in packets_2d[0][:2]] == [
        "graph_stage_start",
        "graph_stage_end",
    ]
    assert packets_2d[0][0]["obj"]["stage_name"] == "Node-1"


def test_flow_stage_timeline_table_is_shared_by_reference_across_branch_clones():
    """Both sibling branches must see the same lookup table without one
    branch's walk mutating it for the other."""
    checkpoints = _flow_forked_checkpoints()
    table = {
        "a-final": [{"stage_name": "N", "event": "start", "timestamp": 1}],
        "b-final": [{"stage_name": "N", "event": "start", "timestamp": 2}],
    }
    metadata = {"persona_id": 7, "flow_stage_timelines": table}
    reconstruct_message_tree(checkpoints, thread_metadata=metadata, chat_session_id="t")
    assert table == {
        "a-final": [{"stage_name": "N", "event": "start", "timestamp": 1}],
        "b-final": [{"stage_name": "N", "event": "start", "timestamp": 2}],
    }


# ---------------------------------------------------------------------------
# Flow single-turn output — a multi-stage FlowAgent run collapses to ONE
# assistant turn on reload. Read-only, in reconstruct_message_tree; the
# compiled graph is never touched. (project_flow_single_turn_output)
#
# Rule: a stage's text FOLDS into collapsed reasoning iff a LATER stage in
# the run still calls a tool (it was prep, not the answer). Every trailing
# text-only stage IS the answer; consecutive ones concatenate into one
# bubble. Gated on flow_stage_timelines carrying the run's last message id.
# ---------------------------------------------------------------------------


def _flow_run_checkpoints(react_final="## Final comparison table\n| Model | Ctx |"):
    """research (web_search) -> analysis (run_python) -> react (text only),
    then the noop loop/merge/output nodes."""
    h = HumanMessage(content="research 3 llms")
    r_call = AIMessage(
        content="", tool_calls=[{"name": "web_search", "args": {"query": "llama ctx"}, "id": "w1"}]
    )
    r_res = ToolMessage(
        content="TITLE: Llama\nURL: http://x\nSNIPPET: 128k", tool_call_id="w1", name="web_search"
    )
    r_final = AIMessage(content="## Research briefing\n- Llama 3.1: 128000", id="ai-research")
    a_call = AIMessage(
        content="",
        tool_calls=[{"name": "run_python", "args": {"code": "print(128000)"}, "id": "p1"}],
    )
    a_res = ToolMessage(content="128000", tool_call_id="p1", name="run_python")
    a_final = AIMessage(content="## Calc summary\nAverage: 128000 tokens", id="ai-analysis")
    react_msg = AIMessage(content=react_final, id="ai-final")

    after_input = [h]
    after_research = after_input + [r_call, r_res, r_final]
    after_analysis = after_research + [a_call, a_res, a_final]
    after_react = after_analysis + [react_msg]
    return [
        {"checkpoint_id": "c0", "parent_checkpoint_id": None, "messages": after_input},
        {"checkpoint_id": "c1", "parent_checkpoint_id": "c0", "messages": after_research},
        {"checkpoint_id": "c2", "parent_checkpoint_id": "c1", "messages": after_analysis},
        {"checkpoint_id": "c3", "parent_checkpoint_id": "c2", "messages": after_react},
        {"checkpoint_id": "c4", "parent_checkpoint_id": "c3", "messages": after_react},
        {"checkpoint_id": "c5", "parent_checkpoint_id": "c4", "messages": after_react},
        {"checkpoint_id": "c6", "parent_checkpoint_id": "c5", "messages": after_react},
    ]


_FLOW_TIMELINE = {
    "ai-final": [
        {"stage_name": "node-stage-research", "event": "start", "timestamp": 1},
        {"stage_name": "node-stage-research", "event": "end", "timestamp": 9},
    ]
}
_FLOW_MD = {"persona_id": 50, "flow_stage_timelines": _FLOW_TIMELINE}


def test_flow_run_collapses_to_one_turn_prep_folded_answer_kept():
    messages, packets_2d = reconstruct_message_tree(
        _flow_run_checkpoints(), thread_metadata=_FLOW_MD, chat_session_id="t-flow"
    )
    assistants = [m for m in messages if m["message_type"] == "assistant"]
    assert len(assistants) == 1
    # research (a later stage still calls run_python) -> folded into reasoning
    # analysis + react (no tool after them) -> concatenated as the answer
    assert assistants[0]["message"] == (
        "## Calc summary\nAverage: 128000 tokens\n\n## Final comparison table\n| Model | Ctx |"
    )

    flat = [p["obj"] for turn in packets_2d for p in turn]
    reasoning = [p["reasoning"] for p in flat if p.get("type") == "reasoning_delta"]
    assert any("Research briefing" in r and "128000" in r for r in reasoning)
    assert not any("Calc summary" in r for r in reasoning)  # answer content, not folded
    kinds = [p.get("type") for p in flat]
    assert any(k and "search" in k for k in kinds)
    assert any(p.get("tool_name") == "run_python" for p in flat)
    assert kinds.count("graph_stage_start") == 1  # one strip on the one turn


def test_flow_run_weak_final_stage_still_keeps_the_real_answer():
    """The bug from thread 39134dae: react only emitted a references footer.
    The calc summary (previous text-only stage) must stay in the headline,
    not be folded away."""
    messages, _ = reconstruct_message_tree(
        _flow_run_checkpoints(react_final="## References\n- Meta Llama 3.1 Blog Post"),
        thread_metadata=_FLOW_MD,
        chat_session_id="t-weakfinal",
    )
    assistants = [m for m in messages if m["message_type"] == "assistant"]
    assert len(assistants) == 1
    assert "Calc summary" in assistants[0]["message"]
    assert "References" in assistants[0]["message"]


def test_flow_run_not_collapsed_without_stage_timeline():
    messages, _ = reconstruct_message_tree(
        _flow_run_checkpoints(),
        thread_metadata={"persona_id": 50},
        chat_session_id="t-noflow",
    )
    assert [m["message"] for m in messages if m["message_type"] == "assistant"] == [
        "## Research briefing\n- Llama 3.1: 128000",
        "## Calc summary\nAverage: 128000 tokens",
        "## Final comparison table\n| Model | Ctx |",
    ]


def test_flow_run_not_collapsed_when_trailing_id_absent_from_timeline():
    messages, _ = reconstruct_message_tree(
        _flow_run_checkpoints(),
        thread_metadata={
            "persona_id": 50,
            "flow_stage_timelines": {
                "unrelated": [{"stage_name": "N", "event": "start", "timestamp": 1}]
            },
        },
        chat_session_id="t-mismatch",
    )
    assert len([m for m in messages if m["message_type"] == "assistant"]) == 3


def test_classic_two_turn_thread_unaffected_even_with_timeline_present():
    h1, h2 = HumanMessage(content="q1"), HumanMessage(content="q2")
    a1, a2 = AIMessage(content="answer 1", id="x1"), AIMessage(content="answer 2", id="x2")
    checkpoints = [
        {"checkpoint_id": "c0", "parent_checkpoint_id": None, "messages": [h1]},
        {"checkpoint_id": "c1", "parent_checkpoint_id": "c0", "messages": [h1, a1]},
        {"checkpoint_id": "c2", "parent_checkpoint_id": "c1", "messages": [h1, a1, h2]},
        {"checkpoint_id": "c3", "parent_checkpoint_id": "c2", "messages": [h1, a1, h2, a2]},
    ]
    messages, _ = reconstruct_message_tree(
        checkpoints,
        thread_metadata={"persona_id": 1, "flow_stage_timelines": {"x1": [], "x2": []}},
        chat_session_id="t-classic",
    )
    assert [m["message"] for m in messages if m["message_type"] == "assistant"] == [
        "answer 1",
        "answer 2",
    ]


def test_retry_fork_mid_flow_run_is_not_collapsed():
    h = HumanMessage(content="q")
    stage = AIMessage(content="stage draft", id="ai-stage")
    fa, fb = AIMessage(content="final A", id="final-a"), AIMessage(content="final B", id="final-b")
    checkpoints = [
        {"checkpoint_id": "c0", "parent_checkpoint_id": None, "messages": [h]},
        {"checkpoint_id": "s1", "parent_checkpoint_id": "c0", "messages": [h, stage]},
        {"checkpoint_id": "s2a", "parent_checkpoint_id": "s1", "messages": [h, stage, fa]},
        {"checkpoint_id": "s2b", "parent_checkpoint_id": "s1", "messages": [h, stage, fb]},
    ]
    messages, _ = reconstruct_message_tree(
        checkpoints,
        thread_metadata={"persona_id": 50, "flow_stage_timelines": {"final-a": [], "final-b": []}},
        chat_session_id="t-forkflow",
    )
    assert {m["message"] for m in messages if m["message_type"] == "assistant"} == {
        "stage draft",
        "final A",
        "final B",
    }


def test_flow_run_then_classic_turn_in_same_thread():
    cps = _flow_run_checkpoints()
    tail = cps[-1]["messages"]
    h2 = HumanMessage(content="thanks")
    a2 = AIMessage(content="you're welcome", id="ai-tail")
    cps += [
        {"checkpoint_id": "c7", "parent_checkpoint_id": "c6", "messages": tail + [h2]},
        {"checkpoint_id": "c8", "parent_checkpoint_id": "c7", "messages": tail + [h2, a2]},
    ]
    messages, _ = reconstruct_message_tree(cps, thread_metadata=_FLOW_MD, chat_session_id="t-mixed")
    assert [m["message_type"] for m in messages] == ["user", "assistant", "user", "assistant"]
    ai = [m["message"] for m in messages if m["message_type"] == "assistant"]
    assert ai[0].endswith("## Final comparison table\n| Model | Ctx |")
    assert ai[1] == "you're welcome"
