"""
Run routes — SDK-compatible streaming.

POST /threads/{thread_id}/runs/stream
POST /threads/{thread_id}/history

These endpoints power the ``@langchain/langgraph-sdk`` client and
Open Agent Platform's chat interface.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Any
import uuid

from error_contract import ApplicationError
from error_contract.localization import render_error_message
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from localization import t

from api.dependencies import AuthenticatedUser, require_permission, require_user
from api.thread_access import require_owned_thread
from core.http.response_errors import request_locale, set_error_response
from core.http.response_models import ErrorModel, ResponseModel
from core.observability.logger import get_logger
from integrations.user_service_client import get_user_settings
from schemas.runs import RunCancel, RunCancelResponse
from schemas.threads import ThreadHistoryRequest, ThreadRunStreamRequest, ThreadState
from service.agents import get_agent_or_lazy
from service.chat.message_conversion import convert_input_messages
from service.orchestration.agent_runner_coordinator import _looks_like_agent_definition_id
from service.runtime.run_service import RunService, get_run_service
from service.runtime.store_service import get_assistant_from_store
from service.stream.error_events import guard_stream

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)

router = APIRouter(tags=["threads"], dependencies=[Depends(require_user)])


def _get_service() -> RunService:
    """Get the singleton RunService instance."""
    return get_run_service()


# =============================================================================
# Endpoints
# =============================================================================


@router.post(
    "/threads/{thread_id}/runs/stream",
    response_class=StreamingResponse,
    responses={
        200: {
            "content": {"text/event-stream": {"schema": {"type": "string"}}},
            "description": "Stream of agent execution runs (SSE)",
        }
    },
)
async def stream_run(
    request: Request,
    thread_id: str,
    request_obj: ThreadRunStreamRequest,
    user: Annotated[AuthenticatedUser, Depends(require_permission("run:create"))],
) -> StreamingResponse:
    """Stream runs for a thread using SDK-compatible format."""
    logger.debug("stream_run called for thread_id: %s", thread_id)

    await require_owned_thread(thread_id, request, user)

    # The acting user is the authenticated principal, never the body: this id
    # selects memory, the SMTP identity and thread ownership.
    user_id = user.user_id

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

    from memory.memory_flags import resolve_memory_flags

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
    # access_token is deliberately NOT placed in resolved_config: it becomes
    # `configurable` below and is persisted verbatim into checkpoint
    # metadata, which /threads/{id}/state and /threads/{id}/history return
    # to the caller. See the identical note in service/AgentHelpers.py.

    from langchain_core.runnables import RunnableConfig

    run_id = str(uuid.uuid4())
    input_messages = convert_input_messages(request_obj.input or {})
    stream_mode = ["values", "updates", "custom"] if request_obj.stream_tokens else ["values", "updates"]

    config = RunnableConfig(
        configurable=resolved_config,
        tags=(request_obj.stream_tokens and ["stream-tokens"]) or [],
    )

    service = _get_service()
    event_gen = service.event_generator(agent, input_messages, config, thread_id, run_id, stream_mode, user_id)

    return StreamingResponse(guard_stream(event_gen), media_type="text/event-stream")


# =============================================================================
# POST /threads/{thread_id}/runs/{run_id}/cancel
# =============================================================================


@router.post("/threads/{thread_id}/runs/{run_id}/cancel", response_model=ResponseModel[RunCancelResponse])
async def cancel_run_endpoint(
    response: Response,
    thread_id: str,
    run_id: str,
    user: Annotated[AuthenticatedUser, Depends(require_permission("run:cancel"))],
    payload: RunCancel | None = None,
    request: Request = None,
) -> ResponseModel[Any]:
    try:
        "Cancel an active run."
        await require_owned_thread(thread_id, request, user)
        logger.info("cancel_run_endpoint called for thread_id=%s, run_id=%s, payload=%s", thread_id, run_id, payload)
        service = _get_service()
        return ResponseModel(data=await service.cancel_run(thread_id, run_id))
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


# =============================================================================
# POST /threads/{thread_id}/history
# =============================================================================


@router.post("/threads/{thread_id}/history", response_model=ResponseModel[list[ThreadState]])
async def get_thread_history(
    response: Response,
    thread_id: str,
    body: ThreadHistoryRequest,
    user: Annotated[AuthenticatedUser, Depends(require_permission("run:read"))],
    request: Request = None,
) -> ResponseModel[Any]:
    try:
        "Get thread history specific checkpointer states."
        await require_owned_thread(thread_id, request, user)
        service = _get_service()
        return ResponseModel(data=await service.get_thread_history(thread_id, body.limit, body.before))
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))
