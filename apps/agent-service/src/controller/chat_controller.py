"""Controller for chat session CRUD and metadata endpoints."""

import uuid
from datetime import UTC, datetime
from typing import Any

from i18n import t
from langchain_core.messages import HumanMessage, SystemMessage

from controller.base import BaseController
from controller.chat_helpers import (
    detect_response_language,
    is_invalid_generated_title,
    normalize_title,
)
from controller.thread_controller import ThreadController, get_thread_controller
from core.llm import get_model
from core.logger import get_logger
from service.ChatHistoryReconstruction import reconstruct_message_tree, reconstruct_messages
from service.CheckpointerService import get_checkpointer

logger = get_logger(__name__)


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

        target_language = detect_response_language(human_message)

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

            normalized = normalize_title(content)
            if is_invalid_generated_title(normalized):
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

    async def _pending_interrupt_packet(self, chat_session_id: str) -> dict[str, Any] | None:
        """The packet a reloaded turn needs to keep showing its controls.

        Each interrupt kind renders differently, so the packet is built from
        the kind rather than passed through: a HumanInput payload IS its own
        packet, while a clarification payload has to become one.

        Never raises: an unreadable checkpoint just means "nothing pending",
        which loses the buttons but not the conversation.
        """
        from agents.clarification.packets import packet_from_interrupt
        from agents.interrupts.classify import HUMAN_INPUT, USER_CLARIFICATION

        try:
            pending = await self._thread_controller.get_pending_interrupt(chat_session_id)
        except Exception:
            logger.warning("Could not read pending interrupt for session %s", chat_session_id)
            return None

        if pending is None:
            return None
        if pending.kind == HUMAN_INPUT:
            return pending.value
        if pending.kind == USER_CLARIFICATION:
            return packet_from_interrupt(pending.value, pending.interrupt_id)
        return None

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

        # Walk every checkpoint of the thread (not just the latest), so a
        # response a retry forked away from stays reachable on its own
        # branch instead of disappearing once it's no longer the tip. Falls
        # back to the single-state path below when history isn't available
        # (older ThreadController stand-ins, a checkpointer without alist
        # support, or any failure) — never breaks a page load over this.
        try:
            checkpoints = await self._thread_controller.get_thread_state_history(chat_session_id)
        except Exception:
            logger.exception("Failed to load thread state history for session %s", chat_session_id)
            checkpoints = []

        if checkpoints:
            messages, packets_2d = reconstruct_message_tree(checkpoints, metadata, chat_session_id)
        else:
            try:
                state = await self._thread_controller.get_thread_state(chat_session_id)
                langgraph_messages = state.get("values", {}).get("messages", [])
            except Exception:
                logger.exception("Failed to load thread state for session %s", chat_session_id)
                langgraph_messages = []

            messages, packets_2d = reconstruct_messages(
                langgraph_messages, metadata, chat_session_id
            )

        # A run parked on an interrupt — a FlowAgent HumanInput node or an
        # `ask_user` question: the live packet died with the stream, so replay
        # it from the checkpoint's pending interrupt. Without this the reloaded
        # turn shows no controls and the run looks stuck, even though it is
        # still waiting.
        pending_packet = await self._pending_interrupt_packet(chat_session_id)

        if pending_packet:
            if not packets_2d:
                packets_2d = [[]]
            # Its own turn_index, matching what the live stream does
            # (streamingUtils): a pause shares no display group with the answer
            # that preceded it, or the client hands the mixed group to the text
            # renderer and the buttons never render.
            last_turn = packets_2d[-1]
            next_turn_index = 1 + max(
                (
                    p.get("placement", {}).get("turn_index", 0)
                    for p in last_turn
                    if isinstance(p, dict)
                ),
                default=-1,
            )
            last_turn.append(
                {
                    "placement": {
                        "turn_index": next_turn_index,
                        "sub_turn_index": None,
                    },
                    "obj": pending_packet,
                }
            )

            # A packet group with no assistant `messages` row never renders —
            # the chat bubble it would hang on does not exist. When the pause
            # happened before any assistant message was persisted (an
            # `ask_user` as the model's first act interrupts the node before
            # it returns), synthesise that row so the card has somewhere to
            # land. Runs that had already streamed an answer keep their real
            # message and skip this.
            if messages and messages[-1].get("message_type") != "assistant":
                # Without a `stop` the client's pacing logic reads this turn as
                # still streaming and shows a "thinking…" spinner forever on
                # reload (the live stream instead ends with `[DONE]`). On its
                # own turn so it does not pull the card's group into the text
                # renderer — the split `_flush_trailing_tool_packets` uses.
                for obj in (
                    {"type": "message_start", "content": "", "final_documents": None},
                    {"type": "stop", "stop_reason": "finished"},
                ):
                    last_turn.append(
                        {
                            "placement": {
                                "turn_index": next_turn_index + 1,
                                "sub_turn_index": None,
                            },
                            "obj": obj,
                        }
                    )

                parent_id = messages[-1].get("message_id")
                synthetic_id = max((m.get("message_id") or 0) for m in messages) + 1
                messages.append(
                    {
                        "message_id": synthetic_id,
                        "message_type": "assistant",
                        "research_type": None,
                        "parent_message": parent_id,
                        "latest_child_message": None,
                        "message": "",
                        "rephrased_query": None,
                        "context_docs": None,
                        "time_sent": None,
                        "overridden_model": None,
                        "alternate_assistant_id": metadata.get("persona_id", 0),
                        "chat_session_id": chat_session_id,
                        "citations": None,
                        "files": [],
                        "tool_call": None,
                        "current_feedback": None,
                        "processing_duration_seconds": None,
                        "sub_questions": [],
                        "comments": None,
                        "parentMessageId": parent_id,
                        "refined_answer_improvement": None,
                        "is_agentic": None,
                    }
                )
                for m in messages:
                    if m.get("message_id") == parent_id:
                        m["latest_child_message"] = synthetic_id
                        break

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
