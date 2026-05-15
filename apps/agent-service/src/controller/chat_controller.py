"""Controller for chat session CRUD and metadata endpoints."""

import re
import uuid
from datetime import UTC, datetime
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from controller.base import BaseController
from controller.thread_controller import ThreadController, get_thread_controller
from core.llm import get_model
from service.CheckpointerService import get_checkpointer


class ChatController(BaseController):
    """Owns non-streaming chat endpoints and delegates persistence to ThreadController."""

    def __init__(self, thread_controller: ThreadController | None = None, user_id: str = "dev-user"):
        self._thread_controller = thread_controller or get_thread_controller()
        self._user_id = user_id

    async def _ensure_thread_belongs_to_user(self, thread_id: str, thread: dict[str, Any] | None) -> bool:
        if not thread:
            return False

        metadata = thread.get("metadata", {}) or {}
        owner = metadata.get("user_id")

        # Migration path for old records created before ownership was enforced.
        if not owner:
            metadata["user_id"] = self._user_id
            await self._thread_controller.update_thread(thread_id, metadata)
            return True

        return owner == self._user_id

    def _is_invalid_generated_title(self, title: str) -> bool:
        text = (title or "").strip().lower()
        if not text:
            return True

        invalid_markers = [
            "no llm models are currently available",
            "please ensure your llm provider",
            "check the admin panel",
            "no llm providers are configured",
            "model '",
            "not found",
        ]
        return any(marker in text for marker in invalid_markers)

    def _normalize_title(self, raw_title: str) -> str:
        title = (raw_title or "").strip()
        if not title:
            return ""

        # Keep only the first line and trim common wrappers like "Baslik:".
        title = title.splitlines()[0].strip()
        title = re.sub(r"^(baslik|başlık|title)\s*[:\-]\s*", "", title, flags=re.IGNORECASE)
        title = title.strip("\"'`“”‘’[](){}.,;:!? ")
        title = re.sub(r"\s+", " ", title).strip()
        return title[:80]

    def _detect_response_language(self, text: str) -> str:
        """Heuristic language detection for title generation prompting."""
        lowered = (text or "").lower()
        if not lowered.strip():
            return "same as input"

        # Quick Turkish signal via unique characters.
        if re.search(r"[çğıöşü]", lowered):
            return "Turkish"

        tokens = re.findall(r"[a-zA-Z]+", lowered)
        if not tokens:
            return "same as input"

        tr_markers = {
            "ve",
            "ile",
            "icin",
            "için",
            "bir",
            "bu",
            "gibi",
            "daha",
            "olarak",
            "ancak",
            "cunku",
            "çünkü",
            "sonra",
            "kadar",
        }
        en_markers = {
            "the",
            "and",
            "for",
            "with",
            "this",
            "that",
            "from",
            "into",
            "about",
            "before",
            "after",
        }

        tr_score = sum(1 for t in tokens if t in tr_markers)
        en_score = sum(1 for t in tokens if t in en_markers)

        if tr_score > en_score:
            return "Turkish"
        if en_score > tr_score:
            return "English"
        return "same as input"

    def _is_trivial_prefix_title(self, title: str, source_text: str) -> bool:
        """Reject titles that are just the opening words of the response."""
        title_words = re.findall(r"[A-Za-z0-9ÇĞİÖŞÜçğıöşü]+", title.lower())
        source_words = re.findall(r"[A-Za-z0-9ÇĞİÖŞÜçğıöşü]+", source_text.lower())
        if not title_words or len(source_words) < len(title_words):
            return False
        return source_words[: len(title_words)] == title_words

    def _heuristic_title_from_ai_response(self, ai_response: str) -> str:
        """Build a short summary-like title from assistant response text without using an LLM."""
        cleaned = re.sub(r"\s+", " ", (ai_response or "")).strip()
        if not cleaned:
            return ""

        words = re.findall(r"[A-Za-z0-9ÇĞİÖŞÜçğıöşü]+", cleaned)
        stopwords = {
            "ve",
            "veya",
            "ile",
            "için",
            "icin",
            "bu",
            "bir",
            "the",
            "and",
            "for",
            "that",
            "from",
            "your",
            "you",
            "olarak",
            "ancak",
            "çünkü",
            "sonuç",
            "buna",
            "göre",
            "daha",
            "gibi",
            "olur",
            "olacak",
            "yapmak",
            "yapabilir",
            "adım",
            "1",
            "2",
            "3",
        }

        # Score keywords by frequency and reward words that appear beyond the opening phrase.
        frequencies: dict[str, int] = {}
        first_seen: dict[str, int] = {}
        for idx, word in enumerate(words):
            lw = word.lower()
            if len(lw) <= 2 or lw in stopwords:
                continue
            frequencies[lw] = frequencies.get(lw, 0) + 1
            first_seen.setdefault(lw, idx)

        if not frequencies:
            return ""

        ranked = sorted(
            frequencies.keys(),
            key=lambda w: (
                frequencies[w],
                -first_seen[w],
            ),
            reverse=True,
        )

        selected = ranked[:4]
        title = " ".join(selected).strip().capitalize()
        if self._is_invalid_generated_title(title):
            return ""
        if self._is_trivial_prefix_title(title, ai_response):
            return ""
        return title[:80]

    async def _extract_first_ai_response(self, session_id: str) -> str:
        """Return the first assistant response text for the session, if present."""
        state = await self._thread_controller.get_thread_state(session_id)
        messages = state.get("values", {}).get("messages", [])

        for msg in messages:
            msg_type = getattr(msg, "type", None) or (msg.get("type", "") if isinstance(msg, dict) else "")
            if msg_type not in ("ai", "assistant"):
                continue

            content = getattr(msg, "content", "") if hasattr(msg, "content") else msg.get("content", "")
            if isinstance(content, list):
                parts: list[str] = []
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        text = item.get("text", "")
                        if text:
                            parts.append(str(text))
                    elif isinstance(item, str):
                        parts.append(item)
                content = " ".join(parts)

            if not isinstance(content, str):
                content = str(content or "")

            normalized = " ".join(content.strip().split())
            if normalized:
                return normalized

        return ""

    async def _generate_title_from_ai_response(self, ai_response: str) -> str:
        """Generate a concise session title (2-5 words) from the assistant response."""
        if not ai_response:
            return ""

        target_language = self._detect_response_language(ai_response)

        system_prompt = (
            "You generate chat titles. "
            "Return a concise 2-5 word title that summarizes the assistant response. "
            "Rules: return only the title, no explanation, no quotes, no trailing punctuation. "
            "Do not copy the opening words of the response verbatim. "
            f"Language requirement: the title must be in {target_language}."
        )
        user_prompt = f"Assistant response:\n{ai_response}"

        try:
            model = get_model()
            result = await model.ainvoke(
                [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=user_prompt),
                ]
            )
            content = getattr(result, "content", "")

            if isinstance(content, list):
                parts: list[str] = []
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        text = item.get("text", "")
                        if text:
                            parts.append(str(text))
                    elif isinstance(item, str):
                        parts.append(item)
                content = " ".join(parts)

            if not isinstance(content, str):
                content = str(content or "")

            normalized = self._normalize_title(content)
            if self._is_invalid_generated_title(normalized):
                return ""
            if self._is_trivial_prefix_title(normalized, ai_response):
                return ""
            return normalized[:80] if normalized else ""
        except Exception:
            return ""

    async def _derive_session_name(self, session_id: str, default_name: str = "New Chat") -> str:
        checkpointer = get_checkpointer()
        if not checkpointer:
            return default_name

        try:
            ai_response = await self._extract_first_ai_response(session_id)
            if ai_response:
                summary = await self._generate_title_from_ai_response(ai_response)
                if summary:
                    return summary

                fallback_summary = self._heuristic_title_from_ai_response(ai_response)
                if fallback_summary:
                    return fallback_summary

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
        if thread and not await self._ensure_thread_belongs_to_user(chat_session_id, thread):
            raise PermissionError("Forbidden")

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

        def _extract_reasoning_from_tags(text: str) -> str:
            if not text:
                return ""

            reasoning_parts: list[str] = []
            for open_tag, close_tag in (("<think>", "</think>"), ("<thinking>", "</thinking>")):
                start = 0
                while True:
                    open_pos = text.find(open_tag, start)
                    if open_pos == -1:
                        break

                    search_from = open_pos + len(open_tag)
                    close_pos = text.find(close_tag, search_from)
                    if close_pos == -1:
                        chunk = text[search_from:]
                        if chunk.strip():
                            reasoning_parts.append(chunk.strip())
                        break

                    chunk = text[search_from:close_pos]
                    if chunk.strip():
                        reasoning_parts.append(chunk.strip())
                    start = close_pos + len(close_tag)

            return "\n".join(reasoning_parts).strip()

        def _extract_visible_and_reasoning(msg: Any) -> tuple[str, str]:
            if hasattr(msg, "content"):
                content = msg.content
            elif isinstance(msg, dict):
                content = msg.get("content", "")
            else:
                return "", ""

            if isinstance(content, list):
                visible_parts: list[str] = []
                reasoning_parts: list[str] = []
                for item in content:
                    if isinstance(item, dict):
                        item_type = item.get("type")
                        if item_type == "thinking":
                            thinking_text = str(item.get("thinking", "") or "")
                            if thinking_text:
                                reasoning_parts.append(thinking_text)
                            continue

                        if item_type == "text":
                            text = str(item.get("text", "") or "")
                            if not text:
                                continue
                            if item.get("thought"):
                                reasoning_parts.append(text)
                            else:
                                visible_parts.append(text)
                            continue

                    if isinstance(item, str) and item:
                        visible_parts.append(item)

                visible_text = "".join(visible_parts).strip()
                reasoning_text = "\n".join(part for part in reasoning_parts if part).strip()
                return visible_text, reasoning_text

            text = _extract_content(msg)
            return _strip_think_tags(text), _extract_reasoning_from_tags(text)

        def _extract_reasoning_from_metadata(msg: Any) -> str:
            def _stringify(value: Any) -> str:
                if isinstance(value, str):
                    return value.strip()
                if isinstance(value, list):
                    parts: list[str] = []
                    for item in value:
                        if isinstance(item, str) and item:
                            parts.append(item)
                        elif isinstance(item, dict):
                            text = item.get("text") or item.get("reasoning") or item.get("thinking")
                            if isinstance(text, str) and text:
                                parts.append(text)
                    return "\n".join(parts).strip()
                return ""

            def _pick(payload: Any) -> str:
                if not isinstance(payload, dict):
                    return ""

                for key in (
                    "reasoning_content",
                    "reasoning",
                    "thinking",
                    "reasoning_text",
                    "thoughts",
                    "thought",
                    "chain_of_thought",
                ):
                    extracted = _stringify(payload.get(key))
                    if extracted:
                        return extracted

                nested_content = payload.get("content")
                if isinstance(nested_content, dict):
                    return _pick(nested_content)

                return ""

            if isinstance(msg, dict):
                additional_kwargs = msg.get("additional_kwargs", {}) or {}
                response_metadata = msg.get("response_metadata", {}) or {}
            else:
                additional_kwargs = getattr(msg, "additional_kwargs", {}) or {}
                response_metadata = getattr(msg, "response_metadata", {}) or {}

            return _pick(additional_kwargs) or _pick(response_metadata)

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
                    msg_content, reasoning_text = _extract_visible_and_reasoning(raw_msg)
                    if not reasoning_text:
                        reasoning_text = _extract_reasoning_from_metadata(raw_msg)

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

                    # Reconstruct LTM recall packet from metadata stored on the AI message
                    _extra = raw_msg.get("additional_kwargs", {}) or {} if isinstance(raw_msg, dict) else getattr(raw_msg, "additional_kwargs", {}) or {}
                    ltm_recalled = _extra.get("_ltm_recalled", 0)
                    if ltm_recalled:
                        turn_packets.append(
                            {
                                "placement": {"turn_index": 0, "sub_turn_index": None},
                                "obj": {
                                    "type": "long_term_memory_recall",
                                    "fact_count": ltm_recalled,
                                    "memories": [],
                                },
                            }
                        )

                    if reasoning_text:
                        turn_packets.append(
                            {
                                "placement": {"turn_index": 0, "sub_turn_index": None},
                                "obj": {"type": "reasoning_start"},
                            }
                        )
                        turn_packets.append(
                            {
                                "placement": {"turn_index": 0, "sub_turn_index": None},
                                "obj": {
                                    "type": "reasoning_delta",
                                    "reasoning": reasoning_text,
                                },
                            }
                        )

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
        thread = await self._thread_controller.get_thread(chat_session_id)
        if thread and not await self._ensure_thread_belongs_to_user(chat_session_id, thread):
            return {"success": False, "error": "Forbidden"}

        await self._thread_controller.delete_thread(chat_session_id)
        return {"success": True}

    async def delete_all_chat_sessions(self) -> dict[str, Any]:
        threads = await self._thread_controller.list_threads(
            limit=1000,
            offset=0,
            metadata={"user_id": self._user_id},
        )
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
        if not await self._ensure_thread_belongs_to_user(session_id, thread):
            return {"success": False, "error": "Forbidden"}

        metadata = thread.get("metadata", {}) or {}
        trimmed_name = name.strip() if isinstance(name, str) else None
        metadata["name"] = (
            trimmed_name
            if trimmed_name
            else await self._derive_session_name(session_id, default_name=metadata.get("name", "New Chat") or "New Chat")
        )
        await self._thread_controller.update_thread(session_id, metadata, update_timestamp=False)
        return {"success": True}

    async def update_chat_session_model(self, session_id: str | None, model: str | None) -> dict[str, Any]:
        if not session_id:
            return {"success": False, "error": "Missing session_id"}

        thread = await self._thread_controller.get_thread(session_id)
        if thread and await self._ensure_thread_belongs_to_user(session_id, thread):
            metadata = thread.get("metadata", {}) or {}
            metadata["current_alternate_model"] = model
            await self._thread_controller.update_thread(session_id, metadata)
        elif thread:
            return {"success": False, "error": "Forbidden"}
        return {"success": True}

    async def update_chat_session_temperature(
        self,
        session_id: str | None,
        temperature: float | None,
    ) -> dict[str, Any]:
        if not session_id:
            return {"success": False, "error": "Missing session_id"}

        thread = await self._thread_controller.get_thread(session_id)
        if thread and await self._ensure_thread_belongs_to_user(session_id, thread):
            metadata = thread.get("metadata", {}) or {}
            metadata["current_temperature_override"] = temperature
            await self._thread_controller.update_thread(session_id, metadata)
        elif thread:
            return {"success": False, "error": "Forbidden"}
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
        if thread and not await self._ensure_thread_belongs_to_user(session_id, thread):
            return []

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
