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
                    "tool_calls": [{"name": "web_search"}],
                },
                {
                    "type": "tool",
                    "name": "web_search",
                    "content": "search results",
                },
                {
                    "type": "ai",
                    "content": "",
                    "tool_calls": [{"name": "fetch_webpage"}],
                },
                {
                    "type": "tool",
                    "name": "fetch_webpage",
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

    assert tool_names == ["web_search", "web_search", "fetch_webpage", "fetch_webpage"]
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
                        {"name": "web_search", "args": {"query": "a"}, "id": "call-a"},
                        {"name": "web_search", "args": {"query": "b"}, "id": "call-b"},
                        {"name": "fetch_webpage", "args": {"url": "c"}, "id": "call-c"},
                    ],
                },
                # Results arrive out of order and interleaved with each other.
                {"type": "tool", "name": "fetch_webpage", "content": "result c", "tool_call_id": "call-c"},
                {"type": "tool", "name": "web_search", "content": "result b", "tool_call_id": "call-b"},
                {"type": "tool", "name": "web_search", "content": "result a", "tool_call_id": "call-a"},
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
                {"type": "ai", "content": "", "tool_calls": [{"name": "web_search"}]},
                {"type": "tool", "name": "web_search", "content": "ok"},
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

    # Document tools emit tool step packets so they register in the timeline.
    assert any(
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
                    "tool_calls": [
                        {"name": "web_search", "args": {"query": "a"}, "id": "c1"}
                    ],
                },
                {"type": "tool", "name": "web_search", "content": "ok", "tool_call_id": "c1"},
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
        p["obj"].get("content")
        for p in result["packets"][0]
        if p["obj"]["type"] == "message_start"
    ]

    assert "Simdi en onemli kaynaklari inceleyelim." in starts
    assert "Sonuclari derledim." in starts
