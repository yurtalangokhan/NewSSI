"""Controller for chat session CRUD and metadata endpoints."""

import logging
import re
import uuid
from datetime import UTC, datetime
from typing import Any

from i18n import t
from langchain_core.messages import HumanMessage, SystemMessage

from controller.base import BaseController
from controller.thread_controller import ThreadController, get_thread_controller
from core.llm import get_model
from service.CheckpointerService import get_checkpointer
from service.DocumentProgressTracker import is_document_tool
from service.GeneratedFilePacket import (
    build_generated_file_packet_obj,
    parse_generated_file_payload,
)

logger = logging.getLogger(__name__)


class ChatController(BaseController):
    """Owns non-streaming chat endpoints and delegates persistence to ThreadController."""

    def __init__(
        self,
        thread_controller: ThreadController | None = None,
        user_id: str = "dev-user",
        owner_ids: list[str] | None = None,
    ):
        self._thread_controller = thread_controller or get_thread_controller()
        self._user_id = user_id
        self._owner_ids: list[str] = []
        for candidate in [user_id, *(owner_ids or [])]:
            normalized = str(candidate).strip() if candidate else ""
            if normalized and normalized not in self._owner_ids:
                self._owner_ids.append(normalized)

    @staticmethod
    def _thread_project_id(thread: dict[str, Any]) -> int | None:
        project_id = thread.get("project_id")
        if project_id is None:
            metadata = thread.get("metadata", {}) or {}
            project_id = metadata.get("project_id")
        if project_id is None:
            return None
        try:
            return int(project_id)
        except (TypeError, ValueError):
            return None

    def _matches_owner(self, metadata: dict[str, Any]) -> bool:
        owner = metadata.get("user_id")
        if owner and str(owner) in self._owner_ids:
            return True

        legacy_owner_ids = metadata.get("legacy_user_ids") or []
        if isinstance(legacy_owner_ids, list):
            return any(str(candidate) in self._owner_ids for candidate in legacy_owner_ids)

        return False

    async def _list_user_threads(self, limit: int, offset: int) -> list[dict[str, Any]]:
        if len(self._owner_ids) <= 1:
            return await self._thread_controller.list_threads(
                limit=limit,
                offset=offset,
                metadata={"user_id": self._user_id},
            )

        threads = await self._thread_controller.list_threads(
            limit=max(limit + offset, 1000),
            offset=0,
        )
        matching_threads = [
            thread for thread in threads if self._matches_owner(thread.get("metadata", {}) or {})
        ]
        return matching_threads[offset : offset + limit]

    @staticmethod
    def _activity_time(thread: dict[str, Any]) -> str:
        """Return the backward-compatible activity timestamp for a thread or session."""
        created_at = thread.get("created_at") or thread.get("time_created") or ""
        updated_at = thread.get("updated_at") or thread.get("time_updated") or ""
        if "last_message_at" in thread:
            return thread.get("last_message_at") or created_at
        return updated_at or created_at

    async def _list_user_threads_by_activity(
        self,
        page_size: int,
        before_activity: str | None,
        before_id: str | None,
    ) -> list[dict[str, Any]]:
        if len(self._owner_ids) <= 1:
            return await self._thread_controller.list_chat_sessions_by_activity(
                page_size=page_size,
                before_activity=before_activity,
                before_id=before_id,
                metadata={"user_id": self._user_id},
            )

        matching_threads: list[dict[str, Any]] = []
        cursor_activity = before_activity
        cursor_id = before_id
        batch_size = max(page_size, 100)

        while len(matching_threads) < page_size:
            batch = await self._thread_controller.list_chat_sessions_by_activity(
                page_size=batch_size,
                before_activity=cursor_activity,
                before_id=cursor_id,
            )
            if not batch:
                break

            for thread in batch:
                if self._matches_owner(thread.get("metadata", {}) or {}):
                    matching_threads.append(thread)
                    if len(matching_threads) >= page_size:
                        break

            if len(batch) < batch_size:
                break

            last_thread = batch[-1]
            cursor_activity = self._activity_time(last_thread)
            cursor_id = last_thread.get("thread_id") or ""
            if not cursor_activity or not cursor_id:
                break

        return matching_threads

    async def _ensure_thread_belongs_to_user(
        self, thread_id: str, thread: dict[str, Any] | None
    ) -> bool:
        if not thread:
            return False

        metadata = thread.get("metadata", {}) or {}
        owner = metadata.get("user_id")

        # Migration path for old records created before ownership was enforced.
        if not owner:
            metadata["user_id"] = self._user_id
            await self._thread_controller.update_thread(thread_id, metadata, update_timestamp=False)
            return True

        if str(owner) == self._user_id:
            return True

        if self._matches_owner(metadata):
            legacy_owner_ids = metadata.get("legacy_user_ids") or []
            if not isinstance(legacy_owner_ids, list):
                legacy_owner_ids = []
            if str(owner) != self._user_id and str(owner) not in legacy_owner_ids:
                legacy_owner_ids.append(str(owner))

            metadata["legacy_user_ids"] = legacy_owner_ids
            metadata["user_id"] = self._user_id
            await self._thread_controller.update_thread(thread_id, metadata, update_timestamp=False)
            return True

        return False

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

    async def _extract_first_human_message(self, session_id: str) -> str:
        """Return the first human message text for the session, if present."""
        state = await self._thread_controller.get_thread_state(session_id)
        messages = state.get("values", {}).get("messages", [])

        for msg in messages:
            msg_type = getattr(msg, "type", None) or (
                msg.get("type", "") if isinstance(msg, dict) else ""
            )
            if msg_type not in ("human", "user"):
                continue

            content = (
                getattr(msg, "content", "") if hasattr(msg, "content") else msg.get("content", "")
            )
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

    async def _generate_title_from_question(
        self,
        human_message: str,
        model_name: str | None = None,
    ) -> str:
        """Generate a concise session title (3-6 words) from the user's question."""
        if not human_message:
            return ""

        target_language = self._detect_response_language(human_message)

        system_prompt = (
            "You generate short chat session titles. "
            "Given the user's first message, return a concise title of 3 to 6 words that captures the main topic or intent. "
            "Rules: return ONLY the title — no explanation, no quotes, no punctuation at the end. "
            "Do not copy the message verbatim; summarize its core topic. "
            f"Write the title in {target_language}."
        )
        user_prompt = f"User message:\n{human_message[:500]}"

        try:
            model = get_model(model_name)
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
            return normalized[:80] if normalized else ""
        except Exception:
            return ""

    async def _derive_session_name(
        self,
        session_id: str,
        default_name: str = "New Chat",
        model_name: str | None = None,
    ) -> str:
        checkpointer = get_checkpointer()
        if not checkpointer:
            return default_name

        try:
            human_message = await self._extract_first_human_message(session_id)
            if human_message:
                title = await self._generate_title_from_question(
                    human_message, model_name=model_name
                )
                if title:
                    return title

                # Fallback: clean truncation of the question (readable, no word-splitting)
                words = human_message.split()
                fallback = " ".join(words[:8])
                if len(words) > 8:
                    fallback += "…"
                return fallback[:80] if fallback else default_name
        except Exception:
            return default_name

        return default_name

    async def get_chat_sessions(
        self,
        page_size: int = 100,
        before_activity: str | None = None,
        before_id: str | None = None,
    ) -> dict[str, Any]:
        page_size = max(1, min(page_size, 100))
        threads = await self._list_user_threads_by_activity(
            page_size=page_size + 1,
            before_activity=before_activity,
            before_id=before_id,
        )
        threads.sort(
            key=lambda thread: (self._activity_time(thread), thread.get("thread_id") or ""),
            reverse=True,
        )
        has_more = len(threads) > page_size
        threads = threads[:page_size]

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
                    "last_message_at": thread.get("last_message_at"),
                    "last_accessed_at": thread.get("last_accessed_at"),
                    "shared_status": "private",
                    "project_id": self._thread_project_id(thread),
                    "current_alternate_model": metadata.get("current_alternate_model"),
                    "current_temperature_override": metadata.get("current_temperature_override"),
                }
            )

        next_cursor = None
        if has_more and threads:
            last_thread = threads[-1]
            next_cursor = {
                "before_activity": self._activity_time(last_thread),
                "before_id": last_thread["thread_id"],
            }
        return {
            "sessions": sessions,
            "chat_sessions": sessions,
            "has_more": has_more,
            "next_cursor": next_cursor,
        }

    async def create_chat_session(
        self,
        persona_id: Any = 0,
        description: str | None = None,
        project_id: int | None = None,
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
                "project_id": project_id,
            },
        )

        return {
            "id": thread["thread_id"],
            "name": thread.get("metadata", {}).get("name", name),
            "description": thread.get("metadata", {}).get("name", name),
            "persona_id": thread.get("metadata", {}).get("persona_id", persona_id),
            "time_created": thread.get("created_at", now),
            "time_updated": thread.get("updated_at", now),
            "last_message_at": thread.get("last_message_at"),
            "last_accessed_at": thread.get("last_accessed_at"),
            "shared_status": "private",
            "project_id": thread.get("project_id"),
            "current_alternate_model": None,
            "current_temperature_override": None,
        }

    async def get_chat_session(self, chat_session_id: str) -> dict[str, Any]:
        thread = await self._thread_controller.get_thread(chat_session_id)
        if thread and not await self._ensure_thread_belongs_to_user(chat_session_id, thread):
            raise PermissionError(t("common.forbidden"))

        if not thread:
            return {
                "chat_session_id": chat_session_id,
                "description": "Chat",
                "persona_id": 0,
                "persona_name": "",
                "messages": [],
                "time_created": None,
                "time_updated": None,
                "last_message_at": None,
                "last_accessed_at": None,
                "shared_status": "private",
                "current_temperature_override": None,
                "current_alternate_model": None,
                "owner_name": None,
                "packets": [],
            }

        metadata = thread.get("metadata", {}) or {}
        try:
            accessed_thread = await self._thread_controller.mark_accessed(chat_session_id)
            if accessed_thread:
                thread = accessed_thread
                metadata = thread.get("metadata", {}) or {}
        except Exception:
            logger.warning("Could not record chat session access for %s", chat_session_id)
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

                reasoning_delta = payload.get("reasoning_delta")
                if isinstance(reasoning_delta, str):
                    return reasoning_delta

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

        def _reindex_tool_packets(
            packets: list[dict[str, Any]],
            start_turn: int,
        ) -> tuple[list[dict[str, Any]], int]:
            """Assign stable turn_index values so each reconstructed tool step stays visible."""
            from controller.step_turn_rules import should_increment_turn

            if not packets:
                return [], start_turn

            reindexed: list[dict[str, Any]] = []
            current_turn = start_turn
            prev_type: str | None = None
            prev_tool: str | None = None

            for packet in packets:
                obj = packet.get("obj", {}) if isinstance(packet, dict) else {}
                pkt_type = obj.get("type", "")
                tool_name = obj.get("tool_name")

                if should_increment_turn(
                    pkt_type,
                    prev_type,
                    prev_tool,
                    tool_name if isinstance(tool_name, str) else None,
                    is_first=not reindexed,
                ):
                    current_turn += 1

                reindexed.append(
                    {
                        **packet,
                        "placement": {"turn_index": current_turn, "sub_turn_index": None},
                    }
                )
                prev_type = pkt_type
                prev_tool = tool_name if isinstance(tool_name, str) else prev_tool

            return reindexed, current_turn + 1

        try:
            state = await self._thread_controller.get_thread_state(chat_session_id)
            langgraph_messages = state.get("values", {}).get("messages", [])
            pending_tool_packets: list[dict[str, Any]] = []
            # tool_call_id -> index of that call's `custom_tool_start` in
            # pending_tool_packets, so its `custom_tool_delta` can be inserted
            # right after it instead of landing wherever the ToolMessage
            # happened to arrive (a batch of parallel calls appends all of its
            # starts before any of their results come back).
            open_tool_call_positions: dict[str, int] = {}
            pending_ltm_recalled_from_system = 0
            pending_ltm_recalled_from_user = 0
            msg_idx = 0
            # Per-message persona_id/model (set on the human message that
            # triggered a turn) take priority over thread-level metadata,
            # which only ever reflects the most recently sent value and goes
            # stale the moment a later turn switches agent/model (e.g. via
            # retry). Seed from thread metadata so messages predating this
            # tracking still resolve correctly.
            current_persona_id = metadata.get("persona_id")
            current_model: str | None = None
            # A retry resends the user's message as a brand new HumanMessage
            # (LangGraph just appends to the flat checkpoint — there is no
            # true branching at that layer), stamped with is_regenerate=True.
            # That duplicate must not surface as its own turn: the response
            # that follows it becomes a sibling of the previous response
            # under the ORIGINAL user message instead of a new sequential
            # child. last_real_user_msg_id tracks that original parent;
            # pending_parent_override carries it forward to the next
            # response exactly once.
            last_real_user_msg_id: int | None = None
            pending_parent_override: int | None = None

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
                    tool_call_id = getattr(raw_msg, "tool_call_id", None) or (
                        raw_msg.get("tool_call_id") if isinstance(raw_msg, dict) else None
                    )
                    tool_content = _extract_content(raw_msg)
                    generated_file = parse_generated_file_payload(tool_content)
                    # Document tools are represented by their generated_file card
                    # alone — same as the live stream, which replaces their
                    # timeline step with the document_generation_* packets.
                    if generated_file is None:
                        delta_packet = {
                            "placement": {"turn_index": 0, "sub_turn_index": None},
                            "obj": {
                                "type": "custom_tool_delta",
                                "tool_name": tool_name,
                                "response_type": "tool_result",
                                "data": tool_content,
                            },
                        }
                        if tool_call_id and tool_call_id in open_tool_call_positions:
                            insert_pos = open_tool_call_positions.pop(tool_call_id) + 1
                            pending_tool_packets.insert(insert_pos, delta_packet)
                            for call_id, pos in open_tool_call_positions.items():
                                if pos >= insert_pos:
                                    open_tool_call_positions[call_id] = pos + 1
                        else:
                            pending_tool_packets.append(delta_packet)
                    if generated_file is not None:
                        pending_tool_packets.append(
                            {
                                "placement": {"turn_index": 0, "sub_turn_index": None},
                                "obj": build_generated_file_packet_obj(generated_file),
                            }
                        )
                    continue

                if raw_type == "system":
                    system_text = _extract_content(raw_msg)
                    if (
                        "[Long-Term Memory — Previously learned facts about this user]"
                        in system_text
                    ):
                        facts = [
                            line
                            for line in system_text.splitlines()
                            if line.strip().startswith("- ")
                        ]
                        if facts:
                            pending_ltm_recalled_from_system = len(facts)
                    continue

                if raw_type == "ai":
                    tool_calls = getattr(raw_msg, "tool_calls", None) or (
                        raw_msg.get("tool_calls", []) if isinstance(raw_msg, dict) else []
                    )
                    msg_content, reasoning_text = _extract_visible_and_reasoning(raw_msg)
                    if not reasoning_text:
                        reasoning_text = _extract_reasoning_from_metadata(raw_msg)

                    if tool_calls:
                        # Preserve intermediate reasoning emitted before this tool call
                        if reasoning_text:
                            pending_tool_packets.append(
                                {
                                    "placement": {"turn_index": 0, "sub_turn_index": None},
                                    "obj": {"type": "reasoning_start"},
                                }
                            )
                            pending_tool_packets.append(
                                {
                                    "placement": {"turn_index": 0, "sub_turn_index": None},
                                    "obj": {"type": "reasoning_delta", "reasoning": reasoning_text},
                                }
                            )
                        # A model often writes a sentence before calling its
                        # tools ("let me look at these pages"). That text
                        # streams live as part of the answer, so dropping it
                        # here made a reloaded conversation start abruptly at
                        # the tool results instead.
                        if msg_content:
                            pending_tool_packets.append(
                                {
                                    "placement": {"turn_index": 0, "sub_turn_index": None},
                                    "obj": {
                                        "type": "message_start",
                                        "content": msg_content,
                                        "final_documents": None,
                                    },
                                }
                            )
                        for tool_call in tool_calls:
                            tool_name = (
                                tool_call.get("name", "tool")
                                if isinstance(tool_call, dict)
                                else getattr(tool_call, "name", "tool")
                            )
                            tool_args = (
                                tool_call.get("args")
                                if isinstance(tool_call, dict)
                                else getattr(tool_call, "args", None)
                            )
                            call_id = (
                                tool_call.get("id")
                                if isinstance(tool_call, dict)
                                else getattr(tool_call, "id", None)
                            )
                            # A document tool is shown by its generated_file
                            # card alone, exactly as the live stream does it.
                            # Adding a generic tool step here made a reloaded
                            # conversation grow an extra timeline entry the
                            # user never saw while it was streaming.
                            if is_document_tool(tool_name):
                                continue
                            pending_tool_packets.append(
                                {
                                    "placement": {"turn_index": 0, "sub_turn_index": None},
                                    "obj": {
                                        "type": "custom_tool_start",
                                        "tool_name": tool_name,
                                        "args": tool_args,
                                    },
                                }
                            )
                            if call_id:
                                open_tool_call_positions[call_id] = len(pending_tool_packets) - 1
                        continue

                    if not msg_content:
                        continue

                    if pending_parent_override is not None:
                        parent_msg_id = pending_parent_override
                        pending_parent_override = None
                    else:
                        parent_msg_id = msg_idx if msg_idx > 0 else None
                    msg_idx += 1

                    turn_packets: list[dict[str, Any]] = []
                    turn_counter = 0

                    # Read LTM metadata from the AI message first so it can be placed
                    # before tool packets — matching the streaming order where LTM recall
                    # is emitted before the agent begins tool calls.
                    _extra = (
                        raw_msg.get("additional_kwargs", {}) or {}
                        if isinstance(raw_msg, dict)
                        else getattr(raw_msg, "additional_kwargs", {}) or {}
                    )
                    ltm_recalled = _extra.get("_ltm_recalled", 0)
                    if not ltm_recalled and pending_ltm_recalled_from_system:
                        ltm_recalled = pending_ltm_recalled_from_system
                    if not ltm_recalled and pending_ltm_recalled_from_user:
                        ltm_recalled = pending_ltm_recalled_from_user
                    pending_ltm_recalled_from_system = 0
                    pending_ltm_recalled_from_user = 0
                    if ltm_recalled:
                        ltm_memories = _extra.get("_ltm_memories", [])
                        logger.debug(
                            "[LTM-history] ai msg %d: extra_keys=%s ltm_recalled=%s",
                            msg_idx,
                            list(_extra.keys()),
                            ltm_recalled,
                        )
                        turn_packets.append(
                            {
                                "placement": {"turn_index": turn_counter, "sub_turn_index": None},
                                "obj": {
                                    "type": "long_term_memory_recall",
                                    "fact_count": ltm_recalled,
                                    "memories": ltm_memories,
                                },
                            }
                        )
                        turn_counter += 1

                    if pending_tool_packets:
                        reindexed_tools, next_turn = _reindex_tool_packets(
                            pending_tool_packets,
                            turn_counter,
                        )
                        turn_packets.extend(reindexed_tools)
                        pending_tool_packets = []
                        open_tool_call_positions = {}
                        turn_counter = next_turn

                    if reasoning_text:
                        turn_packets.append(
                            {
                                "placement": {"turn_index": turn_counter, "sub_turn_index": None},
                                "obj": {"type": "reasoning_start"},
                            }
                        )
                        turn_packets.append(
                            {
                                "placement": {"turn_index": turn_counter, "sub_turn_index": None},
                                "obj": {
                                    "type": "reasoning_delta",
                                    "reasoning": reasoning_text,
                                },
                            }
                        )
                        turn_counter += 1

                    duration_sec = _extra.get("processing_duration_seconds") or _extra.get(
                        "duration_seconds"
                    )
                    if duration_sec is None and reasoning_text:
                        duration_sec = max(5, min(300, int(len(reasoning_text) / 25)))
                    elif duration_sec is None and turn_packets:
                        duration_sec = max(3, len(turn_packets) * 2)

                    display_turn = turn_counter
                    turn_packets.append(
                        {
                            "placement": {"turn_index": display_turn, "sub_turn_index": None},
                            "obj": {
                                "type": "message_start",
                                "content": msg_content,
                                "final_documents": None,
                                "pre_answer_processing_seconds": duration_sec,
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
                            "overridden_model": current_model,
                            "alternate_assistant_id": current_persona_id,
                            "chat_session_id": chat_session_id,
                            "citations": None,
                            "files": [],
                            "tool_call": None,
                            "current_feedback": None,
                            "processing_duration_seconds": duration_sec,
                            "sub_questions": [],
                            "comments": None,
                            "parentMessageId": parent_msg_id,
                            "refined_answer_improvement": None,
                            "is_agentic": None,
                        }
                    )
                    continue

                if raw_type not in ("human", "user"):
                    continue

                # Restore file badges from additional_kwargs set at send time.
                # raw_msg may be a LangChain object or a plain dict depending
                # on checkpointer deserialization.
                if isinstance(raw_msg, dict):
                    _extra = raw_msg.get("additional_kwargs", {}) or {}
                else:
                    _extra = getattr(raw_msg, "additional_kwargs", {}) or {}

                # A message carrying its own persona_id/model means this turn
                # was sent with that agent/model — adopt it as the current
                # value for this and subsequent messages until the next one
                # overrides it. Messages predating this tracking have neither
                # key, so current_persona_id/current_model keep whatever they
                # were seeded/last set to (thread metadata, by default).
                if "persona_id" in _extra:
                    current_persona_id = _extra.get("persona_id")
                if _extra.get("model"):
                    current_model = _extra.get("model")

                if _extra.get("is_regenerate"):
                    # The user never sent this — it's a duplicate created so
                    # the agent graph would replay with new input. Skip the
                    # turn entirely; the response that follows becomes a
                    # sibling of the previous response under the original
                    # user message (last_real_user_msg_id), not a new turn.
                    pending_parent_override = last_real_user_msg_id
                    continue

                msg_content = _strip_think_tags(_extract_content(raw_msg))
                parent_msg_id = msg_idx if msg_idx > 0 else None
                msg_idx += 1
                last_real_user_msg_id = msg_idx

                if not pending_ltm_recalled_from_user:
                    recalled_from_user = _extra.get("_ltm_recalled", 0)
                    if isinstance(recalled_from_user, int) and recalled_from_user > 0:
                        pending_ltm_recalled_from_user = recalled_from_user
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
                        "overridden_model": current_model,
                        "alternate_assistant_id": current_persona_id,
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

            # If stream/state ends without a visible AI message after tool calls
            # (e.g. the model's final generation was interrupted and produced no
            # content), preserve those tool steps as their own history turn
            # instead of dropping them. A `packets_2d` entry with no matching
            # `messages` entry never rendered — the chat bubble that would show
            # it doesn't exist — so a `messages` entry is added here too.
            if pending_tool_packets:
                reindexed_tools, next_turn = _reindex_tool_packets(pending_tool_packets, 0)
                # Without a message_start/stop pair, the client has no signal
                # that this turn ever finished (no `stop` packet == "still
                # streaming" as far as the timeline pacing/completion logic is
                # concerned), so only the first step ever gets revealed.
                reindexed_tools.append(
                    {
                        "placement": {"turn_index": next_turn, "sub_turn_index": None},
                        "obj": {
                            "type": "message_start",
                            "content": "",
                            "final_documents": None,
                        },
                    }
                )
                reindexed_tools.append(
                    {
                        "placement": {"turn_index": next_turn, "sub_turn_index": None},
                        "obj": {"type": "stop", "stop_reason": "finished"},
                    }
                )
                packets_2d.append(reindexed_tools)
                pending_tool_packets = []

                if pending_parent_override is not None:
                    parent_msg_id = pending_parent_override
                    pending_parent_override = None
                else:
                    parent_msg_id = msg_idx if msg_idx > 0 else None
                msg_idx += 1
                messages.append(
                    {
                        "message_id": msg_idx,
                        "message_type": "assistant",
                        "research_type": None,
                        "parent_message": parent_msg_id,
                        "latest_child_message": None,
                        "message": "",
                        "rephrased_query": None,
                        "context_docs": None,
                        "time_sent": None,
                        "overridden_model": current_model,
                        "alternate_assistant_id": current_persona_id,
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

            # A parent can now have multiple children (retried alternates
            # sharing the same original user message) instead of always
            # exactly one — the "latest" child is whichever was appended
            # last, matching how the live in-session switcher already
            # treats the most recent retry as the active branch.
            children_by_parent: dict[int, list[int]] = {}
            for m in messages:
                if m["parent_message"] is not None:
                    children_by_parent.setdefault(m["parent_message"], []).append(
                        m["message_id"]
                    )
            for m in messages:
                children = children_by_parent.get(m["message_id"])
                m["latest_child_message"] = children[-1] if children else None
        except Exception:
            import logging as _logging
            import traceback as _traceback

            _logging.getLogger(__name__).error(
                "Failed to load chat history for session %s (returning the %d "
                "turn(s) parsed before the failure):\n%s",
                chat_session_id,
                len(messages),
                _traceback.format_exc(),
            )
            # `messages`/`packets_2d` already hold whatever was parsed before
            # the failing turn — a long tool-heavy conversation has one bad
            # message wipe the entire visible history otherwise, discarding
            # turns that parsed fine.

        return {
            "chat_session_id": chat_session_id,
            "description": metadata.get("name", "New Chat"),
            "persona_id": metadata.get("persona_id", 0),
            "persona_name": "",
            "messages": messages,
            "time_created": thread.get("created_at"),
            "time_updated": thread.get("updated_at"),
            "last_message_at": thread.get("last_message_at"),
            "last_accessed_at": thread.get("last_accessed_at"),
            "shared_status": "private",
            "current_temperature_override": metadata.get("current_temperature_override"),
            "current_alternate_model": metadata.get("current_alternate_model"),
            "owner_name": None,
            "packets": packets_2d,
        }

    async def delete_chat_session(self, chat_session_id: str) -> dict[str, Any]:
        thread = await self._thread_controller.get_thread(chat_session_id)
        if thread and not await self._ensure_thread_belongs_to_user(chat_session_id, thread):
            return {"success": False, "error": t("common.forbidden")}

        await self._thread_controller.delete_thread(chat_session_id)
        return {"success": True}

    async def delete_all_chat_sessions(self) -> dict[str, Any]:
        threads = await self._list_user_threads(limit=1000, offset=0)
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
            return {"success": False, "error": t("chat.missing_session_id")}

        thread = await self._thread_controller.get_thread(session_id)
        if not thread:
            return {"success": False, "error": t("chat.session_not_found")}
        if not await self._ensure_thread_belongs_to_user(session_id, thread):
            return {"success": False, "error": t("common.forbidden")}

        metadata = thread.get("metadata", {}) or {}
        trimmed_name = name.strip() if isinstance(name, str) else None
        metadata["name"] = (
            trimmed_name
            if trimmed_name
            else await self._derive_session_name(
                session_id,
                default_name=metadata.get("name", "New Chat") or "New Chat",
                model_name=metadata.get("current_alternate_model"),
            )
        )
        await self._thread_controller.update_thread(session_id, metadata, update_timestamp=False)
        return {"success": True}

    async def update_chat_session_model(
        self, session_id: str | None, model: str | None
    ) -> dict[str, Any]:
        if not session_id:
            return {"success": False, "error": t("chat.missing_session_id")}

        thread = await self._thread_controller.get_thread(session_id)
        if thread and await self._ensure_thread_belongs_to_user(session_id, thread):
            metadata = thread.get("metadata", {}) or {}
            metadata["current_alternate_model"] = model
            await self._thread_controller.update_thread(session_id, metadata)
        elif thread:
            return {"success": False, "error": t("common.forbidden")}
        return {"success": True}

    async def update_chat_session_temperature(
        self,
        session_id: str | None,
        temperature: float | None,
    ) -> dict[str, Any]:
        if not session_id:
            return {"success": False, "error": t("chat.missing_session_id")}

        thread = await self._thread_controller.get_thread(session_id)
        if thread and await self._ensure_thread_belongs_to_user(session_id, thread):
            metadata = thread.get("metadata", {}) or {}
            metadata["current_temperature_override"] = temperature
            await self._thread_controller.update_thread(session_id, metadata)
        elif thread:
            return {"success": False, "error": t("common.forbidden")}
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
