"""
Run routes — SDK-compatible streaming.

POST /threads/{thread_id}/runs/stream
POST /threads/{thread_id}/history

These endpoints power the ``@langchain/langgraph-sdk`` client and
Open Agent Platform's chat interface.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from agents import get_agent_or_lazy
from controller import RunController, get_run_controller
from core.logger import get_logger
from service.AuthService import extract_user_id_from_token, verify_bearer
from service.UserServiceClient import get_user_settings
from service.Schemas import ThreadHistoryRequest, ThreadState
from service.Utils import convert_input_messages

if TYPE_CHECKING:
    from langchain_core.runnables import RunnableConfig

logger = get_logger(__name__)

router = APIRouter(tags=["threads"], dependencies=[Depends(verify_bearer)])


def _get_controller() -> RunController:
    """Get the singleton RunController instance."""
    return get_run_controller()


# =============================================================================
# Endpoints
# =============================================================================


@dataclass
class StreamInput:
    """Schema for stream input."""

    assistant_id: str | None = None
    input: dict | None = None
    model: str | None = None
    stream_tokens: bool = True


async def _parse_input(request: Request) -> tuple[dict, str, str, str | None, str]:
    """Parse request body and extract relevant fields."""
    try:
        body = await request.json()
    except Exception:
        body = {}

    assistant_id = body.get("assistant_id")
    user_input = body.get("input", {})
    if isinstance(user_input, str):
        user_input = {"messages": [{"type": "human", "content": user_input}]}

    model = body.get("model")
    thread_id = body.get("thread_id", "")
    run_id = str(uuid_module.uuid4())

    api_key = request.headers.get("x-api-key")
    user_id = extract_user_id_from_token(api_key) if api_key else None

    return user_input, thread_id, run_id, model, user_id


@router.post("/threads/{thread_id}/runs/stream")
async def stream_run(
    request: Request, thread_id: str, request_obj: StreamInput
) -> StreamingResponse:
    """Stream runs for a thread using SDK-compatible format."""
    logger.debug("stream_run called for thread_id: %s", thread_id)

    api_key = request.headers.get("x-api-key")
    user_id = extract_user_id_from_token(api_key) if api_key else None

    stored = None
    assistant_id = request_obj.assistant_id
    if not assistant_id:
        from service.StoreService import get_assistant_from_store

        stored = await get_assistant_from_store(thread_id)
        assistant_id = stored.get("assistant_id") if stored else None

    if not assistant_id:
        logger.debug("No stored assistant found")
        raise HTTPException(status_code=400, detail="assistant_id is required")

    agent = get_agent_or_lazy(assistant_id)
    logger.debug("stream_run: Got agent type: %s", type(agent).__name__)

    assistant_config: dict[str, Any] = {}
    stored_assistant = await get_assistant_from_store(assistant_id)
    if stored_assistant:
        assistant_config = stored_assistant.get("config", {}) or {}

    user_ltm_enabled = False
    agent_ltm_enabled = bool(assistant_config.get("long_term_memory", False))
    if user_id:
        try:
            user_settings = await get_user_settings(user_id)
            user_ltm_enabled = bool(user_settings.get("long_term_memory_enabled", False))
        except Exception as exc:
            logger.debug("stream_run: failed to load user LTM settings for %s: %s", user_id, exc)

    resolved_config: dict[str, Any] = dict(assistant_config)
    resolved_config.update(
        {
            "thread_id": thread_id,
            "user_id": user_id,
            "model": request_obj.model or assistant_config.get("model") or "ollama",
            "long_term_memory": user_ltm_enabled and agent_ltm_enabled,
        }
    )

    from langchain_core.runnables import RunnableConfig
    import uuid

    run_id = str(uuid.uuid4())
    input_messages = convert_input_messages(request_obj.input or {})
    stream_mode = (
        ["values", "updates", "custom"] if request_obj.stream_tokens else ["values", "updates"]
    )

    config = RunnableConfig(
        configurable=resolved_config,
        tags=request_obj.stream_tokens and ["stream-tokens"] or [],
    )

    ctrl = _get_controller()
    event_gen = ctrl.event_generator(agent, input_messages, config, thread_id, run_id, stream_mode, user_id)

    return StreamingResponse(event_gen, media_type="text/event-stream")


# =============================================================================
# POST /threads/{thread_id}/runs/{run_id}/cancel
# =============================================================================


@router.post("/threads/{thread_id}/runs/{run_id}/cancel")
async def cancel_run_endpoint(thread_id: str, run_id: str) -> dict:
    """Cancel an active run."""
    logger.info("cancel_run_endpoint called for thread_id=%s, run_id=%s", thread_id, run_id)
    ctrl = _get_controller()
    return await ctrl.cancel_run(thread_id, run_id)


# =============================================================================
# POST /threads/{thread_id}/history
# =============================================================================


@router.post("/threads/{thread_id}/history")
async def get_thread_history(thread_id: str, request: ThreadHistoryRequest) -> list[ThreadState]:
    """Get thread history specific checkpointer states."""
    ctrl = _get_controller()
    return await ctrl.get_thread_history(thread_id, request.limit, request.before)
