"""
Agent interaction routes.

Endpoints: /info, /catalog, /{id}, /invoke, /stream, /feedback, /history.

Handlers only: parse, delegate, respond. The SSE streaming engine behind
/stream lives in ``service/AgentStreamService.py``.
"""

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from i18n import t
from langchain_core.messages import AIMessage, AnyMessage
from langchain_core.runnables import RunnableConfig

from agent_composition import ComponentKind, list_available
from agents import DEFAULT_AGENT, AgentGraph, get_agent, get_all_agent_info
from api.dependencies import AuthenticatedUser, require_permission, require_user
from controller import get_persona_controller
from core import settings
from core.logger import get_logger
from models.agents import ServiceMetadata
from models.chat import (
    ChatHistory,
    ChatHistoryInput,
    ChatMessage,
    Feedback,
    FeedbackResponse,
    StreamInput,
    UserInput,
)
from service.AgentHelpers import _handle_input
from service.AgentStreamService import message_generator
from service.AssistantAgentService import AssistantAgentService
from service.AuthService import extract_user_id_from_token
from service.message_conversion import langchain_to_chat_message

logger = get_logger(__name__)

router = APIRouter(prefix="/agents", tags=["agents"], dependencies=[Depends(require_user)])


# =============================================================================
# /info
# =============================================================================


@router.get("/info")
async def info(_user=Depends(require_permission("agent:list"))) -> ServiceMetadata:
    from core.providers.registry import provider_registry

    provider_registry.initialize()
    all_models = await provider_registry.get_model_names()
    all_models.sort()

    # Determine default model
    default_model = settings.DEFAULT_MODEL or None
    if default_model and default_model.lower() in {"ollama", "default", "provider", "builtin"}:
        default_model = settings.OLLAMA_MODEL or "llama3.1:8b"
    if (not default_model or default_model not in all_models) and all_models:
        default_model = all_models[0]

    return ServiceMetadata(
        agents=get_all_agent_info(),
        models=all_models,
        default_agent=DEFAULT_AGENT,
        default_model=default_model or "fake",
    )


# =============================================================================
# Product agent catalog
# =============================================================================


@router.get("/catalog")
async def agent_catalog(
    user: AuthenticatedUser = Depends(require_permission("persona:read")),
) -> list[dict[str, Any]]:
    """Return lightweight product agent summaries for catalog and chat selection."""
    return await get_persona_controller().get_agent_catalog(user)


@router.get("/composition/catalog")
async def agent_composition_catalog(
    _user: AuthenticatedUser = Depends(require_permission("persona:read")),
    kind: str | None = None,
) -> dict[str, Any]:
    """Return available agent composition components from the canonical catalog.

    Query param ``kind`` filters by component kind:
    brain, perceptron, graph_strategy, runtime_policy.
    When omitted returns all available entries.
    """
    component_kind: ComponentKind | None = ComponentKind(kind) if kind else None
    return {
        "components": list_available(component_kind),
        "kinds": [k.value for k in ComponentKind],
    }


@router.get("/{agent_id}")
async def agent_detail(
    agent_id: str,
    user: AuthenticatedUser = Depends(require_permission("persona:read")),
) -> dict[str, Any]:
    """Return full product agent detail for viewer, edit, share, and chat actions."""
    return await get_persona_controller().get_agent_detail(agent_id, user)


# =============================================================================
# /invoke
# =============================================================================


@router.post("/{agent_id}/invoke", operation_id="invoke_with_agent_id")
@router.post("/invoke")
async def invoke(
    request: Request,
    user_input: UserInput,
    agent_id: str = DEFAULT_AGENT,
    _user=Depends(require_permission("agent:invoke")),
) -> ChatMessage:
    """
    Invoke an agent with user input to retrieve a final response.

    If agent_id is not provided, the default agent will be used.
    Use thread_id to persist and continue a multi-turn conversation. run_id kwarg
    is also attached to messages for recording feedback.
    Use user_id to persist and continue a conversation across multiple threads.

    The user_id can also be automatically extracted from the x-api-key header.
    """
    api_key = request.headers.get("x-api-key")
    user_id = extract_user_id_from_token(api_key) if api_key else None

    service = AssistantAgentService.get_instance()
    _, stored_config = await service.get_graph_and_config(agent_id)
    if stored_config:
        final_config = stored_config.copy()
        if user_input.agent_config:
            final_config.update(user_input.agent_config)
        user_input.agent_config = final_config

    agent = await service.get_configured_agent(agent_id, user_input.agent_config or {})
    kwargs, run_id = await _handle_input(user_input, agent, user_id)

    try:
        response_events: list[tuple[str, Any]] = await agent.ainvoke(
            **kwargs, stream_mode=["updates", "values"]
        )  # type: ignore
        response_type, response = response_events[-1]
        if response_type == "values":
            output = langchain_to_chat_message(response["messages"][-1])
        elif response_type == "updates" and "__interrupt__" in response:
            _interrupt_value = response["__interrupt__"][0].value
            output = langchain_to_chat_message(
                AIMessage(
                    content=_interrupt_value
                    if isinstance(_interrupt_value, str)
                    else json.dumps(_interrupt_value)
                )
            )
        else:
            raise ValueError(f"Unexpected response type: {response_type}")

        output.run_id = str(run_id)
        return output
    except Exception as e:
        logger.error(f"An exception occurred: {e}")
        raise HTTPException(status_code=500, detail=t("agent.unexpected_error"))


# =============================================================================
# /stream  (SSE)
# =============================================================================


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


@router.post(
    "/{agent_id}/stream",
    response_class=StreamingResponse,
    responses=_sse_response_example(),
    operation_id="stream_with_agent_id",
)
@router.post("/stream", response_class=StreamingResponse, responses=_sse_response_example())
async def stream(
    request: Request,
    user_input: StreamInput,
    agent_id: str = DEFAULT_AGENT,
    _user=Depends(require_permission("agent:stream")),
) -> StreamingResponse:
    """
    Stream an agent's response to a user input, including intermediate messages and tokens.

    If agent_id is not provided, the default agent will be used.
    Use thread_id to persist and continue a multi-turn conversation.
    Set ``stream_tokens=false`` to return intermediate messages but not token-by-token.
    """
    api_key = request.headers.get("x-api-key")
    user_id = extract_user_id_from_token(api_key) if api_key else None

    return StreamingResponse(
        message_generator(user_input, agent_id, user_id),
        media_type="text/event-stream",
    )


# =============================================================================
# /feedback & /history
# =============================================================================


@router.post("/feedback")
async def feedback(
    feedback: Feedback,
    _user=Depends(require_permission("agent:feedback")),
) -> FeedbackResponse:
    """Accept feedback for a run."""
    logger.info("Feedback received for run %s with key %s", feedback.run_id, feedback.key)
    return FeedbackResponse(status="success")


@router.post("/history")
async def history(
    input: ChatHistoryInput,
    _user=Depends(require_permission("chat:read")),
) -> ChatHistory:
    """Get chat history."""
    agent: AgentGraph = get_agent(DEFAULT_AGENT)
    try:
        state_snapshot = await agent.aget_state(
            config=RunnableConfig(configurable={"thread_id": input.thread_id})
        )
        messages: list[AnyMessage] = state_snapshot.values["messages"]
        chat_messages: list[ChatMessage] = [langchain_to_chat_message(m) for m in messages]
        return ChatHistory(messages=chat_messages)
    except Exception as e:
        logger.error(f"An exception occurred: {e}")
        raise HTTPException(status_code=500, detail=t("agent.unexpected_error"))
