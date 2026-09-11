"""
Run routes — SDK-compatible streaming.

POST /threads/{thread_id}/runs/stream
POST /threads/{thread_id}/history

These endpoints power the ``@langchain/langgraph-sdk`` client and
Open Agent Platform's chat interface.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from i18n import t

from agents import get_agent_or_lazy
from api.dependencies import require_permission, require_user
from controller import RunController, get_run_controller
from core.logger import get_logger
from models.threads import ThreadHistoryRequest, ThreadState
from service.AgentHelpers import _looks_like_agent_definition_id
from service.AuthService import extract_user_id_from_token
from service.message_conversion import convert_input_messages
from service.StoreService import get_assistant_from_store
from service.UserServiceClient import get_user_settings

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)

router = APIRouter(tags=["threads"], dependencies=[Depends(require_user)])


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
    user_id: str | None = None


async def _parse_input(request: Request) -> tuple[dict, str, str, str | None, str]:
    """Parse request body and extract relevant fields."""
    try:
        body = await request.json()
    except Exception:
        body = {}

    user_input = body.get("input", {})
    if isinstance(user_input, str):
        user_input = {"messages": [{"type": "human", "content": user_input}]}

    model = body.get("model")
    thread_id = body.get("thread_id", "")
    run_id = str(uuid.uuid4())

    api_key = request.headers.get("x-api-key")
    user_id = extract_user_id_from_token(api_key) if api_key else None

    return user_input, thread_id, run_id, model, user_id


@router.post("/threads/{thread_id}/runs/stream")
async def stream_run(
    request: Request,
    thread_id: str,
    request_obj: StreamInput,
    _user=Depends(require_permission("run:create")),
) -> StreamingResponse:
    """Stream runs for a thread using SDK-compatible format."""
    logger.debug("stream_run called for thread_id: %s", thread_id)

    # Extract user_id from request body first, then fall back to x-api-key header
    user_id = request_obj.user_id
    if not user_id:
        api_key = request.headers.get("x-api-key")
        user_id = extract_user_id_from_token(api_key) if api_key else None

    stored = None
    assistant_id = request_obj.assistant_id
    if not assistant_id:
        stored = await get_assistant_from_store(thread_id)
        assistant_id = stored.get("assistant_id") if stored else None

    if not assistant_id:
        logger.debug("No stored assistant found")
        raise HTTPException(status_code=400, detail=t("run.assistant_id_required"))

    agent = get_agent_or_lazy(assistant_id)
    logger.debug("stream_run: Got agent type: %s", type(agent).__name__)

    assistant_config: dict[str, Any] = {}
    stored_assistant = await get_assistant_from_store(assistant_id)
    if stored_assistant:
        assistant_config = stored_assistant.get("config", {}) or {}

    # The user's personalization settings are the master switch for memory
    # (see service.memory_flags). An assistant "participates" when it opts in
    # via config/memory_type or when it is a builtin/default assistant (not a
    # dynamic AgentDefinition), in which case the user setting alone drives it.
    user_recall_enabled = False
    user_extract_enabled = True
    if user_id:
        try:
            user_settings = await get_user_settings(user_id)
            user_recall_enabled = bool(user_settings.get("long_term_memory_enabled", False))
            user_extract_enabled = bool(user_settings.get("extract_memory", True))
        except Exception as exc:
            logger.debug("stream_run: failed to load user LTM settings for %s: %s", user_id, exc)

    agent_participates = (
        bool(assistant_config.get("long_term_memory", False))
        or assistant_config.get("memory_type") == "long_term"
        or not _looks_like_agent_definition_id(assistant_id)
    )

    from service.memory_flags import resolve_memory_flags

    long_term_memory, extract_memory = resolve_memory_flags(
        user_recall_enabled=user_recall_enabled,
        user_extract_enabled=user_extract_enabled,
        agent_participates=agent_participates,
    )

    resolved_config: dict[str, Any] = dict(assistant_config)
    resolved_config.update(
        {
            "thread_id": thread_id,
            "user_id": user_id,
            "model": request_obj.model or assistant_config.get("model") or "ollama",
            "long_term_memory": long_term_memory,
            "extract_memory": extract_memory,
        }
    )
    try:
        from service.UserServiceClient import get_current_access_token

        access_token = get_current_access_token()
        if access_token:
            resolved_config["access_token"] = access_token
    except Exception:
        pass

    from langchain_core.runnables import RunnableConfig

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
    event_gen = ctrl.event_generator(
        agent, input_messages, config, thread_id, run_id, stream_mode, user_id
    )

    return StreamingResponse(event_gen, media_type="text/event-stream")


# =============================================================================
# POST /threads/{thread_id}/runs/{run_id}/cancel
# =============================================================================


@router.post("/threads/{thread_id}/runs/{run_id}/cancel")
async def cancel_run_endpoint(
    thread_id: str,
    run_id: str,
    _user=Depends(require_permission("run:cancel")),
) -> dict:
    """Cancel an active run."""
    logger.info("cancel_run_endpoint called for thread_id=%s, run_id=%s", thread_id, run_id)
    ctrl = _get_controller()
    return await ctrl.cancel_run(thread_id, run_id)


# =============================================================================
# POST /threads/{thread_id}/history
# =============================================================================


@router.post("/threads/{thread_id}/history")
async def get_thread_history(
    thread_id: str,
    request: ThreadHistoryRequest,
    _user=Depends(require_permission("run:read")),
) -> list[ThreadState]:
    """Get thread history specific checkpointer states."""
    ctrl = _get_controller()
    return await ctrl.get_thread_history(thread_id, request.limit, request.before)
