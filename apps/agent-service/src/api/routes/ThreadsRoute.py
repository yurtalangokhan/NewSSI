"""
Thread CRUD routes.

Endpoints: POST /threads/search, POST /threads, GET /threads/{id},
GET /threads/{id}/state, PATCH /threads/{id}, DELETE /threads/{id}
"""

import asyncio
import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException

from controller import ThreadController, get_thread_controller
from service.CheckpointerService import get_checkpointer
from service.Schemas import (
    ThreadCreateRequest,
    ThreadSearchRequest,
    ThreadUpdateRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/threads", tags=["threads"])


def _get_controller() -> ThreadController:
    return get_thread_controller()


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


@router.post("/search")
async def search_threads(
    request: ThreadSearchRequest = ThreadSearchRequest(),
) -> list[dict]:
    """Search / List threads."""
    ctrl = _get_controller()
    threads = await ctrl.list_threads(request.limit, request.offset, request.metadata)

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


@router.post("")
async def create_thread(request: ThreadCreateRequest) -> dict:
    """Create a new thread."""
    return await _get_controller().create_thread(
        thread_id=request.thread_id,
        metadata=request.metadata,
    )


@router.get("/{thread_id}")
async def get_thread(thread_id: str) -> dict:
    """Get a thread."""
    t = await _get_controller().get_thread(thread_id)
    if not t:
        raise HTTPException(status_code=404, detail="Thread not found")
    return t


@router.get("/{thread_id}/state")
async def get_thread_state(thread_id: str) -> dict:
    """
    Get thread state including messages.
    Compatible with @langchain/langgraph-sdk client.threads.getState()
    """
    return await _get_controller().get_thread_state(thread_id)


@router.patch("/{thread_id}")
async def update_thread(thread_id: str, request: ThreadUpdateRequest) -> dict:
    """Update a thread."""
    t = await _get_controller().update_thread(thread_id, request.metadata)
    if not t:
        raise HTTPException(status_code=404, detail="Thread not found")
    return t


@router.delete("/{thread_id}")
async def delete_thread(thread_id: str) -> dict:
    """Delete a thread."""
    if await _get_controller().delete_thread(thread_id):
        return {"status": "ok"}
    raise HTTPException(status_code=404, detail="Thread not found")
