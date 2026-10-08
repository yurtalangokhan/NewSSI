"""Chat session CRUD and metadata management service."""

from datetime import UTC, datetime
from typing import Any
import uuid

from error_contract import BadRequestError, ForbiddenError, InternalServerError, NotFoundError

from core.observability.logger import get_logger
from infrastructure.runtime.checkpointer import get_checkpointer
from service.chat.chat_history_reconstruction import reconstruct_message_tree, reconstruct_messages
from service.chat.chat_thread_service import remember_model_provider
from service.chat.chat_title_service import (
    DEFAULT_SESSION_NAME,
    ChatTitleService,
    get_chat_title_service,
    resolve_display_name,
)
from service.chat.session_naming_service import (
    SessionNamingService,
    apply_user_name,
    get_naming_lock,
)
from service.chat_runs.provider import get_chat_run_service
from service.chat_runs.service import ChatRunService
from service.common.base import BaseService
from service.common.domain_errors import translate_domain_errors
from service.knowledge_evidence.factory import build_knowledge_evidence_hydrator
from service.knowledge_evidence.hydrator import KnowledgeEvidenceHydrator
from service.threads import ThreadAccessService, get_thread_access_service

logger = get_logger(__name__)

#: delete_all_chat_sessions pages through the caller's threads with this as
#: the page size, rather than fetching a single fixed-size batch. A single
#: limit=1000 call left everything past row 1000 undeleted while still
#: reporting success -- the account was not empty, and nothing said so.
DELETE_ALL_BATCH_SIZE = 1000


class ChatManagementService(BaseService):
    """Owns non-streaming chat endpoints and delegates persistence to ThreadAccessService."""

    def __init__(
        self,
        thread_service: ThreadAccessService | None = None,
        user_id: str = "dev-user",
        owner_ids: list[str] | None = None,
        title_service: ChatTitleService | None = None,
        chat_runs: ChatRunService | None = None,
        naming_service: SessionNamingService | None = None,
        evidence_hydrator: KnowledgeEvidenceHydrator | None = None,
    ):
        self._thread_service = thread_service or get_thread_access_service()
        self._title_service = title_service or get_chat_title_service()
        self._evidence_hydrator = evidence_hydrator or build_knowledge_evidence_hydrator()
        self._user_id = user_id
        self._chat_runs = chat_runs
        self._owner_ids: list[str] = []
        for candidate in [user_id, *(owner_ids or [])]:
            normalized = str(candidate).strip() if candidate else ""
            if normalized and normalized not in self._owner_ids:
                self._owner_ids.append(normalized)
        self._naming = naming_service or SessionNamingService(
            thread_service=self._thread_service,
            title_service=self._title_service,
            lock=get_naming_lock(),
            checkpointer_provider=lambda: get_checkpointer(),
            default_user_id=self._user_id,
        )

    def _runs(self) -> ChatRunService:
        return self._chat_runs or get_chat_run_service()

    async def _active_run_thread_ids(self, threads: list[dict[str, Any]]) -> set[str]:
        """Threads on this page that still have a live run.

        Best-effort: the chat-run runtime is optional (a deployment without
        Redis), and a missing activity indicator is never worth failing the
        session list over it.
        """
        thread_ids = [thread.get("thread_id") for thread in threads if thread.get("thread_id")]
        if not thread_ids:
            return set()
        try:
            return await self._runs().active_thread_ids(thread_ids, owner_ids=self._owner_ids)
        except Exception as exc:  # indicator lookup is best-effort
            logger.warning("[ChatRun] active-run lookup for the session list failed: %s", exc)
            return set()

    @property
    def owner_ids(self) -> frozenset[str]:
        return frozenset(self._owner_ids)

    async def can_access_session(self, session_id: str) -> bool:
        thread = await self._thread_service.get_thread(session_id)
        return bool(thread) and await self._ensure_thread_belongs_to_user(session_id, thread)

    @translate_domain_errors
    async def mark_session_seen(self, session_id: str) -> None:
        """Advance a chat's read watermark (``last_accessed_at``) to now.

        The sidebar's unread dot compares the newest message against this
        watermark, so a client that has actually rendered the answer clears it
        without reopening the chat. Best-effort, like every access update: an
        unknown chat is a 404, an unwritable one is only logged.
        """
        if not await self.can_access_session(session_id):
            raise NotFoundError(message_key="chat.session_not_found")
        try:
            await self._thread_service.mark_accessed(session_id)
        except Exception:
            logger.warning("Could not record chat session read for %s", session_id, exc_info=True)

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

    def _owner_metadata_candidates(self) -> list[dict[str, Any]]:
        """Every JSONB shape `_matches_owner` would accept, as query filters.

        One candidate per owner id per match path (current `user_id`, or
        membership in `legacy_user_ids`), OR'd together server-side --
        replacing a fetch-1000-and-filter-in-Python step that silently
        missed anything past row 1000.
        """
        candidates: list[dict[str, Any]] = []
        for owner_id in self._owner_ids:
            candidates.append({"user_id": owner_id})
            candidates.append({"legacy_user_ids": [owner_id]})
        return candidates

    async def _list_user_threads(self, limit: int, offset: int) -> list[dict[str, Any]]:
        if len(self._owner_ids) <= 1:
            return await self._thread_service.list_threads(
                limit=limit,
                offset=offset,
                metadata={"user_id": self._user_id},
            )

        return await self._thread_service.list_threads(
            limit=limit,
            offset=offset,
            metadata_any=self._owner_metadata_candidates(),
        )

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
        name_contains: str | None = None,
        agents_only: bool = False,
    ) -> list[dict[str, Any]]:
        if len(self._owner_ids) <= 1:
            return await self._thread_service.list_chat_sessions_by_activity(
                page_size=page_size,
                before_activity=before_activity,
                before_id=before_id,
                metadata={"user_id": self._user_id},
                name_contains=name_contains,
                agents_only=agents_only,
            )

        return await self._thread_service.list_chat_sessions_by_activity(
            page_size=page_size,
            before_activity=before_activity,
            before_id=before_id,
            metadata_any=self._owner_metadata_candidates(),
            name_contains=name_contains,
            agents_only=agents_only,
        )

    async def _ensure_thread_belongs_to_user(self, thread_id: str, thread: dict[str, Any] | None) -> bool:
        if not thread:
            return False

        metadata = thread.get("metadata", {}) or {}
        owner = metadata.get("user_id")

        # Migration path for old records created before ownership was enforced.
        if not owner:
            metadata["user_id"] = self._user_id
            await self._thread_service.update_thread(thread_id, metadata, update_timestamp=False)
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
            await self._thread_service.update_thread(thread_id, metadata, update_timestamp=False)
            return True

        return False

    @translate_domain_errors
    async def get_chat_sessions(
        self,
        page_size: int = 100,
        before_activity: str | None = None,
        before_id: str | None = None,
        query: str | None = None,
        agents_only: bool = False,
    ) -> dict[str, Any]:
        page_size = max(1, min(page_size, 100))
        threads = await self._list_user_threads_by_activity(
            page_size=page_size + 1,
            before_activity=before_activity,
            before_id=before_id,
            name_contains=query,
            agents_only=agents_only,
        )
        threads.sort(
            key=lambda thread: (self._activity_time(thread), thread.get("thread_id") or ""),
            reverse=True,
        )
        has_more = len(threads) > page_size
        threads = threads[:page_size]

        active_thread_ids = await self._active_run_thread_ids(threads)

        checkpointer = get_checkpointer()
        sessions: list[dict[str, Any]] = []

        for thread in threads:
            thread_id = thread.get("thread_id", "")
            metadata = thread.get("metadata", {}) or {}
            stored_name = metadata.get("name")

            # A still-unnamed session gets a readable stand-in, never a model
            # call: one generation per listed row would make opening the
            # sidebar the most expensive request in the app. The real title
            # arrives through the auto-name endpoint.
            first_user_message = ""
            if stored_name in (None, "", DEFAULT_SESSION_NAME) and checkpointer and thread_id:
                try:
                    first_user_message = (await self._naming.extract_first_exchange(thread_id)).user_message
                except Exception as exc:
                    logger.warning(
                        "[ChatTitle] Could not read session %s transcript for listing: %s",
                        thread_id,
                        exc,
                    )

            display = resolve_display_name(
                stored_name=stored_name,
                provisional_flag=bool(metadata.get("name_provisional")),
                first_user_message=first_user_message,
            )

            sessions.append(
                {
                    "id": thread_id,
                    "name": display.title,
                    "description": display.title,
                    # Tells the client this name is worth asking to
                    # regenerate: either naming fell back, or the thread has
                    # no stored name and what it sees is the stand-in built
                    # above. Neither is distinguishable from a settled title
                    # otherwise, because `description` is never sent empty.
                    "name_provisional": display.provisional,
                    "persona_id": metadata.get("persona_id", 0),
                    "time_created": thread.get("created_at"),
                    "time_updated": thread.get("updated_at"),
                    "last_message_at": thread.get("last_message_at"),
                    "last_accessed_at": thread.get("last_accessed_at"),
                    "has_active_run": thread_id in active_thread_ids,
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

    @translate_domain_errors
    async def create_chat_session(
        self,
        persona_id: Any = 0,
        description: str | None = None,
        project_id: int | None = None,
    ) -> dict[str, Any]:
        thread_id = str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()
        name = (description or "").strip() or "New Chat"

        thread = await self._thread_service.create_thread(
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
            "has_active_run": False,
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
            pending = await self._thread_service.get_pending_interrupt(chat_session_id)
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

    @translate_domain_errors
    async def get_chat_session(self, chat_session_id: str) -> dict[str, Any]:
        thread = await self._thread_service.get_thread(chat_session_id)
        if thread and not await self._ensure_thread_belongs_to_user(chat_session_id, thread):
            raise ForbiddenError()

        if not thread:
            raise NotFoundError(message_key="chat.session_not_found")

        metadata = thread.get("metadata", {}) or {}
        try:
            accessed_thread = await self._thread_service.mark_accessed(chat_session_id)
            if accessed_thread:
                thread = accessed_thread
                metadata = thread.get("metadata", {}) or {}
        except Exception:
            logger.warning("Could not record chat session access for %s", chat_session_id)

        # Walk every checkpoint of the thread (not just the latest), so a
        # response a retry forked away from stays reachable on its own
        # branch instead of disappearing once it's no longer the tip. Falls
        # back to the single-state path below when history isn't available
        # (older thread service stand-ins, a checkpointer without alist
        # support, or any failure) — never breaks a page load over this.
        try:
            checkpoints = await self._thread_service.get_thread_state_history(chat_session_id)
        except Exception:
            logger.exception("Failed to load thread state history for session %s", chat_session_id)
            checkpoints = []

        if checkpoints:
            messages, packets_2d = reconstruct_message_tree(checkpoints, metadata, chat_session_id)
        else:
            try:
                state = await self._thread_service.get_thread_state(chat_session_id)
                langgraph_messages = state.get("values", {}).get("messages", [])
            except Exception:
                logger.exception("Failed to load thread state for session %s", chat_session_id)
                langgraph_messages = []

            messages, packets_2d = reconstruct_messages(langgraph_messages, metadata, chat_session_id)

        # Knowledge tool steps replay as evidence references; load their
        # chunks and subgraph from this thread's evidence rows.
        await self._evidence_hydrator.hydrate_tree(chat_session_id, packets_2d)

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
                (p.get("placement", {}).get("turn_index", 0) for p in last_turn if isinstance(p, dict)),
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

    @translate_domain_errors
    async def delete_chat_session(self, chat_session_id: str) -> dict[str, Any]:
        thread = await self._thread_service.get_thread(chat_session_id)
        if not thread:
            raise NotFoundError(message_key="chat.session_not_found")
        if not await self._ensure_thread_belongs_to_user(chat_session_id, thread):
            raise ForbiddenError()

        if not await self._thread_service.delete_thread(chat_session_id):
            raise NotFoundError(message_key="chat.session_not_found")
        return {"success": True}

    @translate_domain_errors
    async def delete_all_chat_sessions(self) -> dict[str, Any]:
        deleted_count = 0

        while True:
            # offset stays 0: each deleted thread is one fewer thread ahead
            # of it, so the next page is always what is left, not what
            # comes after this one.
            batch = await self._list_user_threads(limit=DELETE_ALL_BATCH_SIZE, offset=0)
            if not batch:
                break

            for thread in batch:
                thread_id = thread.get("thread_id")
                if not thread_id:
                    continue
                await self._thread_service.delete_thread(thread_id)
                deleted_count += 1

            if len(batch) < DELETE_ALL_BATCH_SIZE:
                break

        return {"success": True, "deleted_count": deleted_count}

    @translate_domain_errors
    async def rename_chat_session(self, session_id: str | None, name: str | None) -> dict[str, Any]:
        if not session_id:
            raise BadRequestError(message_key="chat.missing_session_id")

        thread = await self._thread_service.get_thread(session_id)
        if not thread:
            raise NotFoundError(message_key="chat.session_not_found")
        if not await self._ensure_thread_belongs_to_user(session_id, thread):
            raise ForbiddenError()

        metadata = thread.get("metadata", {}) or {}
        trimmed_name = name.strip() if isinstance(name, str) else None

        if trimmed_name:
            apply_user_name(metadata, trimmed_name)
            await self._thread_service.update_thread(session_id, metadata, update_timestamp=False)
            return {"success": True}

        await self._naming.ensure_named(session_id, respect_legacy=False)
        return {"success": True}

    @translate_domain_errors
    async def update_chat_session_model(self, session_id: str | None, model: str | None) -> dict[str, Any]:
        if not session_id:
            raise BadRequestError(message_key="chat.missing_session_id")

        thread = await self._thread_service.get_thread(session_id)
        if not thread:
            raise NotFoundError(message_key="chat.session_not_found")
        if await self._ensure_thread_belongs_to_user(session_id, thread):
            metadata = thread.get("metadata", {}) or {}
            if model and model != metadata.get("current_alternate_model"):
                # This endpoint carries no provider, so the old model's provider no longer applies.
                remember_model_provider(metadata, None, None)
            metadata["current_alternate_model"] = model
            await self._thread_service.update_thread(session_id, metadata)
        elif thread:
            raise ForbiddenError()
        return {"success": True}

    @translate_domain_errors
    async def update_chat_session_temperature(
        self,
        session_id: str | None,
        temperature: float | None,
    ) -> dict[str, Any]:
        if not session_id:
            raise BadRequestError(message_key="chat.missing_session_id")

        thread = await self._thread_service.get_thread(session_id)
        if not thread:
            raise NotFoundError(message_key="chat.session_not_found")
        if await self._ensure_thread_belongs_to_user(session_id, thread):
            metadata = thread.get("metadata", {}) or {}
            metadata["current_temperature_override"] = temperature
            await self._thread_service.update_thread(session_id, metadata)
        elif thread:
            raise ForbiddenError()
        return {"success": True}

    @translate_domain_errors
    async def stop_chat_session(self, chat_session_id: str, *, client_request_id: str | None = None) -> dict[str, Any]:
        from service.runtime.active_runs_service import cancel_all_for_thread

        thread = await self._thread_service.get_thread(chat_session_id)
        if not thread:
            raise NotFoundError(message_key="chat.session_not_found")
        if not await self._ensure_thread_belongs_to_user(chat_session_id, thread):
            raise ForbiddenError()
        # The supervisor records the Stop first (locally, or as a cross-instance
        # flag its owner's heartbeat picks up), so a generator that breaks on
        # the cooperative flag is still finalized as `cancelled`, not
        # `completed`. The local flag is raised even when the registry fails.
        try:
            await self._runs().cancel_active(chat_session_id, client_request_id=client_request_id)
        finally:
            cancel_all_for_thread(chat_session_id)
        return {"success": True}

    @translate_domain_errors
    async def set_message_as_latest(self) -> dict[str, Any]:
        return {"success": True}

    @translate_domain_errors
    async def get_available_context_tokens(self, session_id: str | None = None) -> dict[str, int]:
        _ = session_id
        return {"max_tokens": 120000, "selected_tokens": 120000}

    @translate_domain_errors
    async def get_session_token_count(self, session_id: str) -> dict[str, int]:
        # Session files are inline attachments in this backend variant.
        # Keep response shape compatible with frontend expectations.
        _ = session_id
        return {"token_count": 0, "total_tokens": 0}

    @translate_domain_errors
    async def get_session_files(self, session_id: str) -> list[dict[str, Any]]:
        thread = await self._thread_service.get_thread(session_id)
        if thread and not await self._ensure_thread_belongs_to_user(session_id, thread):
            raise ForbiddenError()

        if not thread:
            raise NotFoundError(message_key="chat.session_not_found")

        files: list[dict[str, Any]] = []
        seen_ids: set[str] = set()

        try:
            state = await self._thread_service.get_thread_state(session_id)
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
        except Exception as exc:
            logger.exception("Failed to load files for session %s", session_id)
            raise InternalServerError() from exc

        return files

    @translate_domain_errors
    async def create_chat_message_feedback(self) -> dict[str, bool]:
        return {"success": True}

    @translate_domain_errors
    async def remove_chat_message_feedback(self) -> dict[str, bool]:
        return {"success": True}


_chat_management_service: ChatManagementService | None = None


def get_chat_management_service() -> ChatManagementService:
    """Get singleton ChatManagementService."""
    global _chat_management_service
    if _chat_management_service is None:
        _chat_management_service = ChatManagementService()
    return _chat_management_service
