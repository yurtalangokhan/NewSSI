"""Tests for chat history reconstruction in ChatController."""

import json

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from controller.chat_controller import ChatController


class DummyThreadController:
    def __init__(self, thread: dict, state: dict):
        self._thread = thread
        self._state = state

    async def get_thread(self, thread_id: str):
        return self._thread

    async def get_thread_state(self, thread_id: str):
        return self._state

    async def update_thread(self, thread_id: str, metadata: dict, update_timestamp: bool = True):
        self._thread["metadata"] = metadata
        return self._thread


class DummyThreadControllerWithHistory(DummyThreadController):
    """Adds get_thread_state_history so get_chat_session takes the
    branch-tree reconstruction path instead of falling back to the
    single-state one (which is all DummyThreadController supports)."""

    def __init__(self, thread: dict, state: dict, checkpoints: list[dict]):
        super().__init__(thread=thread, state=state)
        self._checkpoints = checkpoints

    async def get_thread_state_history(self, thread_id: str):
        return self._checkpoints


class DummyThreadListController:
    def __init__(self, threads: list[dict]):
        self._threads = threads
        self.list_calls: list[dict] = []
        self.activity_list_calls: list[dict] = []

    async def list_threads(self, limit: int = 100, offset: int = 0, metadata: dict | None = None):
        self.list_calls.append({"limit": limit, "offset": offset, "metadata": metadata})
        if metadata:
            return [
                thread
                for thread in self._threads
                if all(
                    (thread.get("metadata", {}) or {}).get(key) == value
                    for key, value in metadata.items()
                )
            ][offset : offset + limit]
        return self._threads[offset : offset + limit]

    async def list_chat_sessions_by_activity(
        self,
        page_size: int = 100,
        before_activity: str | None = None,
        before_id: str | None = None,
        metadata: dict | None = None,
    ):
        self.activity_list_calls.append(
            {
                "page_size": page_size,
                "before_activity": before_activity,
                "before_id": before_id,
                "metadata": metadata,
            }
        )
        return self._threads[:page_size]


@pytest.mark.asyncio
async def test_get_chat_sessions_includes_legacy_keycloak_owner_ids():
    threads = [
        {
            "thread_id": "legacy-thread",
            "metadata": {
                "user_id": "keycloak-subject",
                "persona_id": 1,
                "name": "Legacy Chat",
            },
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
        },
        {
            "thread_id": "other-thread",
            "metadata": {"user_id": "other-user", "persona_id": 1, "name": "Other"},
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
        },
    ]
    thread_controller = DummyThreadListController(threads)
    controller = ChatController(
        thread_controller=thread_controller,
        user_id="local-user-id",
        owner_ids=["local-user-id", "keycloak-subject"],
    )

    result = await controller.get_chat_sessions()

    assert [session["id"] for session in result["sessions"]] == ["legacy-thread"]
    assert thread_controller.activity_list_calls[0]["metadata"] is None


@pytest.mark.asyncio
async def test_get_chat_session_skips_system_memory_messages_and_replays_ltm_packet():
    memory_context = (
        "[Long-Term Memory — Previously learned facts about this user]\n"
        "- User likes tea\n"
        "[End of Long-Term Memory]"
    )
    thread = {
        "thread_id": "thread-1",
        "metadata": {"user_id": "user-1", "persona_id": 1, "name": "Chat"},
    }
    state = {
        "values": {
            "messages": [
                SystemMessage(content=memory_context),
                HumanMessage(content="merhaba"),
                AIMessage(content="selam", additional_kwargs={"_ltm_recalled": 1}),
            ]
        }
    }

    controller = ChatController(
        thread_controller=DummyThreadController(thread=thread, state=state),
        user_id="user-1",
    )

    result = await controller.get_chat_session("thread-1")

    assert [m["message_type"] for m in result["messages"]] == ["user", "assistant"]
    assert [m["message"] for m in result["messages"]] == ["merhaba", "selam"]
    assert result["packets"][0][0]["obj"]["type"] == "long_term_memory_recall"


@pytest.mark.asyncio
async def test_get_chat_session_reconstructs_ltm_from_system_context_without_metadata():
    memory_context = (
        "[Long-Term Memory — Previously learned facts about this user]\n"
        "- User likes tea\n"
        "- Speaks Turkish\n"
        "[End of Long-Term Memory]"
    )
    thread = {
        "thread_id": "thread-2",
        "metadata": {"user_id": "user-1", "persona_id": 1, "name": "Chat"},
    }
    state = {
        "values": {
            "messages": [
                SystemMessage(content=memory_context),
                HumanMessage(content="merhaba"),
                AIMessage(content="selam"),
            ]
        }
    }

    controller = ChatController(
        thread_controller=DummyThreadController(thread=thread, state=state),
        user_id="user-1",
    )

    result = await controller.get_chat_session("thread-2")

    assert [m["message_type"] for m in result["messages"]] == ["user", "assistant"]
    assert result["packets"][0][0]["obj"]["type"] == "long_term_memory_recall"
    assert result["packets"][0][0]["obj"]["fact_count"] == 2


class _BoomMessage:
    """A message shaped enough to reach the AI branch, then blow up on it.

    Mimics an unexpected LangGraph message shape deep in a long tool-heavy
    conversation (e.g. an unusual `tool_calls` payload).
    """

    type = "ai"
    content = ""
    additional_kwargs: dict = {}

    @property
    def tool_calls(self):
        raise RuntimeError("boom")


@pytest.mark.asyncio
async def test_get_chat_session_keeps_turns_parsed_before_a_later_failure():
    thread = {
        "thread_id": "thread-boom",
        "metadata": {"user_id": "user-1", "persona_id": 1, "name": "Chat"},
    }
    state = {
        "values": {
            "messages": [
                HumanMessage(content="merhaba"),
                AIMessage(content="selam"),
                _BoomMessage(),
            ]
        }
    }

    controller = ChatController(
        thread_controller=DummyThreadController(thread=thread, state=state),
        user_id="user-1",
    )

    result = await controller.get_chat_session("thread-boom")

    # The first turn parsed fine before the third message blew up — it must
    # not be discarded just because a later message in the same thread failed.
    assert [m["message_type"] for m in result["messages"]] == ["user", "assistant"]
    assert [m["message"] for m in result["messages"]] == ["merhaba", "selam"]


@pytest.mark.asyncio
async def test_get_chat_session_keeps_multiple_tool_steps_in_separate_turns():
    thread = {
        "thread_id": "thread-3",
        "metadata": {"user_id": "user-1", "persona_id": 1, "name": "Chat"},
    }
    state = {
        "values": {
            "messages": [
                HumanMessage(content="Gazi Universitesi hakkinda arastirma yapar misin?"),
                {
                    "type": "ai",
                    "content": "",
                    "tool_calls": [{"name": "generic_tool_a"}],
                },
                {
                    "type": "tool",
                    "name": "generic_tool_a",
                    "content": "search results",
                },
                {
                    "type": "ai",
                    "content": "",
                    "tool_calls": [{"name": "generic_tool_b"}],
                },
                {
                    "type": "tool",
                    "name": "generic_tool_b",
                    "content": "ssl error",
                },
                AIMessage(content="Sonuclari derledim."),
            ]
        }
    }

    controller = ChatController(
        thread_controller=DummyThreadController(thread=thread, state=state),
        user_id="user-1",
    )

    result = await controller.get_chat_session("thread-3")
    packets = result["packets"][0]

    tool_packets = [p for p in packets if p["obj"]["type"].startswith("custom_tool_")]
    tool_names = [p["obj"].get("tool_name") for p in tool_packets]
    tool_turns = [p["placement"]["turn_index"] for p in tool_packets]

    assert tool_names == ["generic_tool_a", "generic_tool_a", "generic_tool_b", "generic_tool_b"]
    assert tool_turns == sorted(tool_turns)
    assert len(set(tool_turns)) >= 2


@pytest.mark.asyncio
async def test_get_chat_session_pairs_parallel_tool_calls_by_id_not_arrival_order():
    """A deep-research turn fires several tool calls at once (all their
    `custom_tool_start`s land in the state before any result comes back), and
    the results can arrive out of order relative to their calls. Each result
    must still land right after its own call's start, matched by
    tool_call_id — not just appended wherever it happened to arrive."""
    thread = {
        "thread_id": "thread-6",
        "metadata": {"user_id": "user-1", "persona_id": 1, "name": "Chat"},
    }
    state = {
        "values": {
            "messages": [
                HumanMessage(content="karsilastir"),
                {
                    "type": "ai",
                    "content": "",
                    "tool_calls": [
                        {"name": "generic_tool_a", "args": {"query": "a"}, "id": "call-a"},
                        {"name": "generic_tool_a", "args": {"query": "b"}, "id": "call-b"},
                        {"name": "generic_tool_b", "args": {"url": "c"}, "id": "call-c"},
                    ],
                },
                # Results arrive out of order and interleaved with each other.
                {
                    "type": "tool",
                    "name": "generic_tool_b",
                    "content": "result c",
                    "tool_call_id": "call-c",
                },
                {
                    "type": "tool",
                    "name": "generic_tool_a",
                    "content": "result b",
                    "tool_call_id": "call-b",
                },
                {
                    "type": "tool",
                    "name": "generic_tool_a",
                    "content": "result a",
                    "tool_call_id": "call-a",
                },
            ]
        }
    }

    controller = ChatController(
        thread_controller=DummyThreadController(thread=thread, state=state),
        user_id="user-1",
    )

    result = await controller.get_chat_session("thread-6")
    packets = result["packets"][0]

    tool_packets = [p for p in packets if p["obj"]["type"].startswith("custom_tool_")]
    shape = [(p["obj"]["type"], p["obj"].get("data") or p["obj"].get("args")) for p in tool_packets]

    assert shape == [
        ("custom_tool_start", {"query": "a"}),
        ("custom_tool_delta", "result a"),
        ("custom_tool_start", {"query": "b"}),
        ("custom_tool_delta", "result b"),
        ("custom_tool_start", {"url": "c"}),
        ("custom_tool_delta", "result c"),
    ]


@pytest.mark.asyncio
async def test_get_chat_session_reconstructs_ltm_from_user_message_metadata_marker():
    thread = {
        "thread_id": "thread-4",
        "metadata": {"user_id": "user-1", "persona_id": 1, "name": "Chat"},
    }
    state = {
        "values": {
            "messages": [
                HumanMessage(content="merhaba", additional_kwargs={"_ltm_recalled": 7}),
                AIMessage(content="selam"),
            ]
        }
    }

    controller = ChatController(
        thread_controller=DummyThreadController(thread=thread, state=state),
        user_id="user-1",
    )

    result = await controller.get_chat_session("thread-4")
    assert result["packets"][0][0]["obj"]["type"] == "long_term_memory_recall"
    assert result["packets"][0][0]["obj"]["fact_count"] == 7


@pytest.mark.asyncio
async def test_get_chat_session_preserves_trailing_tool_packets_without_final_ai_message():
    thread = {
        "thread_id": "thread-5",
        "metadata": {"user_id": "user-1", "persona_id": 1, "name": "Chat"},
    }
    state = {
        "values": {
            "messages": [
                HumanMessage(content="arastir"),
                {"type": "ai", "content": "", "tool_calls": [{"name": "generic_tool_a"}]},
                {"type": "tool", "name": "generic_tool_a", "content": "ok"},
                # No final visible AI message in state snapshot.
            ]
        }
    }

    controller = ChatController(
        thread_controller=DummyThreadController(thread=thread, state=state),
        user_id="user-1",
    )

    result = await controller.get_chat_session("thread-5")
    packets = result["packets"]

    assert len(packets) == 1
    assert packets[0][0]["obj"]["type"] == "custom_tool_start"
    assert packets[0][1]["obj"]["type"] == "custom_tool_delta"

    # A `packets_2d` entry with no matching `messages` entry never renders —
    # the human message must not be the only turn the client can show.
    assert [m["message_type"] for m in result["messages"]] == ["user", "assistant"]

    # Without a trailing message_start/stop pair, the client has no signal
    # that this turn is finished and the timeline pacing never reveals
    # anything past the first step.
    assert [p["obj"]["type"] for p in packets[0][-2:]] == ["message_start", "stop"]


@pytest.mark.asyncio
async def test_get_chat_session_reconstructs_generated_file_packet_from_tool_message():
    payload = json.dumps(
        {
            "__generated_file__": True,
            "file_id": "abc123",
            "filename": "rapor.pdf",
            "mime_type": "application/pdf",
            "size_bytes": 42,
            "download_url": "/api/chat/file/abc123?download=1",
        }
    )
    thread = {
        "thread_id": "thread-6",
        "metadata": {"user_id": "user-1", "persona_id": 0, "name": "Chat"},
    }
    state = {
        "values": {
            "messages": [
                HumanMessage(content="Bana bir rapor hazırla"),
                AIMessage(
                    content="",
                    tool_calls=[{"name": "create_document", "args": {}, "id": "call-1"}],
                ),
                ToolMessage(content=payload, tool_call_id="call-1", name="create_document"),
                AIMessage(content="İşte dosyanız."),
            ]
        }
    }

    controller = ChatController(
        thread_controller=DummyThreadController(thread=thread, state=state),
        user_id="user-1",
    )

    result = await controller.get_chat_session("thread-6")
    all_packets = [packet for turn in result["packets"] for packet in turn]

    generated_file_packets = [p for p in all_packets if p["obj"]["type"] == "generated_file"]
    assert len(generated_file_packets) == 1
    assert generated_file_packets[0]["obj"]["file_id"] == "abc123"
    assert generated_file_packets[0]["obj"]["filename"] == "rapor.pdf"
    assert generated_file_packets[0]["obj"]["download_url"] == "/api/chat/file/abc123?download=1"

    # The file card represents the document on its own — the live stream
    # suppresses the generic tool step for document tools, so reconstruction
    # must not add one either.
    assert not any(
        p["obj"]["type"] == "custom_tool_start" and p["obj"].get("tool_name") == "create_document"
        for p in all_packets
    )


@pytest.mark.asyncio
async def test_get_chat_session_skips_generated_file_packet_for_plain_tool_result():
    thread = {
        "thread_id": "thread-7",
        "metadata": {"user_id": "user-1", "persona_id": 0, "name": "Chat"},
    }
    state = {
        "values": {
            "messages": [
                HumanMessage(content="2+2 kaç eder"),
                AIMessage(
                    content="",
                    tool_calls=[{"name": "Calculator", "args": {}, "id": "call-1"}],
                ),
                ToolMessage(content="4", tool_call_id="call-1", name="Calculator"),
                AIMessage(content="4 eder."),
            ]
        }
    }

    controller = ChatController(
        thread_controller=DummyThreadController(thread=thread, state=state),
        user_id="user-1",
    )

    result = await controller.get_chat_session("thread-7")
    all_packets = [packet for turn in result["packets"] for packet in turn]

    assert not any(p["obj"]["type"] == "generated_file" for p in all_packets)


@pytest.mark.asyncio
async def test_get_chat_session_keeps_text_written_before_a_tool_call():
    """A model often writes a sentence before calling its tools.

    That text streams live as part of the answer, so dropping it on reload
    made the conversation restart abruptly at the tool results.
    """
    thread = {
        "thread_id": "thread-preamble",
        "metadata": {"user_id": "user-1", "persona_id": 1, "name": "Chat"},
    }
    state = {
        "values": {
            "messages": [
                HumanMessage(content="arastir"),
                {
                    "type": "ai",
                    "content": "Simdi en onemli kaynaklari inceleyelim.",
                    "tool_calls": [{"name": "generic_tool_a", "args": {"query": "a"}, "id": "c1"}],
                },
                {"type": "tool", "name": "generic_tool_a", "content": "ok", "tool_call_id": "c1"},
                AIMessage(content="Sonuclari derledim."),
            ]
        }
    }

    controller = ChatController(
        thread_controller=DummyThreadController(thread=thread, state=state),
        user_id="user-1",
    )

    result = await controller.get_chat_session("thread-preamble")
    starts = [
        p["obj"].get("content") for p in result["packets"][0] if p["obj"]["type"] == "message_start"
    ]

    assert "Simdi en onemli kaynaklari inceleyelim." in starts
    assert "Sonuclari derledim." in starts


@pytest.mark.asyncio
async def test_get_chat_session_uses_per_message_persona_id_over_thread_metadata():
    """Retry can leave the thread's current persona different from the one
    that actually produced an earlier turn. Once a human message carries its
    own persona_id/model in additional_kwargs, that value — not the
    thread-level metadata.persona_id which only reflects the most recent
    send — must be reported for both that turn's messages."""
    thread = {
        "thread_id": "thread-persona",
        # Thread-level value has since moved on to persona 1 (e.g. user
        # switched agents after this turn was generated).
        "metadata": {"user_id": "user-1", "persona_id": 1, "name": "Chat"},
    }
    state = {
        "values": {
            "messages": [
                HumanMessage(
                    content="merhaba",
                    additional_kwargs={"persona_id": 7, "model": "gpt-4o"},
                ),
                AIMessage(content="selam"),
            ]
        }
    }

    controller = ChatController(
        thread_controller=DummyThreadController(thread=thread, state=state),
        user_id="user-1",
    )

    result = await controller.get_chat_session("thread-persona")
    human_msg, ai_msg = result["messages"]

    assert human_msg["alternate_assistant_id"] == 7
    assert human_msg["overridden_model"] == "gpt-4o"
    assert ai_msg["alternate_assistant_id"] == 7
    assert ai_msg["overridden_model"] == "gpt-4o"


@pytest.mark.asyncio
async def test_get_chat_session_falls_back_to_thread_metadata_persona_id_for_legacy_messages():
    """Messages persisted before per-message persona_id tracking existed
    have no persona_id in additional_kwargs — they must keep resolving from
    thread-level metadata so old conversations don't regress."""
    thread = {
        "thread_id": "thread-legacy",
        "metadata": {"user_id": "user-1", "persona_id": 3, "name": "Chat"},
    }
    state = {
        "values": {
            "messages": [
                HumanMessage(content="merhaba"),
                AIMessage(content="selam"),
            ]
        }
    }

    controller = ChatController(
        thread_controller=DummyThreadController(thread=thread, state=state),
        user_id="user-1",
    )

    result = await controller.get_chat_session("thread-legacy")
    human_msg, ai_msg = result["messages"]

    assert human_msg["alternate_assistant_id"] == 3
    assert ai_msg["alternate_assistant_id"] == 3


@pytest.mark.asyncio
async def test_get_chat_session_tracks_persona_id_per_turn_across_retries():
    """Each turn keeps reporting the persona/model that was active when it
    was generated, even after a later turn in the same thread switches to a
    different one (simulating a retry-with-different-model in model chat)."""
    thread = {
        "thread_id": "thread-multi-turn",
        "metadata": {"user_id": "user-1", "persona_id": 0, "name": "Chat"},
    }
    state = {
        "values": {
            "messages": [
                HumanMessage(
                    content="ilk soru",
                    additional_kwargs={"persona_id": 0, "model": "gpt-4o-mini"},
                ),
                AIMessage(content="ilk cevap"),
                HumanMessage(
                    content="ilk soru",  # retried with a different model
                    additional_kwargs={"persona_id": 0, "model": "gpt-4o"},
                ),
                AIMessage(content="ikinci cevap"),
            ]
        }
    }

    controller = ChatController(
        thread_controller=DummyThreadController(thread=thread, state=state),
        user_id="user-1",
    )

    result = await controller.get_chat_session("thread-multi-turn")
    msgs = result["messages"]

    assert [m["overridden_model"] for m in msgs] == [
        "gpt-4o-mini",
        "gpt-4o-mini",
        "gpt-4o",
        "gpt-4o",
    ]


@pytest.mark.asyncio
async def test_get_chat_session_treats_regenerated_response_as_a_sibling_not_a_new_turn():
    """A retry resends the user's message as a NEW HumanMessage in the flat
    checkpoint (LangGraph just appends), stamped with is_regenerate=True.
    On reload, that duplicate must not surface as its own chat bubble — the
    new AI response must become a sibling of the original response under
    the SAME original user message, exactly like the live in-session
    switcher already shows, instead of the conversation growing a
    duplicate user turn and losing the original response."""
    thread = {
        "thread_id": "thread-regen",
        "metadata": {"user_id": "user-1", "persona_id": 0, "name": "Chat"},
    }
    state = {
        "values": {
            "messages": [
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
            ]
        }
    }

    controller = ChatController(
        thread_controller=DummyThreadController(thread=thread, state=state),
        user_id="user-1",
    )

    result = await controller.get_chat_session("thread-regen")
    msgs = result["messages"]

    assert [m["message_type"] for m in msgs] == ["user", "assistant", "assistant"]
    assert [m["message"] for m in msgs] == ["soru", "cevap 1", "cevap 2"]

    user_msg, ai_msg_1, ai_msg_2 = msgs
    assert ai_msg_1["parent_message"] == user_msg["message_id"]
    assert ai_msg_2["parent_message"] == user_msg["message_id"]
    # The most recently generated alternate is the one shown by default.
    assert user_msg["latest_child_message"] == ai_msg_2["message_id"]
    # Each alternate still reports the model that actually produced it.
    assert ai_msg_1["overridden_model"] == "gpt-4o-mini"
    assert ai_msg_2["overridden_model"] == "gpt-4o"


@pytest.mark.asyncio
async def test_get_chat_session_supports_three_way_branching_from_repeated_retries():
    thread = {
        "thread_id": "thread-regen-3",
        "metadata": {"user_id": "user-1", "persona_id": 0, "name": "Chat"},
    }
    state = {
        "values": {
            "messages": [
                HumanMessage(content="soru"),
                AIMessage(content="cevap 1"),
                HumanMessage(content="soru", additional_kwargs={"is_regenerate": True}),
                AIMessage(content="cevap 2"),
                HumanMessage(content="soru", additional_kwargs={"is_regenerate": True}),
                AIMessage(content="cevap 3"),
            ]
        }
    }

    controller = ChatController(
        thread_controller=DummyThreadController(thread=thread, state=state),
        user_id="user-1",
    )

    result = await controller.get_chat_session("thread-regen-3")
    msgs = result["messages"]

    assert [m["message_type"] for m in msgs] == [
        "user",
        "assistant",
        "assistant",
        "assistant",
    ]
    user_msg, ai1, ai2, ai3 = msgs
    assert ai1["parent_message"] == user_msg["message_id"]
    assert ai2["parent_message"] == user_msg["message_id"]
    assert ai3["parent_message"] == user_msg["message_id"]
    assert user_msg["latest_child_message"] == ai3["message_id"]


@pytest.mark.asyncio
async def test_get_chat_session_still_builds_a_plain_chain_without_any_regenerate():
    """No is_regenerate markers at all (the common case) must produce the
    exact same strictly-linear chain as before — one child per message."""
    thread = {
        "thread_id": "thread-plain",
        "metadata": {"user_id": "user-1", "persona_id": 1, "name": "Chat"},
    }
    state = {
        "values": {
            "messages": [
                HumanMessage(content="merhaba"),
                AIMessage(content="selam"),
                HumanMessage(content="nasılsın"),
                AIMessage(content="iyiyim"),
            ]
        }
    }

    controller = ChatController(
        thread_controller=DummyThreadController(thread=thread, state=state),
        user_id="user-1",
    )

    result = await controller.get_chat_session("thread-plain")
    msgs = result["messages"]

    ids = [m["message_id"] for m in msgs]
    parents = [m["parent_message"] for m in msgs]
    latest_children = [m["latest_child_message"] for m in msgs]

    assert parents == [None, ids[0], ids[1], ids[2]]
    assert latest_children == [ids[1], ids[2], ids[3], None]


@pytest.mark.asyncio
async def test_get_chat_session_does_not_add_a_tool_step_for_document_tools():
    """A document tool is represented by its file card alone.

    The live stream suppresses the generic tool step for it, so emitting one
    here made a reloaded conversation grow a timeline entry the user never
    saw while it was streaming.
    """
    payload = json.dumps(
        {
            "__generated_file__": True,
            "file_id": "abc123",
            "filename": "rapor.pdf",
            "mime_type": "application/pdf",
            "size_bytes": 42,
            "download_url": "/api/chat/file/abc123?download=1",
        }
    )
    thread = {
        "thread_id": "thread-doc-step",
        "metadata": {"user_id": "user-1", "persona_id": 1, "name": "Chat"},
    }
    state = {
        "values": {
            "messages": [
                HumanMessage(content="rapor hazirla"),
                {
                    "type": "ai",
                    "content": "",
                    "tool_calls": [
                        {"name": "generic_tool_a", "args": {"query": "a"}, "id": "c1"},
                        {"name": "create_document", "args": {"filename": "r"}, "id": "c2"},
                    ],
                },
                {"type": "tool", "name": "generic_tool_a", "content": "ok", "tool_call_id": "c1"},
                {
                    "type": "tool",
                    "name": "create_document",
                    "content": payload,
                    "tool_call_id": "c2",
                },
                AIMessage(content="Hazir."),
            ]
        }
    }

    controller = ChatController(
        thread_controller=DummyThreadController(thread=thread, state=state),
        user_id="user-1",
    )

    result = await controller.get_chat_session("thread-doc-step")
    objs = [p["obj"] for grp in result["packets"] for p in grp]
    tool_steps = [o.get("tool_name") for o in objs if o["type"] == "custom_tool_start"]

    assert "create_document" not in tool_steps
    assert "generic_tool_a" in tool_steps
    # The document is still represented — by its file card.
    assert any(o["type"] == "generated_file" for o in objs)


@pytest.mark.asyncio
async def test_get_chat_session_keeps_a_retried_away_from_response_reachable_via_real_branching():
    """The whole point of true checkpoint branching (2026-08-21): a retry
    forks a new checkpoint chain rather than appending to the tip, so
    get_thread_state (single latest state) alone would only ever see the
    NEW branch. get_chat_session must instead walk the full checkpoint
    history and keep the original response reachable as a sibling."""
    thread = {
        "thread_id": "thread-real-fork",
        "metadata": {"user_id": "user-1", "persona_id": 0, "name": "Chat"},
    }
    human = HumanMessage(content="soru")
    checkpoints = [
        {"checkpoint_id": "root", "parent_checkpoint_id": None, "messages": [human]},
        {
            "checkpoint_id": "original",
            "parent_checkpoint_id": "root",
            "messages": [human, AIMessage(content="ilk cevap")],
        },
        {
            "checkpoint_id": "retry",
            "parent_checkpoint_id": "root",
            "messages": [human, AIMessage(content="retry cevabı")],
        },
    ]
    # get_thread_state (the fallback) would only ever see this — the most
    # recently written checkpoint — if the tree path weren't used.
    latest_state_only = {"values": {"messages": [human, AIMessage(content="retry cevabı")]}}

    controller = ChatController(
        thread_controller=DummyThreadControllerWithHistory(
            thread=thread, state=latest_state_only, checkpoints=checkpoints
        ),
        user_id="user-1",
    )

    result = await controller.get_chat_session("thread-real-fork")
    msgs = result["messages"]

    assert [m["message_type"] for m in msgs] == ["user", "assistant", "assistant"]
    user_msg, ai_a, ai_b = msgs
    assert {ai_a["message"], ai_b["message"]} == {"ilk cevap", "retry cevabı"}
    assert ai_a["parent_message"] == user_msg["message_id"]
    assert ai_b["parent_message"] == user_msg["message_id"]
    assert user_msg["latest_child_message"] == ai_b["message_id"]


@pytest.mark.asyncio
async def test_get_chat_session_still_supports_legacy_flat_is_regenerate_data_via_history_path():
    """Conversations retried under the OLD mechanism (a duplicate
    is_regenerate=True HumanMessage inline in one flat checkpoint, shipped
    2026-08-20) must keep reconstructing correctly even once
    get_thread_state_history is available — the tree walk degrades to the
    same single-checkpoint case reconstruct_messages already handled."""
    thread = {
        "thread_id": "thread-legacy-fork",
        "metadata": {"user_id": "user-1", "persona_id": 0, "name": "Chat"},
    }
    raw_messages = [
        HumanMessage(content="soru", additional_kwargs={"persona_id": 0}),
        AIMessage(content="cevap 1"),
        HumanMessage(
            content="soru",
            additional_kwargs={"persona_id": 0, "is_regenerate": True},
        ),
        AIMessage(content="cevap 2"),
    ]
    checkpoints = [
        {
            "checkpoint_id": "only",
            "parent_checkpoint_id": None,
            "messages": raw_messages,
        }
    ]

    controller = ChatController(
        thread_controller=DummyThreadControllerWithHistory(
            thread=thread,
            state={"values": {"messages": raw_messages}},
            checkpoints=checkpoints,
        ),
        user_id="user-1",
    )

    result = await controller.get_chat_session("thread-legacy-fork")
    msgs = result["messages"]

    assert [m["message_type"] for m in msgs] == ["user", "assistant", "assistant"]
    user_msg, ai1, ai2 = msgs
    assert ai1["parent_message"] == user_msg["message_id"]
    assert ai2["parent_message"] == user_msg["message_id"]
    assert user_msg["latest_child_message"] == ai2["message_id"]
