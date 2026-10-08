"""
Agent interaction routes.

Endpoints: /info, /catalog, /{id}, /invoke, /stream, /feedback, /history.

Handlers only: parse, delegate, respond. The SSE streaming engine behind
/stream lives in ``service/AgentStreamService.py``.
"""

from typing import Annotated, Any

from error_contract import ApplicationError, render_error_message
from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import StreamingResponse
from localization import t

from api.dependencies import AuthenticatedUser, require_permission, require_user
from api.thread_access import require_owned_thread
from core.http.response_errors import request_locale, set_error_response
from core.http.response_models import ErrorModel, ResponseModel
from core.observability.logger import get_logger
from schemas.agent_config_policy import sanitize_client_agent_config
from schemas.agents import (
    AgentCatalogItemResponse,
    AgentCompositionCatalogResponse,
    AgentDetailResponse,
    ServiceMetadata,
)
from schemas.chat import ChatHistory, ChatHistoryInput, ChatMessage, Feedback, StreamInput, UserInput
from service.agents import DEFAULT_AGENT, get_composition_catalog
from service.chat.feedback_service import accept_feedback
from service.orchestration import agent_interaction_service
from service.orchestration.agent_stream_service import message_generator
from service.personas import get_persona_service
from service.stream.error_events import guard_stream

logger = get_logger(__name__)
router = APIRouter(prefix="/agents", tags=["agents"], dependencies=[Depends(require_user)])


@router.get("/info", response_model=ResponseModel[ServiceMetadata])
async def info(
    http_request: Request,
    http_response: Response,
    _user: Annotated[AuthenticatedUser, Depends(require_permission("agent:list"))],
):
    try:
        return ResponseModel(data=await agent_interaction_service.info())
    except ApplicationError as error:
        set_error_response(http_response, error, http_request)
        message = render_error_message(error, locale=request_locale(http_request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.get("/catalog", response_model=ResponseModel[list[AgentCatalogItemResponse]])
async def agent_catalog(
    response: Response,
    request: Request,
    user: Annotated[AuthenticatedUser, Depends(require_permission("persona:read"))],
):
    """Return lightweight product agent summaries for catalog and chat selection."""
    try:
        data = await get_persona_service().get_agent_catalog(user)
        return ResponseModel(data=data)
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.get("/composition/catalog", response_model=ResponseModel[AgentCompositionCatalogResponse])
async def agent_composition_catalog(
    response: Response,
    request: Request,
    _user: Annotated[AuthenticatedUser, Depends(require_permission("persona:read"))],
    kind: str | None = None,
):
    """Return available agent composition components from the canonical catalog.

    Query param ``kind`` filters by component kind:
    brain, perceptron, graph_strategy, runtime_policy.
    When omitted returns all available entries.
    """
    try:
        data = get_composition_catalog(kind)
        return ResponseModel(data=data)
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.get("/{agent_id}", response_model=ResponseModel[AgentDetailResponse])
async def agent_detail(
    agent_id: str,
    response: Response,
    request: Request,
    user: Annotated[AuthenticatedUser, Depends(require_permission("persona:read"))],
):
    """Return full product agent detail for viewer, edit, share, and chat actions."""
    try:
        data = await get_persona_service().get_agent_detail(agent_id, user)
        return ResponseModel(data=data)
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.post("/{agent_id}/invoke", response_model=ResponseModel[ChatMessage])
async def invoke(
    http_request: Request,
    http_response: Response,
    _user: Annotated[AuthenticatedUser, Depends(require_permission("agent:invoke"))],
    user_input: UserInput,
    agent_id: str = DEFAULT_AGENT,
):
    try:
        return ResponseModel(data=await agent_interaction_service.invoke(_user, user_input, agent_id))
    except ApplicationError as error:
        set_error_response(http_response, error, http_request)
        message = render_error_message(error, locale=request_locale(http_request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


def _sse_response_example() -> dict[int | str, Any]:
    return {
        status.HTTP_200_OK: {
            "description": "Server Sent Event Response",
            "content": {
                "text/event-stream": {
                    "example": "data: {'type': 'token', 'content': 'Hello'}\n\ndata: {'type': 'token', 'content': ' World'}\n\ndata: [DONE]\n\n",
                    "schema": {"type": "string"},
                }
            },
        }
    }


@router.post("/{agent_id}/stream", response_class=StreamingResponse, responses=_sse_response_example())
async def stream(
    _user: Annotated[AuthenticatedUser, Depends(require_permission("agent:stream"))],
    user_input: StreamInput,
    agent_id: str = DEFAULT_AGENT,
) -> StreamingResponse:
    """
    Stream an agent's response to a user input, including intermediate messages and tokens.

    If agent_id is not provided, the default agent will be used.
    Use thread_id to persist and continue a multi-turn conversation.
    Set ``stream_tokens=false`` to return intermediate messages but not token-by-token.
    """
    await get_persona_service().authorize_agent_execution(agent_id, _user)
    user_id = _user.user_id
    user_input.agent_config = sanitize_client_agent_config(user_input.agent_config)
    return StreamingResponse(
        guard_stream(message_generator(user_input, agent_id, user_id)), media_type="text/event-stream"
    )


@router.post("/feedback", response_model=ResponseModel[dict[str, str]])
async def feedback(
    feedback: Feedback,
    response: Response,
    request: Request,
    _user: Annotated[AuthenticatedUser, Depends(require_permission("agent:feedback"))],
):
    """Accept feedback for a run."""
    try:
        data = accept_feedback(feedback.run_id, feedback.key)
        return ResponseModel(statusCode=200, message=t("agent.feedback_received"), data=data)
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.post("/history", response_model=ResponseModel[ChatHistory])
async def history(
    http_request: Request,
    http_response: Response,
    input: ChatHistoryInput,
    user: Annotated[AuthenticatedUser, Depends(require_permission("chat:read"))],
):
    try:
        await require_owned_thread(input.thread_id, http_request or http_request, user)
        return ResponseModel(data=await agent_interaction_service.history(input.thread_id))
    except ApplicationError as error:
        set_error_response(http_response, error, http_request)
        message = render_error_message(error, locale=request_locale(http_request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))
