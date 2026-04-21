"""Controller for chat session CRUD and metadata endpoints."""

import re
import uuid
from datetime import UTC, datetime
from typing import Any

from controller.base import BaseController
from controller.thread_controller import ThreadController, get_thread_controller
from service.CheckpointerService import get_checkpointer


class ChatController(BaseController):
    """Owns non-streaming chat endpoints and delegates persistence to ThreadController."""

    def __init__(self, thread_controller: ThreadController | None = None, user_id: str = "dev-user"):
        self._thread_controller = thread_controller or get_thread_controller()
        self._user_id = user_id

    async def get_chat_sessions(self) -> dict[str, Any]:
        threads = await self._thread_controller.list_threads(
            limit=100,
            offset=0,
            metadata={"user_id": self._user_id},
        )

        checkpointer = get_checkpointer()
        sessions: list[dict[str, Any]] = []

        for thread in threads:
            thread_id = thread.get("thread_id", "")
            metadata = thread.get("metadata", {}) or {}
            session_name = metadata.get("name", "New Chat")

            if session_name == "New Chat" and checkpointer and thread_id:
                try:
                    state = await self._thread_controller.get_thread_state(thread_id)
                    messages = state.get("values", {}).get("messages", [])
                    for msg in messages:
                        msg_type = getattr(msg, "type", None) or msg.get("type", "")
                        if msg_type in ("human", "user"):
                            content = getattr(msg, "content", "") or msg.get("content", "")
                            if isinstance(content, str) and content:
                                session_name = content[:50]
                                break
                except Exception:
                    pass

            sessions.append(
                {
                    "id": thread_id,
                    "name": session_name or "New Chat",
                    "description": session_name or "New Chat",
                    "persona_id": metadata.get("persona_id", 0),
                    "time_created": thread.get("created_at"),
                    "time_updated": thread.get("updated_at"),
                    "shared_status": "private",
                    "current_alternate_model": metadata.get("current_alternate_model"),
                    "current_temperature_override": metadata.get("current_temperature_override"),
                }
            )

        sessions.sort(key=lambda s: s.get("time_updated") or "", reverse=True)
        return {"sessions": sessions, "chat_sessions": sessions, "has_more": False}

    async def create_chat_session(self) -> dict[str, Any]:
        thread_id = str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()

        thread = await self._thread_controller.create_thread(
            thread_id=thread_id,
            metadata={
                "user_id": self._user_id,
                "name": "New Chat",
                "persona_id": 0,
            },
        )

        return {
            "id": thread["thread_id"],
            "name": thread.get("metadata", {}).get("name", "New Chat"),
            "description": thread.get("metadata", {}).get("name", "New Chat"),
            "persona_id": thread.get("metadata", {}).get("persona_id", 0),
            "time_created": thread.get("created_at", now),
            "time_updated": thread.get("updated_at", now),
            "shared_status": "private",
            "current_alternate_model": None,
            "current_temperature_override": None,
        }

    async def get_chat_session(self, chat_session_id: str) -> dict[str, Any]:
        thread = await self._thread_controller.get_thread(chat_session_id)
        if not thread:
            return {
                "chat_session_id": chat_session_id,
                "description": "Chat",
                "persona_id": 0,
                "messages": [],
                "time_created": None,
                "time_updated": None,
                "shared_status": "private",
                "current_temperature_override": None,
                "current_alternate_model": None,
                "owner_name": None,
                "packets": [],
            }

        metadata = thread.get("metadata", {}) or {}
        state = await self._thread_controller.get_thread_state(chat_session_id)
        langgraph_messages = state.get("values", {}).get("messages", [])

        def _strip_think_tags(text: str) -> str:
            if not text:
                return text
            result = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
            result = re.sub(r"<thinking>.*?</thinking>", "", result, flags=re.DOTALL)
            result = re.sub(r"<think>(?:(?!</think>).)*$", "", result, flags=re.DOTALL)
            result = re.sub(r"<thinking>(?:(?!</thinking>).)*$", "", result, flags=re.DOTALL)
            return result.strip()

        def _extract_content(msg: Any) -> str:
            if hasattr(msg, "content"):
                content = msg.content
            elif isinstance(msg, dict):
                content = msg.get("content", "")
            else:
                return ""
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        return item.get("text", "")
                    if isinstance(item, str):
                        return item
            if isinstance(content, dict):
                return content.get("text", "") or str(content)
            return ""

        messages: list[dict[str, Any]] = []
        packets_2d: list[list[dict[str, Any]]] = []
        msg_idx = 0

        for raw_msg in langgraph_messages:
            raw_type = getattr(raw_msg, "type", None)
            if raw_type is None and isinstance(raw_msg, dict):
                raw_type = raw_msg.get("type", "")

            if raw_type == "tool":
                continue

            msg_content = _strip_think_tags(_extract_content(raw_msg))
            if raw_type == "ai" and not msg_content:
                continue

            parent_msg_id = msg_idx if msg_idx > 0 else None
            msg_idx += 1

            messages.append(
                {
                    "message_id": msg_idx,
                    "message_type": "assistant" if raw_type == "ai" else "user",
                    "message": msg_content,
                    "parentMessageId": parent_msg_id,
                    "chat_session_id": chat_session_id,
                }
            )

        for i in range(len(messages) - 1):
            messages[i]["latest_child_message"] = messages[i + 1]["message_id"]

        return {
            "chat_session_id": chat_session_id,
            "description": metadata.get("name", "New Chat"),
            "persona_id": metadata.get("persona_id", 0),
            "messages": messages,
            "time_created": thread.get("created_at"),
            "time_updated": thread.get("updated_at"),
            "shared_status": "private",
            "current_temperature_override": metadata.get("current_temperature_override"),
            "current_alternate_model": metadata.get("current_alternate_model"),
            "owner_name": None,
            "packets": packets_2d,
        }

    async def delete_chat_session(self, chat_session_id: str) -> dict[str, Any]:
        await self._thread_controller.delete_thread(chat_session_id)
        return {"success": True}

    async def delete_all_chat_sessions(self) -> dict[str, Any]:
        threads = await self._thread_controller.list_threads(limit=1000, offset=0)
        deleted_count = 0

        for thread in threads:
            thread_id = thread.get("thread_id")
            if not thread_id:
                continue
            await self._thread_controller.delete_thread(thread_id)
            deleted_count += 1

        return {"success": True, "deleted_count": deleted_count}

    async def rename_chat_session(self, session_id: str | None, name: str | None) -> dict[str, Any]:
        if not session_id:
            return {"success": False, "error": "Missing session_id"}

        thread = await self._thread_controller.get_thread(session_id)
        if not thread:
            return {"success": False, "error": "Session not found"}

        metadata = thread.get("metadata", {}) or {}
        metadata["name"] = name or "New Chat"
        await self._thread_controller.update_thread(session_id, metadata)
        return {"success": True}

    async def update_chat_session_model(self, session_id: str | None, model: str | None) -> dict[str, Any]:
        if not session_id:
            return {"success": False, "error": "Missing session_id"}

        thread = await self._thread_controller.get_thread(session_id)
        if thread:
            metadata = thread.get("metadata", {}) or {}
            metadata["current_alternate_model"] = model
            await self._thread_controller.update_thread(session_id, metadata)
        return {"success": True}

    async def update_chat_session_temperature(
        self,
        session_id: str | None,
        temperature: float | None,
    ) -> dict[str, Any]:
        if not session_id:
            return {"success": False, "error": "Missing session_id"}

        thread = await self._thread_controller.get_thread(session_id)
        if thread:
            metadata = thread.get("metadata", {}) or {}
            metadata["current_temperature_override"] = temperature
            await self._thread_controller.update_thread(session_id, metadata)
        return {"success": True}

    async def stop_chat_session(self, chat_session_id: str) -> dict[str, Any]:
        _ = chat_session_id
        return {"success": True}

    async def set_message_as_latest(self) -> dict[str, Any]:
        return {"success": True}

    async def get_available_context_tokens(self, session_id: str | None = None) -> dict[str, int]:
        _ = session_id
        return {"max_tokens": 120000, "selected_tokens": 120000}

    async def get_session_token_count(self, session_id: str) -> dict[str, int]:
        _ = session_id
        return {"token_count": 0}

    async def get_session_files(self, session_id: str) -> dict[str, list[Any]]:
        _ = session_id
        return {"files": []}

    async def create_chat_message_feedback(self) -> dict[str, bool]:
        return {"success": True}

    async def remove_chat_message_feedback(self) -> dict[str, bool]:
        return {"success": True}


_chat_controller: ChatController | None = None


def get_chat_controller() -> ChatController:
    """Get singleton ChatController."""
    global _chat_controller
    if _chat_controller is None:
        _chat_controller = ChatController()
    return _chat_controller
