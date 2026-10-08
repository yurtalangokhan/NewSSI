"""Thread access service - handles threads and runs domain logic."""

import asyncio
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from error_contract import InternalServerError
from localization import t

from core.observability.logger import get_logger
from core.types.run_kinds import RunKind
from infrastructure.db.persistence_gateway import thread_repository
from infrastructure.runtime.checkpointer import get_checkpointer
from service.common.base import BaseService
from service.runtime.store_service import (
    add_thread,
    delete_thread_from_store,
    get_thread_from_store,
    list_chat_sessions_by_activity_from_store,
    list_threads_from_store,
    mark_thread_accessed,
    mark_thread_message_activity,
    update_thread_in_store,
)

logger = get_logger(__name__)

DEFAULT_LIST_RUN_KINDS: tuple[str, ...] = (RunKind.PRODUCTION,)


class ThreadAccessService(BaseService):
    """Service for threads and runs domain.

    Injects:
    - ThreadRepository: for persistent thread storage
    - CheckpointerService: forLangGraph checkpointing
    """

    def __init__(self, repo: Any = None):
        self._repo = repo or thread_repository()

    # =========================================================================
    # Thread CRUD
    # =========================================================================

    async def search_owned_threads(
        self, limit: int, offset: int, metadata: dict | None, owner_ids: list[str]
    ) -> list[dict[str, Any]]:
        from service.users import thread_belongs_to_owner_ids

        threads = await self.list_threads(limit, offset, metadata)
        threads = [thread for thread in threads if thread_belongs_to_owner_ids(thread, owner_ids)]
        saver = get_checkpointer()
        if not saver:
            return threads

        async def enrich_thread(thread: dict) -> dict:
            try:
                checkpoint = await saver.aget_tuple({"configurable": {"thread_id": thread["thread_id"]}})
                if checkpoint and checkpoint.checkpoint:
                    thread["values"] = self._sanitize_checkpoint_values(checkpoint.checkpoint.get("channel_values", {}))
            except Exception as exc:
                logger.warning("Failed to fetch state for thread %s: %s", thread["thread_id"], exc)
            return thread

        return list(await asyncio.gather(*(enrich_thread(thread) for thread in threads)))

    async def get_thread(self, thread_id: str) -> dict[str, Any] | None:
        """Get a thread by ID."""
        return await get_thread_from_store(thread_id)

    async def list_threads(
        self,
        limit: int = 100,
        offset: int = 0,
        metadata: dict[str, Any] | None = None,
        metadata_any: Sequence[dict[str, Any]] | None = None,
        run_kinds: Sequence[str] | None = DEFAULT_LIST_RUN_KINDS,
    ) -> list[dict[str, Any]]:
        """List threads with optional metadata filter and run_kinds filter."""
        return await list_threads_from_store(limit, offset, metadata, metadata_any=metadata_any, run_kinds=run_kinds)

    async def list_chat_sessions_by_activity(
        self,
        page_size: int = 100,
        before_activity: str | None = None,
        before_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        metadata_any: Sequence[dict[str, Any]] | None = None,
        run_kinds: Sequence[str] | None = DEFAULT_LIST_RUN_KINDS,
        name_contains: str | None = None,
        agents_only: bool = False,
    ) -> list[dict[str, Any]]:
        """List chat sessions using conversational activity ordering."""
        return await list_chat_sessions_by_activity_from_store(
            page_size,
            before_activity,
            before_id,
            metadata,
            metadata_any=metadata_any,
            run_kinds=run_kinds,
            name_contains=name_contains,
            agents_only=agents_only,
        )

    async def create_thread(
        self,
        thread_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a new thread."""
        from datetime import UTC, datetime
        import uuid

        thread_id = thread_id or str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()

        existing = await get_thread_from_store(thread_id)
        if existing:
            return existing

        thread = {
            "thread_id": thread_id,
            "created_at": now,
            "updated_at": now,
            "metadata": metadata or {},
            "status": "idle",
        }
        created = await add_thread(thread)
        return created or thread

    async def update_thread(
        self,
        thread_id: str,
        metadata: dict[str, Any],
        update_timestamp: bool = True,
    ) -> dict[str, Any] | None:
        """Update a thread."""
        return await update_thread_in_store(
            thread_id,
            {"metadata": metadata},
            update_timestamp=update_timestamp,
        )

    async def mark_message_activity(self, thread_id: str) -> dict[str, Any] | None:
        """Record accepted user-message activity for a thread."""
        return await mark_thread_message_activity(thread_id)

    async def mark_answer_activity(self, thread_id: str, *, at: datetime | None = None) -> dict[str, Any] | None:
        """Record a completed agent answer as the thread's latest message activity.

        The sidebar's unread dot compares the newest message against the last
        time the chat was opened, so a finished answer must advance that
        timestamp too: the accepted user send alone leaves it older than the
        open that followed it.
        """
        return await mark_thread_message_activity(thread_id, at=at)

    async def mark_accessed(self, thread_id: str) -> dict[str, Any] | None:
        """Record a read without changing conversation activity."""
        return await mark_thread_accessed(thread_id)

    async def delete_thread(self, thread_id: str) -> bool:
        """Delete a thread: its message rows *and* its LangGraph checkpoint.

        Deleting only the rows left the checkpointer's thread state behind, so
        reusing the same ``chat_session_id`` (a client that derives a stable
        id, a "start over" flow) resurrected the old conversation — it
        replayed from the checkpoint and grew on every run (B13). The
        retention sweep already purges both; a user-triggered delete must
        too.
        """
        deleted = await delete_thread_from_store(thread_id)
        saver = get_checkpointer()
        if saver is not None and hasattr(saver, "adelete_thread"):
            try:
                await saver.adelete_thread(thread_id)
            except Exception as exc:
                logger.warning(
                    "Could not purge checkpointer state for thread %s: %s",
                    thread_id,
                    exc,
                )
        return deleted

    # =========================================================================
    # Thread state (checkpointer)
    # =========================================================================

    async def get_thread_state_history(self, thread_id: str) -> list[dict[str, Any]]:
        """Returns every checkpoint for a thread, across every branch (not
        just the ancestry of the current tip) — needed so a retried-away
        response stays reachable via its own branch instead of only the
        most-recently-written one. Each entry:
          - "checkpoint_id": str
          - "parent_checkpoint_id": str | None
          - "ts": str | None — when the checkpoint was written. The only
            record of when a turn happened; reconstruction stamps the
            messages a checkpoint introduced with it.
          - "messages": list[Any] — that checkpoint's own full accumulated
            message list, serialized the same way `get_thread_state` does
        """
        saver = get_checkpointer()
        if not saver:
            return []

        try:
            # Scope to the top-level graph's namespace. A FlowAgent compiles
            # every agent-type execution node as an embedded subgraph
            # (flow_builder._make_agent_node), so a single flow turn also
            # writes checkpoints under checkpoint_ns="<node_id>:<task_id>".
            # LangGraph's alist() only filters checkpoint_ns when it is
            # present in the config, so without this those subgraph
            # checkpoints leak in and reconstruct_message_tree mistakes them
            # for extra branches — wiping the real retry-sibling structure.
            config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}
            history: list[dict[str, Any]] = []
            async for checkpoint_tuple in saver.alist(config):
                if not checkpoint_tuple or not checkpoint_tuple.checkpoint:
                    continue
                # Defensive: honour the namespace scope even if a checkpointer
                # implementation ignores the config filter above.
                tuple_config = getattr(checkpoint_tuple, "config", None) or {}
                if tuple_config.get("configurable", {}).get("checkpoint_ns"):
                    continue
                raw_values = checkpoint_tuple.checkpoint.get("channel_values", {})
                values = self._sanitize_checkpoint_values(raw_values)
                messages = self._serialize_messages(values.get("messages", [])) if "messages" in values else []
                parent_config = checkpoint_tuple.parent_config
                parent_checkpoint_id = parent_config["configurable"].get("checkpoint_id") if parent_config else None
                history.append(
                    {
                        "checkpoint_id": checkpoint_tuple.checkpoint.get("id"),
                        "parent_checkpoint_id": parent_checkpoint_id,
                        "ts": checkpoint_tuple.checkpoint.get("ts"),
                        "messages": messages,
                    }
                )
            return history
        except Exception as exc:
            logger.exception("Checkpoint history lookup failed for thread %s", thread_id)
            raise InternalServerError() from exc

    async def get_pending_interrupt(self, thread_id: str):
        """The interrupt a paused run is waiting on, if any — subgraphs included.

        The live SSE packet only exists for the duration of the stream, but the
        interrupt itself is durable: LangGraph parks it in the checkpoint's
        pending writes under the ``__interrupt__`` channel. Reading it back is
        what keeps the decision buttons on the turn after a reload instead of
        leaving the run looking silently stuck.

        Supervisor sub-agents, pipeline stages and the flow canvas' ReActAgent
        node are all subgraphs with checkpoint namespaces of their own, so a
        single root ``aget_tuple`` is not obviously enough. Measured: the
        interrupt bubbles into the root namespace's writes as well, but the
        listing walks every namespace anyway — it costs one query and does not
        depend on that bubbling continuing to hold. Notably it needs no
        compiled agent, which is why the reload path stays cheap.

        Only the *newest* checkpoint of each namespace is inspected. LangGraph
        never deletes a resolved interrupt's ``__interrupt__`` pending write —
        it lingers on the checkpoint that first parked there forever — so a
        finished run still carries one on an older checkpoint. ``alist`` yields
        newest-first, so the first checkpoint seen per namespace is that
        namespace's current tip; a run genuinely parked now has the interrupt
        there, a run that moved past it does not.

        Never raises: a missing checkpointer or an unreadable checkpoint just
        means "nothing pending".
        """
        from agents.interrupts.pending import _as_pending
        from schemas.agent_runtime import PendingInterrupt

        saver = get_checkpointer()
        if not saver:
            return None

        try:
            tuples = saver.alist({"configurable": {"thread_id": thread_id}})
            seen_namespaces: set[str] = set()
            async for checkpoint_tuple in tuples:
                namespace = (
                    (getattr(checkpoint_tuple, "config", None) or {}).get("configurable", {}).get("checkpoint_ns", "")
                )
                if namespace in seen_namespaces:
                    continue  # an older checkpoint of a namespace already at
                    # its tip — a stale __interrupt__ write may still sit here
                seen_namespaces.add(namespace)
                for write in getattr(checkpoint_tuple, "pending_writes", None) or []:
                    # (task_id, channel, value)
                    if len(write) < 3 or write[1] != "__interrupt__":
                        continue
                    raw = write[2]
                    candidates = raw if isinstance(raw, (list, tuple)) else [raw]
                    for candidate in candidates:
                        pending: PendingInterrupt | None = _as_pending(candidate)
                        if pending is not None:
                            return pending
        except Exception:
            logger.warning("Could not read pending interrupts for thread %s", thread_id)
            return None

        return None

    async def get_pending_human_input(self, thread_id: str) -> dict[str, Any] | None:
        """The HumanInput request a paused FlowAgent run is waiting on, if any.

        The live ``human_input`` SSE packet only exists for the duration of the
        stream, but the interrupt itself is durable: LangGraph parks it in the
        checkpoint's pending writes under the ``__interrupt__`` channel. Reading
        it back is what keeps the decision buttons on the turn after a reload
        instead of leaving the run looking silently stuck.

        Kept for callers that only care about the flow canvas' HumanInput node;
        new callers want ``get_pending_interrupt``, which reports every kind of
        pause — including a run waiting on an ``ask_user`` question.
        """
        from agents.interrupts.classify import HUMAN_INPUT

        pending = await self.get_pending_interrupt(thread_id)
        if pending is None or pending.kind != HUMAN_INPUT:
            return None
        return pending.value

    async def get_thread_state(
        self,
        thread_id: str,
    ) -> dict[str, Any]:
        """Get thread state including messages."""
        saver = get_checkpointer()
        empty_state = {
            "values": {"messages": []},
            "next": [],
            "checkpoint": None,
            "metadata": {},
            "created_at": None,
            "parent_config": None,
        }

        if not saver:
            return empty_state

        try:
            config = {"configurable": {"thread_id": thread_id}}
            checkpoint_tuple = await saver.aget_tuple(config)

            if not checkpoint_tuple or not checkpoint_tuple.checkpoint:
                return empty_state

            raw_values = checkpoint_tuple.checkpoint.get("channel_values", {})
            values = self._sanitize_checkpoint_values(raw_values)

            if "messages" in values:
                values["messages"] = self._serialize_messages(values.get("messages", []))

            return {
                "values": values,
                "next": [],
                "checkpoint": {
                    "thread_id": thread_id,
                    "checkpoint_id": checkpoint_tuple.checkpoint.get("id"),
                },
                "metadata": checkpoint_tuple.metadata,
                "created_at": (checkpoint_tuple.metadata.get("created_at") if checkpoint_tuple.metadata else None),
                "parent_config": checkpoint_tuple.parent_config,
            }
        except Exception as exc:
            logger.exception("Checkpoint state lookup failed for thread %s", thread_id)
            raise InternalServerError() from exc

    def _sanitize_checkpoint_values(self, values: dict) -> dict:
        """Remove non-serializable types like Send from checkpoint values."""
        from langgraph.types import Send

        sanitized: dict = {}
        for key, value in values.items():
            if isinstance(value, Send):
                sanitized[key] = {
                    "__type__": "Send",
                    "node": value.node,
                    "arg": str(value.arg)[:500],
                }
            elif isinstance(value, list):
                sanitized[key] = [
                    {
                        "__type__": "Send",
                        "node": v.node,
                        "arg": str(v.arg)[:500],
                    }
                    if isinstance(v, Send)
                    else v
                    for v in value
                ]
            else:
                sanitized[key] = value
        return sanitized

    def _serialize_messages(self, messages: list) -> list[dict]:
        """Serialize messages for response."""
        serialized: list = []
        for msg in messages:
            if hasattr(msg, "model_dump"):
                serialized.append(msg.model_dump())
            elif hasattr(msg, "dict"):
                serialized.append(msg.dict())
            elif isinstance(msg, dict):
                serialized.append(msg)
            else:
                try:
                    serialized.append(
                        {
                            "type": getattr(msg, "type", "unknown"),
                            "content": getattr(msg, "content", str(msg)),
                            "id": getattr(msg, "id", None),
                            "name": getattr(msg, "name", None),
                        }
                    )
                except Exception:
                    logger.exception("Could not serialize checkpoint message")
                    serialized.append({"content": t("common.internal_error")})
        return serialized


# Singleton instance
_thread_access_service: ThreadAccessService | None = None


def get_thread_access_service() -> ThreadAccessService:
    """Get the singleton ThreadAccessService instance."""
    global _thread_access_service
    if _thread_access_service is None:
        _thread_access_service = ThreadAccessService()
    return _thread_access_service
