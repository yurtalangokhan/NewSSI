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

    async def _derive_session_name(self, session_id: str, default_name: str = "New Chat") -> str:
        checkpointer = get_checkpointer()
        if not checkpointer:
            return default_name

        try:
            state = await self._thread_controller.get_thread_state(session_id)
            messages = state.get("values", {}).get("messages", [])
            for msg in messages:
                msg_type = getattr(msg, "type", None) or (msg.get("type", "") if isinstance(msg, dict) else "")
                if msg_type not in ("human", "user"):
                    continue

                content = getattr(msg, "content", "") if hasattr(msg, "content") else msg.get("content", "")
                if isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict) and item.get("type") == "text":
                            content = item.get("text", "")
                            break
                        if isinstance(item, str):
                            content = item
                            break
                if not isinstance(content, str):
                    content = str(content or "")

                content = " ".join(content.strip().split())
                if content:
                    return content[:50]
        except Exception:
            return default_name

        return default_name

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

    async def create_chat_session(
        self,
        persona_id: Any = 0,
        description: str | None = None,
    ) -> dict[str, Any]:
        thread_id = str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()
        name = (description or "").strip() or "New Chat"

        thread = await self._thread_controller.create_thread(
            thread_id=thread_id,
            metadata={
                "user_id": self._user_id,
                "name": name,
                "persona_id": persona_id,
            },
        )

        return {
            "id": thread["thread_id"],
            "name": thread.get("metadata", {}).get("name", name),
            "description": thread.get("metadata", {}).get("name", name),
            "persona_id": thread.get("metadata", {}).get("persona_id", persona_id),
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
                "persona_name": "",
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
        messages: list[dict[str, Any]] = []
        packets_2d: list[list[dict[str, Any]]] = []

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

        try:
            state = await self._thread_controller.get_thread_state(chat_session_id)
            langgraph_messages = state.get("values", {}).get("messages", [])
            pending_tool_packets: list[dict[str, Any]] = []
            msg_idx = 0

            for raw_msg in langgraph_messages:
                raw_type = getattr(raw_msg, "type", None)
                if raw_type is None and isinstance(raw_msg, dict):
                    raw_type = raw_msg.get("type", "")

                if raw_type == "tool":
                    tool_name = (
                        getattr(raw_msg, "name", None)
                        or (raw_msg.get("name", "") if isinstance(raw_msg, dict) else "")
                        or "tool"
                    )
                    tool_content = _extract_content(raw_msg)
                    pending_tool_packets.append(
                        {
                            "placement": {"turn_index": 0, "sub_turn_index": None},
                            "obj": {
                                "type": "custom_tool_delta",
                                "tool_name": tool_name,
                                "response_type": "tool_result",
                                "data": tool_content,
                            },
                        }
                    )
                    continue

                if raw_type == "ai":
                    tool_calls = (
                        getattr(raw_msg, "tool_calls", None)
                        or (raw_msg.get("tool_calls", []) if isinstance(raw_msg, dict) else [])
                    )
                    msg_content = _strip_think_tags(_extract_content(raw_msg))

                    if tool_calls:
                        for tool_call in tool_calls:
                            tool_name = (
                                tool_call.get("name", "tool")
                                if isinstance(tool_call, dict)
                                else getattr(tool_call, "name", "tool")
                            )
                            pending_tool_packets.append(
                                {
                                    "placement": {"turn_index": 0, "sub_turn_index": None},
                                    "obj": {
                                        "type": "custom_tool_start",
                                        "tool_name": tool_name,
                                    },
                                }
                            )
                        continue

                    if not msg_content:
                        continue

                    parent_msg_id = msg_idx if msg_idx > 0 else None
                    msg_idx += 1

                    turn_packets: list[dict[str, Any]] = []
                    if pending_tool_packets:
                        turn_packets.extend(pending_tool_packets)
                        pending_tool_packets = []

                    display_turn = 1 if turn_packets else 0
                    turn_packets.append(
                        {
                            "placement": {"turn_index": display_turn, "sub_turn_index": None},
                            "obj": {
                                "type": "message_start",
                                "content": msg_content,
                                "final_documents": None,
                            },
                        }
                    )
                    turn_packets.append(
                        {
                            "placement": {"turn_index": display_turn, "sub_turn_index": None},
                            "obj": {
                                "type": "stop",
                                "stop_reason": "finished",
                            },
                        }
                    )
                    packets_2d.append(turn_packets)

                    messages.append(
                        {
                            "message_id": msg_idx,
                            "message_type": "assistant",
                            "research_type": None,
                            "parent_message": parent_msg_id,
                            "latest_child_message": None,
                            "message": msg_content,
                            "rephrased_query": None,
                            "context_docs": None,
                            "time_sent": None,
                            "overridden_model": None,
                            "alternate_assistant_id": metadata.get("persona_id"),
                            "chat_session_id": chat_session_id,
                            "citations": None,
                            "files": [],
                            "tool_call": None,
                            "current_feedback": None,
                            "processing_duration_seconds": None,
                            "sub_questions": [],
                            "comments": None,
                            "parentMessageId": parent_msg_id,
                            "refined_answer_improvement": None,
                            "is_agentic": None,
                        }
                    )
                    continue

                msg_content = _strip_think_tags(_extract_content(raw_msg))
                parent_msg_id = msg_idx if msg_idx > 0 else None
                msg_idx += 1

                # Restore file badges from additional_kwargs set at send time.
                # raw_msg may be a LangChain object or a plain dict depending
                # on checkpointer deserialization.
                if isinstance(raw_msg, dict):
                    _extra = raw_msg.get("additional_kwargs", {}) or {}
                else:
                    _extra = getattr(raw_msg, "additional_kwargs", {}) or {}
                raw_files_meta = _extra.get("files_metadata", [])
                history_files = [
                    {
                        "id": f.get("id", ""),
                        "type": f.get("type", "document"),
                        "name": f.get("name"),
                    }
                    for f in (raw_files_meta or [])
                    if isinstance(f, dict) and f.get("id")
                ]

                messages.append(
                    {
                        "message_id": msg_idx,
                        "message_type": "user",
                        "research_type": None,
                        "parent_message": parent_msg_id,
                        "latest_child_message": None,
                        "message": msg_content,
                        "rephrased_query": None,
                        "context_docs": None,
                        "time_sent": None,
                        "overridden_model": None,
                        "alternate_assistant_id": metadata.get("persona_id"),
                        "chat_session_id": chat_session_id,
                        "citations": None,
                        "files": history_files,
                        "tool_call": None,
                        "current_feedback": None,
                        "processing_duration_seconds": None,
                        "sub_questions": [],
                        "comments": None,
                        "parentMessageId": parent_msg_id,
                        "refined_answer_improvement": None,
                        "is_agentic": None,
                    }
                )

            for index in range(len(messages) - 1):
                messages[index]["latest_child_message"] = messages[index + 1]["message_id"]
        except Exception:
            import logging as _logging
            import traceback as _traceback
            _logging.getLogger(__name__).error(
                "Failed to load chat history for session %s:\n%s",
                chat_session_id,
                _traceback.format_exc(),
            )
            messages = []
            packets_2d = []

        return {
            "chat_session_id": chat_session_id,
            "description": metadata.get("name", "New Chat"),
            "persona_id": metadata.get("persona_id", 0),
            "persona_name": "",
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
        trimmed_name = name.strip() if isinstance(name, str) else None
        metadata["name"] = (
            trimmed_name
            if trimmed_name
            else await self._derive_session_name(session_id, default_name=metadata.get("name", "New Chat") or "New Chat")
        )
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
        # Session files are inline attachments in this backend variant.
        # Keep response shape compatible with frontend expectations.
        _ = session_id
        return {"token_count": 0, "total_tokens": 0}

    async def get_session_files(self, session_id: str) -> list[dict[str, Any]]:
        thread = await self._thread_controller.get_thread(session_id)
        if not thread:
            return []

        files: list[dict[str, Any]] = []
        seen_ids: set[str] = set()

        try:
            state = await self._thread_controller.get_thread_state(session_id)
            langgraph_messages = state.get("values", {}).get("messages", [])

            for raw_msg in langgraph_messages:
                raw_type = getattr(raw_msg, "type", None)
                if raw_type is None and isinstance(raw_msg, dict):
                    raw_type = raw_msg.get("type", "")

                if raw_type not in ("human", "user"):
                    continue

                if isinstance(raw_msg, dict):
                    _extra = raw_msg.get("additional_kwargs", {}) or {}
                else:
                    _extra = getattr(raw_msg, "additional_kwargs", {}) or {}

                raw_files_meta = _extra.get("files_metadata", [])
                for f in raw_files_meta or []:
                    if not isinstance(f, dict):
                        continue
                    file_id = f.get("id")
                    if not file_id or file_id in seen_ids:
                        continue
                    seen_ids.add(file_id)

                    chat_file_type = f.get("type", "document")
                    if chat_file_type == "image":
                        file_type = "image/png"
                    elif chat_file_type == "csv":
                        file_type = "text/csv"
                    elif chat_file_type == "plain_text":
                        file_type = "text/plain"
                    else:
                        file_type = "application/octet-stream"

                    files.append(
                        {
                            "id": file_id,
                            "name": f.get("name") or file_id,
                            "project_id": None,
                            "user_id": self._user_id,
                            "file_id": file_id,
                            "created_at": thread.get("created_at"),
                            "status": "COMPLETED",
                            "file_type": file_type,
                            "last_accessed_at": thread.get("updated_at"),
                            "chat_file_type": chat_file_type,
                            "token_count": None,
                            "chunk_count": None,
                            "temp_id": None,
                        }
                    )
        except Exception:
            return []

        return files

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
