"""
Agent interaction routes.

Endpoints: /info, /invoke, /stream, /feedback, /history
plus the ``message_generator`` streaming helper.
"""

import inspect
import json
import logging
import re
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, AIMessageChunk, AnyMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.types import Interrupt

from agents import DEFAULT_AGENT, AgentGraph, get_agent, get_all_agent_info
from service.AssistantAgentService import AssistantAgentService
from core import settings
from schema import (
    ChatHistory,
    ChatHistoryInput,
    ChatMessage,
    Feedback,
    FeedbackResponse,
    ServiceMetadata,
    StreamInput,
    UserInput,
)
from service.AgentHelpers import _handle_input
from service.AuthService import extract_user_id_from_token, verify_bearer
from service.Utils import (
    convert_message_content_to_string,
    langchain_to_chat_message,
    remove_tool_calls,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agents", tags=["agents"], dependencies=[Depends(verify_bearer)])


# =============================================================================
# /info
# =============================================================================


@router.get("/info")
async def info() -> ServiceMetadata:
    from core.providers.registry import provider_registry

    provider_registry.initialize()
    all_models = await provider_registry.get_model_names()
    all_models.sort()

    # Determine default model
    default_model = settings.DEFAULT_MODEL or None
    if not default_model and all_models:
        default_model = all_models[0]

    return ServiceMetadata(
        agents=get_all_agent_info(),
        models=all_models,
        default_agent=DEFAULT_AGENT,
        default_model=default_model or "fake",
    )


# =============================================================================
# /invoke
# =============================================================================


@router.post("/{agent_id}/invoke", operation_id="invoke_with_agent_id")
@router.post("/invoke")
async def invoke(
    request: Request,
    user_input: UserInput,
    agent_id: str = DEFAULT_AGENT,
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
            output = langchain_to_chat_message(
                AIMessage(content=response["__interrupt__"][0].value)
            )
        else:
            raise ValueError(f"Unexpected response type: {response_type}")

        output.run_id = str(run_id)
        return output
    except Exception as e:
        logger.error(f"An exception occurred: {e}")
        raise HTTPException(status_code=500, detail="Unexpected error")


# =============================================================================
# /stream  (SSE)
# =============================================================================


async def message_generator(
    user_input: StreamInput,
    agent_id: str = DEFAULT_AGENT,
    user_id: str | None = None,
) -> AsyncGenerator[str, None]:
    """
    Generate a stream of messages from the agent.

    This is the workhorse method for the /stream endpoint.
    """
    import logging

    logger = logging.getLogger(__name__)

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
        async for stream_event in agent.astream(
            **kwargs, stream_mode=["updates", "messages", "custom"], subgraphs=True
        ):
            if not isinstance(stream_event, tuple):
                continue

            if len(stream_event) == 3:
                _, stream_mode, event = stream_event
            else:
                stream_mode, event = stream_event

            new_messages: list = []
            if stream_mode == "updates":
                for node, updates in event.items():
                    if node == "__interrupt__":
                        interrupt: Interrupt
                        for interrupt in updates:
                            new_messages.append(AIMessage(content=interrupt.value))
                        continue
                    updates = updates or {}
                    update_messages = updates.get("messages", [])

                    if not update_messages:
                        continue

                    if "supervisor" in node or "sub-agent" in node:
                        filtered_messages = []
                        for msg in update_messages:
                            if (
                                isinstance(msg, AIMessage)
                                and hasattr(msg, "tool_calls")
                                and msg.tool_calls
                            ):
                                filtered_messages.append(msg)
                            elif isinstance(msg, ToolMessage):
                                filtered_messages.append(msg)
                            elif isinstance(msg, AIMessage) and msg.content:
                                filtered_messages.append(msg)
                        update_messages = filtered_messages

                    new_messages.extend(update_messages)

            if stream_mode == "custom":
                new_messages = [event]

            processed_messages: list = []
            current_message: dict[str, Any] = {}
            for message in new_messages:
                if isinstance(message, tuple):
                    key, value = message
                    current_message[key] = value
                else:
                    if current_message:
                        processed_messages.append(_create_ai_message(current_message))
                        current_message = {}
                    processed_messages.append(message)

            if current_message:
                processed_messages.append(_create_ai_message(current_message))

            for message in processed_messages:
                try:
                    chat_message = langchain_to_chat_message(message)
                    chat_message.run_id = str(run_id)
                except Exception as e:
                    logger.error(f"Error parsing message: {e}")
                    yield f"data: {json.dumps({'type': 'error', 'content': 'Unexpected error'})}\n\n"
                    continue

                if chat_message.type == "human" and chat_message.content == user_input.message:
                    continue

                # Emit tool call lifecycle packets for frontend timeline
                # Skip the regular 'message' yield for tool-related messages
                # so they only appear in the timeline, not duplicated in chat
                if chat_message.type == "ai" and chat_message.tool_calls:
                    for tc in chat_message.tool_calls:
                        yield f"data: {json.dumps({'type': 'custom_tool_start', 'tool_name': tc.get('name', 'tool')})}\n\n"
                    continue
                elif chat_message.type == "tool":
                    tool_name = getattr(message, "name", "") or ""
                    yield f"data: {json.dumps({'type': 'custom_tool_delta', 'tool_name': tool_name, 'response_type': 'tool_result', 'data': chat_message.content})}\n\n"
                    continue

                # Strip <think>/<thinking> tags from AI responses
                if chat_message.type == "ai" and chat_message.content:
                    cleaned = re.sub(r"<think>.*?</think>", "", chat_message.content, flags=re.DOTALL)
                    cleaned = re.sub(r"<thinking>.*?</thinking>", "", cleaned, flags=re.DOTALL)
                    cleaned = re.sub(r"<think>(?:(?!</think>).)*$", "", cleaned, flags=re.DOTALL)
                    cleaned = re.sub(r"<thinking>(?:(?!</thinking>).)*$", "", cleaned, flags=re.DOTALL)
                    chat_message.content = cleaned.strip()
                    if not chat_message.content:
                        continue

                yield f"data: {json.dumps({'type': 'message', 'content': chat_message.model_dump()})}\n\n"

            if stream_mode == "messages":
                if not user_input.stream_tokens:
                    continue
                msg, metadata = event
                if "skip_stream" in metadata.get("tags", []):
                    continue
                if not isinstance(msg, AIMessageChunk):
                    continue
                content = remove_tool_calls(msg.content)
                if content:
                    token_str = convert_message_content_to_string(content)
                    # Strip <think>/<thinking> tags from streaming tokens
                    token_str = re.sub(r"<think>.*?</think>", "", token_str, flags=re.DOTALL)
                    token_str = re.sub(r"<thinking>.*?</thinking>", "", token_str, flags=re.DOTALL)
                    token_str = re.sub(r"<think>(?:(?!</think>).)*$", "", token_str, flags=re.DOTALL)
                    token_str = re.sub(r"<thinking>(?:(?!</thinking>).)*$", "", token_str, flags=re.DOTALL)
                    if token_str.strip():
                        yield f"data: {json.dumps({'type': 'token', 'content': token_str})}\n\n"
    except Exception as e:
        import traceback

        logger.error("Error in message generator: %s\n%s", e, traceback.format_exc())
        yield f"data: {json.dumps({'type': 'error', 'content': 'Internal server error'})}\n\n"
    finally:
        yield "data: [DONE]\n\n"


def _create_ai_message(parts: dict) -> AIMessage:
    sig = inspect.signature(AIMessage)
    valid_keys = set(sig.parameters)
    filtered = {k: v for k, v in parts.items() if k in valid_keys}
    return AIMessage(**filtered)


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


# @router.post("/feedback")
# async def feedback(feedback: Feedback) -> FeedbackResponse:
#     """Record feedback for a run to LangSmith."""
#     client = LangsmithClient()
#     kwargs = feedback.kwargs or {}
#     client.create_feedback(
#         run_id=feedback.run_id,
#         key=feedback.key,
#         score=feedback.score,
#         **kwargs,
#     )
#     return FeedbackResponse()


@router.post("/history")
async def history(input: ChatHistoryInput) -> ChatHistory:
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
