"""Thread controller - handles threads and runs domain logic."""

from typing import Any

from controller.base import BaseController
from core.db.repositories import ThreadRepository
from service.CheckpointerService import get_checkpointer
from service.StoreService import (
    add_thread,
    delete_thread_from_store,
    get_thread_from_store,
    list_threads_from_store,
    update_thread_in_store,
)


class ThreadController(BaseController):
    """Controller for threads and runs domain.

    Injects:
    - ThreadRepository: for persistent thread storage
    - CheckpointerService: forLangGraph checkpointing
    """

    def __init__(self, repo: ThreadRepository | None = None):
        self._repo = repo or ThreadRepository()

    # =========================================================================
    # Thread CRUD
    # =========================================================================

    async def get_thread(self, thread_id: str) -> dict[str, Any] | None:
        """Get a thread by ID."""
        return await get_thread_from_store(thread_id)

    async def list_threads(
        self,
        limit: int = 100,
        offset: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """List threads with optional metadata filter."""
        return await list_threads_from_store(limit, offset, metadata)

    async def create_thread(
        self,
        thread_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a new thread."""
        import uuid
        from datetime import UTC, datetime

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
        await add_thread(thread)
        return thread

    async def update_thread(
        self,
        thread_id: str,
        metadata: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Update a thread."""
        return await update_thread_in_store(thread_id, {"metadata": metadata})

    async def delete_thread(self, thread_id: str) -> bool:
        """Delete a thread."""
        return await delete_thread_from_store(thread_id)

    # =========================================================================
    # Thread state (checkpointer)
    # =========================================================================

    async def get_thread_state(
        self,
        thread_id: str,
    ) -> dict[str, Any]:
        """Get thread state including messages."""
        from langgraph.types import Send

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
                "created_at": (
                    checkpoint_tuple.metadata.get("created_at")
                    if checkpoint_tuple.metadata
                    else None
                ),
                "parent_config": checkpoint_tuple.parent_config,
            }
        except Exception as e:
            return {**empty_state, "error": str(e)}

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
            if hasattr(msg, "dict"):
                serialized.append(msg.dict())
            elif hasattr(msg, "model_dump"):
                serialized.append(msg.model_dump())
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
                    serialized.append({"content": str(msg)})
        return serialized


# Singleton instance
_thread_controller: ThreadController | None = None


def get_thread_controller() -> ThreadController:
    """Get the singleton ThreadController instance."""
    global _thread_controller
    if _thread_controller is None:
        _thread_controller = ThreadController()
    return _thread_controller
