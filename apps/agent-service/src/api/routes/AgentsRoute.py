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
from api.dependencies import require_permission, require_user
from core import settings
from schema import (
    ChatHistory,
    ChatHistoryInput,
    ChatMessage,
    ServiceMetadata,
    StreamInput,
    UserInput,
)
from service.AgentHelpers import _handle_input
from service.AssistantAgentService import AssistantAgentService
from service.AuthService import extract_user_id_from_token
from service.Utils import (
    convert_message_content_to_string,
    langchain_to_chat_message,
    remove_tool_calls,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agents", tags=["agents"], dependencies=[Depends(require_user)])


class ThinkingTagProcessor:
    """Tag-based thinking models (<think>...</think>) için streaming state machine."""

    OPEN_TAGS = ("<thinking>", "<think>")
    CLOSE_TAGS = ("</thinking>", "</think>")
    MAX_TAG_LEN = max(len(t) for t in OPEN_TAGS + CLOSE_TAGS)  # = 11

    def __init__(self):
        self.in_thinking = False
        self.reasoning_started = False
        self.buffer = ""

    def feed(self, text: str) -> list[dict]:
        self.buffer += text
        events: list[dict] = []

        while self.buffer:
            if not self.in_thinking:
                pos, tag = self._find_tag(self.buffer, self.OPEN_TAGS)
                if pos is not None:
                    if pos > 0:
                        events.append({"type": "token", "content": self.buffer[:pos]})
                    if not self.reasoning_started:
                        events.append({"type": "reasoning_start"})
                        self.reasoning_started = True
                    self.in_thinking = True
                    self.buffer = self.buffer[pos + len(tag):]
                else:
                    safe_len = max(0, len(self.buffer) - self.MAX_TAG_LEN)
                    if safe_len > 0:
                        events.append({"type": "token", "content": self.buffer[:safe_len]})
                        self.buffer = self.buffer[safe_len:]
                    break
            else:
                pos, tag = self._find_tag(self.buffer, self.CLOSE_TAGS)
                if pos is not None:
                    if pos > 0:
                        events.append({"type": "reasoning_delta", "reasoning": self.buffer[:pos]})
                    self.in_thinking = False
                    self.buffer = self.buffer[pos + len(tag):]
                else:
                    safe_len = max(0, len(self.buffer) - self.MAX_TAG_LEN)
                    if safe_len > 0:
                        events.append({"type": "reasoning_delta", "reasoning": self.buffer[:safe_len]})
                        self.buffer = self.buffer[safe_len:]
                    break

        return events

    def flush(self) -> list[dict]:
        """Stream bitişinde kalan buffer'ı emit et."""
        if not self.buffer:
            return []
        t = "reasoning_delta" if self.in_thinking else "token"
        key = "reasoning" if self.in_thinking else "content"
        event = {"type": t, key: self.buffer}
        self.buffer = ""
        return [event]

    @staticmethod
    def _find_tag(text: str, tags: tuple) -> tuple:
        best_pos, best_tag = None, None
        for tag in tags:
            pos = text.find(tag)
            if pos != -1 and (best_pos is None or pos < best_pos):
                best_pos, best_tag = pos, tag
        return best_pos, best_tag


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

    # Detect DynamicAgent so we can emit step events per meaningful node.
    from agents.dynamic_agent import DynamicAgent

    is_dynamic_agent = isinstance(agent, DynamicAgent)
    # Infrastructure nodes that should NOT produce step events
    _INFRA_NODES = frozenset({"__interrupt__", "__end__", "tools", "agent"})

    kwargs, run_id = await _handle_input(user_input, agent, user_id)

    thinking_processor = ThinkingTagProcessor()
    saw_reasoning_for_current_answer = False
    # Track the first LLM call's message ID so that subsequent LLM calls
    # (e.g. background memory extraction) don't emit tokens to the stream.
    first_llm_call_id: str | None = None
    saw_visible_answer_tokens = False

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

                    # Emit step-start event for DynamicAgent non-infrastructure nodes
                    if is_dynamic_agent and node not in _INFRA_NODES:
                        yield f"data: {json.dumps({'type': 'custom_step_start', 'step_name': node})}\n\n"

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
                # Intercept long-term memory custom events (emitted by get_stream_writer)
                if isinstance(message, dict):
                    msg_type = message.get("type", "")
                    if msg_type in ("long_term_memory_recall", "long_term_memory_save"):
                        yield f"data: {json.dumps(message)}\n\n"
                        continue

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
                    # New tool phase: allow post-tool model call tokens/reasoning through.
                    first_llm_call_id = None
                    saw_visible_answer_tokens = False
                    saw_reasoning_for_current_answer = False
                    for tc in chat_message.tool_calls:
                        yield f"data: {json.dumps({'type': 'custom_tool_start', 'tool_name': tc.get('name', 'tool')})}\n\n"
                    continue
                elif chat_message.type == "tool":
                    tool_name = getattr(message, "name", "") or ""
                    # Keep subsequent assistant phase visible even when prior phase streamed tokens.
                    saw_visible_answer_tokens = False
                    saw_reasoning_for_current_answer = False
                    yield f"data: {json.dumps({'type': 'custom_tool_delta', 'tool_name': tool_name, 'response_type': 'tool_result', 'data': chat_message.content})}\n\n"
                    continue

                # Some providers do not stream reasoning chunks and only attach
                # reasoning to final AI message metadata. Emit fallback packets so
                # live timeline matches refresh reconstruction behavior.
                if chat_message.type == "ai" and not saw_reasoning_for_current_answer:
                    final_reasoning = _extract_reasoning_text_from_message(message)
                    if final_reasoning:
                        yield f"data: {json.dumps({'type': 'reasoning_start'})}\n\n"
                        yield f"data: {json.dumps({'type': 'reasoning_delta', 'reasoning': final_reasoning})}\n\n"
                        saw_reasoning_for_current_answer = True

                # When token streaming is enabled, the frontend already receives
                # the assistant answer incrementally via `token` packets.
                # Emitting the final full `message` packet as well causes the UI
                # to render the full answer and then animate tokens on top of it.
                if chat_message.type == "ai" and user_input.stream_tokens and saw_visible_answer_tokens:
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

                # Filter out tokens from secondary LLM calls (e.g. memory extraction).
                # Each model.ainvoke() produces AIMessageChunks with a unique `id`.
                # We only stream tokens from the first (main response) call.
                msg_id = getattr(msg, "id", None)
                if msg_id:
                    if first_llm_call_id is None:
                        first_llm_call_id = msg_id
                    elif msg_id != first_llm_call_id:
                        continue

                content = remove_tool_calls(msg.content)
                reasoning_text = _extract_reasoning_text(msg)
                if not content and not reasoning_text:
                    continue

                # Anthropic extended thinking: content list'te "thinking" type block'lar
                if isinstance(content, list):
                    emitted_reasoning = False
                    for block in content:
                        if not isinstance(block, dict):
                            continue
                        btype = block.get("type")
                        if btype == "thinking":
                            # Anthropic extended thinking block
                            thinking_text = block.get("thinking", "")
                            if thinking_text:
                                if not saw_reasoning_for_current_answer:
                                    yield f"data: {json.dumps({'type': 'reasoning_start'})}\n\n"
                                    saw_reasoning_for_current_answer = True
                                yield f"data: {json.dumps({'type': 'reasoning_delta', 'reasoning': thinking_text})}\n\n"
                                emitted_reasoning = True
                        elif btype == "text" and block.get("thought"):
                            # Google Gemini thought block (thought=True in content part)
                            thought_text = block.get("text", "")
                            if thought_text:
                                if not saw_reasoning_for_current_answer:
                                    yield f"data: {json.dumps({'type': 'reasoning_start'})}\n\n"
                                    saw_reasoning_for_current_answer = True
                                yield f"data: {json.dumps({'type': 'reasoning_delta', 'reasoning': thought_text})}\n\n"
                                emitted_reasoning = True
                        elif btype == "text":
                            text = block.get("text", "")
                            if text:
                                saw_visible_answer_tokens = True
                                yield f"data: {json.dumps({'type': 'token', 'content': text})}\n\n"
                    if reasoning_text and not emitted_reasoning:
                        if not saw_reasoning_for_current_answer:
                            yield f"data: {json.dumps({'type': 'reasoning_start'})}\n\n"
                            saw_reasoning_for_current_answer = True
                        yield f"data: {json.dumps({'type': 'reasoning_delta', 'reasoning': reasoning_text})}\n\n"
                else:
                    # Tag tabanlı modeller (DeepSeek, Qwen vb.)
                    token_str = convert_message_content_to_string(content)
                    if token_str:
                        for evt in thinking_processor.feed(token_str):
                            if evt.get("type") == "token" and evt.get("content"):
                                saw_visible_answer_tokens = True
                            yield f"data: {json.dumps(evt)}\n\n"
                    elif reasoning_text:
                        if not saw_reasoning_for_current_answer:
                            yield f"data: {json.dumps({'type': 'reasoning_start'})}\n\n"
                            saw_reasoning_for_current_answer = True
                        yield f"data: {json.dumps({'type': 'reasoning_delta', 'reasoning': reasoning_text})}\n\n"

    except Exception as e:
        import traceback

        logger.error("Error in message generator: %s\n%s", e, traceback.format_exc())
        yield f"data: {json.dumps({'type': 'error', 'content': 'Internal server error'})}\n\n"
    finally:
        for evt in thinking_processor.flush():
            yield f"data: {json.dumps(evt)}\n\n"
        yield "data: [DONE]\n\n"


def _create_ai_message(parts: dict) -> AIMessage:
    sig = inspect.signature(AIMessage)
    valid_keys = set(sig.parameters)
    filtered = {k: v for k, v in parts.items() if k in valid_keys}
    return AIMessage(**filtered)


def _extract_reasoning_text(message: AIMessageChunk) -> str:
    """Extract provider-specific reasoning text from chunk metadata when available."""

    def _from_payload(payload: Any) -> str:
        if not isinstance(payload, dict):
            return ""

        # reasoning_delta carries per-token streaming chunks which may be
        # whitespace-only (e.g. "\n\n" between sections). Check presence only,
        # not strip(), so newlines and spaces are preserved.
        reasoning_delta = payload.get("reasoning_delta")
        if isinstance(reasoning_delta, str):
            return reasoning_delta

        for key in (
            "reasoning_content",  # Ollama (reasoning=True), DeepSeek API, OpenRouter
            "reasoning",          # Some OpenAI-compatible providers
            "thinking",           # Some providers
            "reasoning_text",     # Some providers
            "thoughts",           # Some providers
            "thought",            # Alternative key used by some providers
            "chain_of_thought",   # Some providers
        ):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value
            if isinstance(value, list):
                try:
                    return convert_message_content_to_string(value)
                except Exception:
                    continue

        nested = payload.get("content")
        if isinstance(nested, dict):
            return _from_payload(nested)

        return ""

    additional_kwargs = getattr(message, "additional_kwargs", {}) or {}
    response_metadata = getattr(message, "response_metadata", {}) or {}
    return _from_payload(additional_kwargs) or _from_payload(response_metadata)


def _extract_reasoning_text_from_message(message: Any) -> str:
    """Extract reasoning text from final AI message metadata when chunks don't carry it."""

    def _from_payload(payload: Any) -> str:
        if not isinstance(payload, dict):
            return ""

        for key in (
            "reasoning_content",
            "reasoning",
            "thinking",
            "reasoning_text",
            "thoughts",
            "thought",
            "chain_of_thought",
        ):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value
            if isinstance(value, list):
                try:
                    text = convert_message_content_to_string(value)
                except Exception:
                    text = ""
                if text:
                    return text

        nested = payload.get("content")
        if isinstance(nested, dict):
            return _from_payload(nested)

        return ""

    def _from_content(content: Any) -> str:
        if isinstance(content, str):
            parts: list[str] = []
            for open_tag, close_tag in (("<think>", "</think>"), ("<thinking>", "</thinking>")):
                start = 0
                while True:
                    open_pos = content.find(open_tag, start)
                    if open_pos == -1:
                        break
                    search_from = open_pos + len(open_tag)
                    close_pos = content.find(close_tag, search_from)
                    if close_pos == -1:
                        chunk = content[search_from:].strip()
                        if chunk:
                            parts.append(chunk)
                        break
                    chunk = content[search_from:close_pos].strip()
                    if chunk:
                        parts.append(chunk)
                    start = close_pos + len(close_tag)
            return "\n".join(parts).strip()

        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if not isinstance(item, dict):
                    continue
                item_type = item.get("type")
                if item_type == "thinking":
                    text = str(item.get("thinking", "") or "").strip()
                    if text:
                        parts.append(text)
                elif item_type == "text" and item.get("thought"):
                    text = str(item.get("text", "") or "").strip()
                    if text:
                        parts.append(text)
            return "\n".join(parts).strip()

        return ""

    additional_kwargs = getattr(message, "additional_kwargs", {}) or {}
    response_metadata = getattr(message, "response_metadata", {}) or {}
    content = getattr(message, "content", None)
    if content is None and isinstance(message, dict):
        content = message.get("content")
    return (
        _from_payload(additional_kwargs)
        or _from_payload(response_metadata)
        or _from_content(content)
    )


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
        raise HTTPException(status_code=500, detail="Unexpected error")
