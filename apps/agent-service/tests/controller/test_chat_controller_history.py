"""Tests for chat history reconstruction in ChatController."""

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

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
