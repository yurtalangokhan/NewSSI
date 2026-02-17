"""
Thread CRUD routes.

Endpoints: POST /threads/search, POST /threads, GET /threads/{id},
GET /threads/{id}/state, PATCH /threads/{id}, DELETE /threads/{id}
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, List
import uuid

from fastapi import APIRouter, Depends, HTTPException

from service.auth import verify_bearer
from service.checkpointer import get_checkpointer
from service.schemas import (
    ThreadCreateRequest,
    ThreadSearchRequest,
    ThreadUpdateRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(verify_bearer)])


# =============================================================================
# Helpers
# =============================================================================

def _sanitize_checkpoint_values(values: dict) -> dict:
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


# =============================================================================
# Routes
# =============================================================================

@router.post("/threads/search")
async def search_threads(
    request: ThreadSearchRequest = ThreadSearchRequest(),
) -> List[Dict]:
    """Search / List threads."""
    from .store import list_threads_from_store

    threads = await list_threads_from_store(request.limit, request.offset, request.metadata)

    saver = get_checkpointer()
    if not saver:
        return threads

    async def enrich_thread(thread: dict) -> dict:
        try:
            config = {"configurable": {"thread_id": thread["thread_id"]}}
            checkpoint_tuple = await saver.aget_tuple(config)
            if checkpoint_tuple and checkpoint_tuple.checkpoint:
                raw_values = checkpoint_tuple.checkpoint.get("channel_values", {})
                thread["values"] = _sanitize_checkpoint_values(raw_values)
        except Exception as e:
            logger.warning(f"Failed to fetch state for thread {thread['thread_id']}: {e}")
        return thread

    enriched_threads = await asyncio.gather(*[enrich_thread(t) for t in threads])
    return list(enriched_threads)


@router.post("/threads")
async def create_thread(request: ThreadCreateRequest) -> Dict:
    """Create a new thread."""
    from .store import add_thread, get_thread_from_store

    thread_id = request.thread_id or str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    existing = await get_thread_from_store(thread_id)
    if existing:
        return existing

    thread = {
        "thread_id": thread_id,
        "created_at": now,
        "updated_at": now,
        "metadata": request.metadata or {},
        "status": "idle",
    }
    await add_thread(thread)
    return thread


@router.get("/threads/{thread_id}")
async def get_thread(thread_id: str) -> Dict:
    """Get a thread."""
    from .store import get_thread_from_store

    t = await get_thread_from_store(thread_id)
    if not t:
        raise HTTPException(status_code=404, detail="Thread not found")
    return t


@router.get("/threads/{thread_id}/state")
async def get_thread_state(thread_id: str) -> Dict:
    """
    Get thread state including messages.
    Compatible with @langchain/langgraph-sdk client.threads.getState()
    """
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
        values = _sanitize_checkpoint_values(raw_values)

        # Convert messages to serializable format
        if "messages" in values:
            serialized_messages: list = []
            for msg in values.get("messages", []):
                if hasattr(msg, "dict"):
                    serialized_messages.append(msg.dict())
                elif hasattr(msg, "model_dump"):
                    serialized_messages.append(msg.model_dump())
                elif isinstance(msg, dict):
                    serialized_messages.append(msg)
                else:
                    try:
                        serialized_messages.append(
                            {
                                "type": getattr(msg, "type", "unknown"),
                                "content": getattr(msg, "content", str(msg)),
                                "id": getattr(msg, "id", None),
                                "name": getattr(msg, "name", None),
                            }
                        )
                    except Exception:
                        serialized_messages.append({"content": str(msg)})
            values["messages"] = serialized_messages

        return {
            "values": values,
            "next": [],
            "checkpoint": {
                "thread_id": thread_id,
                "checkpoint_id": checkpoint_tuple.checkpoint.get("id"),
            },
            "metadata": checkpoint_tuple.metadata,
            "created_at": (
                checkpoint_tuple.metadata.get("created_at") if checkpoint_tuple.metadata else None
            ),
            "parent_config": checkpoint_tuple.parent_config,
        }
    except Exception as e:
        logger.error(f"Error getting state for thread {thread_id}: {e}")
        return {**empty_state, "error": str(e)}


@router.patch("/threads/{thread_id}")
async def update_thread(thread_id: str, request: ThreadUpdateRequest) -> Dict:
    """Update a thread."""
    from .store import update_thread_in_store

    t = await update_thread_in_store(thread_id, {"metadata": request.metadata})
    if not t:
        raise HTTPException(status_code=404, detail="Thread not found")
    return t


@router.delete("/threads/{thread_id}")
async def delete_thread(thread_id: str) -> Dict:
    """Delete a thread."""
    from .store import delete_thread_from_store

    if await delete_thread_from_store(thread_id):
        return {"status": "ok"}
    raise HTTPException(status_code=404, detail="Thread not found")
