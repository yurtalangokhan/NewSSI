"""
Agent interaction routes.

Endpoints: /info, /invoke, /stream, /feedback, /history
plus the ``message_generator`` streaming helper.
"""

import asyncio
import inspect
import json
import logging
import re
import time
from collections.abc import AsyncGenerator, AsyncIterator
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from i18n import t
from langchain_core.messages import AIMessage, AIMessageChunk, AnyMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.errors import GraphRecursionError
from langgraph.types import Interrupt

from agents import DEFAULT_AGENT, AgentGraph, get_agent, get_all_agent_info
from api.dependencies import AuthenticatedUser, require_permission, require_user
from controller import get_persona_controller
from core import settings
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
from service.AssistantAgentService import AssistantAgentService
from service.AuthService import extract_user_id_from_token
from service.DocumentProgressTracker import DocumentProgressTracker, is_document_tool
from service.GeneratedFilePacket import (
    build_generated_file_packet_obj,
    parse_generated_file_payload,
)
from service.Utils import (
    convert_message_content_to_string,
    langchain_to_chat_message,
    remove_tool_calls,
)
from service.WebSearchProgressTracker import WebSearchProgressTracker, is_web_search_tool

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agents", tags=["agents"], dependencies=[Depends(require_user)])


class _Heartbeat:
    """Yielded by `_with_idle_heartbeat` while the wrapped stream is quiet.

    Carries how long the current silence has lasted so the client can show
    the user that work is still happening rather than a frozen screen.
    """

    __slots__ = ("silent_seconds",)

    def __init__(self, silent_seconds: float) -> None:
        self.silent_seconds = silent_seconds


async def _with_idle_heartbeat(
    source: AsyncIterator[Any], interval: float
) -> AsyncGenerator[Any, None]:
    """Re-yield `source`, injecting `_HEARTBEAT` during silent stretches.

    A model writing a document emits the whole body as tool-call arguments,
    and providers that only hand over the *completed* call (Ollama via
    langchain-ollama) send nothing at all while that happens — a long
    document can take minutes. `DocumentProgressTracker` cannot fill that
    gap for them because it has no argument chunks to count. Meanwhile any
    proxy in front of the stream sees an idle connection: Kong defaults to a
    60s read timeout and tears it down mid-generation, which surfaces in the
    browser as ERR_INCOMPLETE_CHUNKED_ENCODING.
    """
    iterator = source.__aiter__()
    pending: asyncio.Future | None = None
    try:
        while True:
            pending = asyncio.ensure_future(iterator.__anext__())
            quiet_since = time.monotonic()
            while True:
                done, _ = await asyncio.wait({pending}, timeout=interval)
                if pending in done:
                    break
                yield _Heartbeat(time.monotonic() - quiet_since)
            try:
                item = pending.result()
            except StopAsyncIteration:
                return
            finally:
                pending = None
            yield item
    finally:
        if pending is not None and not pending.done():
            pending.cancel()


def _stream_error_payload(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, httpx.ConnectError | httpx.ConnectTimeout | httpx.ReadTimeout):
        return {
            "type": "error",
            "error": "LLM provider is unreachable. Check the provider URL, network, or model server status.",
            "content": "LLM provider is unreachable. Check the provider URL, network, or model server status.",
            "error_code": "provider_unavailable",
            "is_retryable": True,
            "details": {"exception_type": type(exc).__name__},
        }

    if isinstance(exc, GraphRecursionError):
        return {
            "type": "error",
            "error": "The agent took too many steps to finish this turn (too many searches/tool calls in a row) and was stopped.",
            "content": "The agent took too many steps to finish this turn (too many searches/tool calls in a row) and was stopped.",
            "error_code": "recursion_limit_exceeded",
            "is_retryable": True,
            "details": {"exception_type": type(exc).__name__},
        }

    if isinstance(exc, httpx.HTTPStatusError):
        status_code = exc.response.status_code if exc.response else None
        return {
            "type": "error",
            "error": "LLM provider returned an error.",
            "content": "LLM provider returned an error.",
            "error_code": "provider_http_error",
            "is_retryable": bool(status_code is None or status_code >= 500),
            "details": {
                "exception_type": type(exc).__name__,
                "status_code": status_code,
            },
        }

    return {
        "type": "error",
        "error": "Internal server error",
        "content": "Internal server error",
        "error_code": "internal_error",
        "is_retryable": True,
        "details": {"exception_type": type(exc).__name__},
    }


class ThinkingTagProcessor:
    """Tag-based thinking models (<think>...</think>) için streaming state machine.

    Also strips tool-call markup: models that are not natively tool-calling emit
    `<tool_call>{...}</tool_call>` as ordinary text, and whatever the provider's
    parser leaves behind would otherwise be rendered in the chat. That text is
    reported as `tool_call_text` events instead of being dropped outright, so
    callers can still see what the model is writing (a document body streamed
    this way is the only progress signal available for those models).
    """

    OPEN_TAGS = ("<thinking>", "<think>")
    CLOSE_TAGS = ("</thinking>", "</think>")
    TOOL_OPEN_TAGS = ("<tool_call>", "<tool_use>")
    # A leading "<" is sometimes consumed by the provider's own parser, leaving
    # a bare "/tool_call>" in the text.
    TOOL_CLOSE_TAGS = ("</tool_call>", "</tool_use>", "/tool_call>", "/tool_use>")
    MAX_TAG_LEN = max(len(t) for t in OPEN_TAGS + CLOSE_TAGS + TOOL_OPEN_TAGS + TOOL_CLOSE_TAGS)
    MAX_TAG_LEN = max(len(t) for t in OPEN_TAGS + CLOSE_TAGS + TOOL_OPEN_TAGS + TOOL_CLOSE_TAGS)

    def __init__(self):
        self.in_thinking = False
        self.in_tool_call = False
        self.reasoning_started = False
        self.buffer = ""
        self.pending_prefix = ""

    def feed(self, text: str) -> list[dict]:
        self.buffer += text
        events: list[dict] = []

        while self.buffer:
            if self.in_tool_call:
                if not self._consume_tool_call(events):
                    break
            elif not self.in_thinking:
                if not self._consume_answer(events):
                    break
            elif not self._consume_thinking(events):
                break

        return events

    def _consume_tool_call(self, events: list[dict]) -> bool:
        """Inside tool-call markup: report it separately, never as answer text."""
        pos, tag = self._find_tag(self.buffer, self.TOOL_CLOSE_TAGS)
        if pos is not None:
            if pos > 0:
                events.append({"type": "tool_call_text", "content": self.buffer[:pos]})
            self.in_tool_call = False
            self.buffer = self.pending_prefix + self.buffer[pos + len(tag) :]
            self.pending_prefix = ""
            return True

        safe_len = max(0, len(self.buffer) - self.MAX_TAG_LEN)
        if safe_len > 0:
            events.append({"type": "tool_call_text", "content": self.buffer[:safe_len]})
            self.buffer = self.buffer[safe_len:]
        return False

    def _consume_answer(self, events: list[dict]) -> bool:
        pos, tag, kind = self._find_first(
            self.buffer,
            (self.OPEN_TAGS, "think"),
            (self.TOOL_OPEN_TAGS, "tool"),
            (self.TOOL_CLOSE_TAGS, "stray"),
        )
        if pos is not None:
            if pos > 0:
                content = self.buffer[:pos]
                if kind == "tool" and not content.endswith(
                    (" ", "\n", "\t", ".", "!", "?", ":", ";", ",")
                ):
                    last_space = max(content.rfind(" "), content.rfind("\n"), content.rfind("\t"))
                    if last_space != -1:
                        events.append({"type": "token", "content": content[: last_space + 1]})
                        self.pending_prefix = content[last_space + 1 :]
                        self.buffer = self.buffer[pos + len(tag) :]
                    else:
                        events.append({"type": "token", "content": content})
                        self.buffer = self.buffer[pos + len(tag) :]
                else:
                    events.append({"type": "token", "content": content})
                    self.buffer = self.buffer[pos + len(tag) :]
            else:
                self.buffer = self.buffer[pos + len(tag) :]

            if kind == "think":
                if not self.reasoning_started:
                    events.append({"type": "reasoning_start"})
                    self.reasoning_started = True
                self.in_thinking = True
            elif kind == "tool":
                self.in_tool_call = True
            # "stray": an unmatched close tag is simply dropped.
            return True

        has_partial_tag = False
        last_lt = self.buffer.rfind("<")
        if last_lt != -1 and (len(self.buffer) - last_lt) <= self.MAX_TAG_LEN:
            has_partial_tag = True

        safe_len = max(0, last_lt) if has_partial_tag else len(self.buffer)
        if safe_len > 0:
            target_content = self.buffer[:safe_len]
            last_space = max(
                target_content.rfind(" "),
                target_content.rfind("\n"),
                target_content.rfind("\t"),
            )
            if last_space != -1:
                events.append({"type": "token", "content": self.buffer[: last_space + 1]})
                self.buffer = self.buffer[last_space + 1 :]
        return False

    def _consume_thinking(self, events: list[dict]) -> bool:
        pos, tag, kind = self._find_first(
            self.buffer,
            (self.CLOSE_TAGS, "think_end"),
            (self.TOOL_OPEN_TAGS, "tool"),
        )
        if pos is not None:
            if pos > 0:
                events.append({"type": "reasoning_delta", "reasoning": self.buffer[:pos]})
            self.buffer = self.buffer[pos + len(tag) :]
            if kind == "think_end":
                self.in_thinking = False
            else:
                # Models write their tool call inside the reasoning block too.
                self.in_tool_call = True
            return True

        safe_len = max(0, len(self.buffer) - self.MAX_TAG_LEN)
        if safe_len > 0:
            events.append({"type": "reasoning_delta", "reasoning": self.buffer[:safe_len]})
            self.buffer = self.buffer[safe_len:]
        return False

    def flush(self) -> list[dict]:
        """Stream bitişinde kalan buffer'ı emit et."""
        if not self.buffer:
            return []
        if self.in_tool_call:
            event = {"type": "tool_call_text", "content": self.buffer}
        elif self.in_thinking:
            event = {"type": "reasoning_delta", "reasoning": self.buffer}
        else:
            event = {"type": "token", "content": self.buffer}
        self.buffer = ""
        return [event]

    @classmethod
    def _find_first(cls, text: str, *groups: tuple) -> tuple:
        """Find the earliest tag across several labelled tag groups."""
        best_pos, best_tag, best_kind = None, None, None
        for tags, kind in groups:
            pos, tag = cls._find_tag(text, tags)
            if pos is not None and (best_pos is None or pos < best_pos):
                best_pos, best_tag, best_kind = pos, tag, kind
        return best_pos, best_tag, best_kind

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
            output = langchain_to_chat_message(
                AIMessage(content=response["__interrupt__"][0].value)
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
    # Document tools write their whole payload into tool-call arguments, which
    # produce no visible tokens — this turns that silence into progress packets.
    document_progress = DocumentProgressTracker()
    web_search_progress = WebSearchProgressTracker()
    saw_reasoning_for_current_answer = False
    # Track the first LLM call's message ID so that subsequent LLM calls
    # (e.g. background memory extraction) don't emit tokens to the stream.
    first_llm_call_id: str | None = None
    # Whether the LLM call we are currently streaming produced tool calls. A
    # call that did is always followed by an answer call, which must be let
    # through even though it has a different message id.
    current_call_made_tool_calls = False
    saw_visible_answer_tokens = False
    # Message ids whose tokens already reached the client, so the final full
    # `message` packet for them can be dropped without guessing.
    streamed_message_ids: set[str] = set()
    # Generated files already announced (a tool may emit its own live packet
    # before the node's ToolMessage reaches this loop).
    emitted_file_ids: set[str] = set()
    # Keyed by tool_call id, not name: a deep-research loop can call the same
    # tool (e.g. web_search) many times in one turn, and each call needs its
    # own custom_tool_start. This set only dedupes the *same* call appearing
    # in both the `messages` stream (tool_call_chunks) and the `updates`
    # stream (the full AI message, reported again once the node returns).
    emitted_tool_call_ids: set[str] = set()
    # Trailing character of the visible answer so far, plus whether a tool
    # phase has interrupted it since. A model routinely breaks off mid-answer
    # to call a tool and resumes afterwards; the two halves arrive as one
    # uninterrupted token stream, so a call that stopped mid-word runs into
    # the next one's first word (e.g. "AramalarıHarika").
    last_visible_char = ""
    answer_interrupted_by_tool = False
    start_time = time.time()

    def _token_payload(text: str) -> str:
        """Serialise one visible token, healing tool-call seams."""
        nonlocal answer_interrupted_by_tool, last_visible_char
        if answer_interrupted_by_tool:
            answer_interrupted_by_tool = False
            # Separate the halves only when they would actually run together.
            # The model usually resumes an unfinished sentence after the tool
            # call, and breaking there would split the sentence instead.
            if last_visible_char and not last_visible_char.isspace() and not text[:1].isspace():
                text = "\n\n" + text
        last_visible_char = text[-1:] or last_visible_char
        return f"data: {json.dumps({'type': 'token', 'content': text})}\n\n"

    def _flush_pending_answer_text() -> list[str]:
        """Release any partial word the tag processor is still holding.

        Its buffer holds back text up to the last whitespace so a split tag
        is never mistaken for answer text, and that buffer spans LLM calls.
        A call that stops mid-word therefore merges with the next call's
        first word *inside* the buffer, before anything downstream can tell
        the two apart. Draining it at the seam keeps them separate.
        """
        payloads: list[str] = []
        for evt in thinking_processor.flush():
            if evt.get("type") == "token" and evt.get("content"):
                payloads.append(_token_payload(evt["content"]))
            elif evt.get("type") != "tool_call_text":
                payloads.append(f"data: {json.dumps(evt)}\n\n")
        return payloads

    def _flush_idle_answer_text() -> list[str]:
        """Release buffered answer text once the stream has fallen quiet.

        Waiting for the tool call to arrive is not good enough here: Ollama
        withholds tool-call arguments until the call is complete, so a model
        writing a document sends nothing for a minute or more. The tail of
        the sentence it wrote just before would sit unrendered behind a
        blinking cursor for that whole time, then appear only once the
        document lands. Silence means no tag can still be arriving, so the
        text is safe to release — unless a partial tag really is pending, in
        which case emitting it would leak markup like "<thi" into the chat.
        """
        if "<" in thinking_processor.buffer:
            return []
        return _flush_pending_answer_text()

    try:
        async for stream_event in _with_idle_heartbeat(
            agent.astream(**kwargs, stream_mode=["updates", "messages", "custom"], subgraphs=True),
            settings.STREAM_HEARTBEAT_SECONDS,
        ):
            if isinstance(stream_event, _Heartbeat):
                # An SSE comment: no packet type, so clients ignore it, but it
                # keeps proxies from seeing an idle connection while the model
                # writes a long tool call (see `_with_idle_heartbeat`).
                yield ": keep-alive\n\n"
                # Nothing more is coming for now, so anything the tag
                # processor is still holding back belongs on screen rather
                # than stuck behind the cursor for the rest of the wait.
                for payload in _flush_idle_answer_text():
                    yield payload
                # Ollama does not stream tool-call arguments, so a model
                # writing a document goes quiet for minutes with nothing to
                # report progress from. Tell the client how long the wait has
                # run so it can show that work continues.
                progress = {
                    "type": "stream_progress",
                    "elapsed_seconds": int(stream_event.silent_seconds),
                }
                yield f"data: {json.dumps(progress)}\n\n"
                continue

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
                    # Live packets written from inside a tool call. A node's
                    # updates only arrive once the whole node returns — for the
                    # single-node chatbot graph that is after the closing answer
                    # has streamed, so these are the only timely signal that the
                    # file is ready.
                    if msg_type in (
                        "document_generation_progress",
                        "document_generation_end",
                        "generated_file",
                    ):
                        # The generation may never have been announced (a model
                        # can write its whole tool call inside a reasoning
                        # block) — open one so the UI has something to update.
                        for packet in document_progress.adopt_live_packet(message):
                            yield f"data: {json.dumps(packet)}\n\n"
                        if msg_type == "generated_file":
                            file_id = message.get("file_id")
                            if file_id in emitted_file_ids:
                                continue
                            emitted_file_ids.add(file_id)
                        if msg_type == "document_generation_end":
                            # The tool closed the generation itself; keep the
                            # tracker from emitting a second end packet.
                            document_progress.close()
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
                    current_call_made_tool_calls = False
                    saw_visible_answer_tokens = False
                    saw_reasoning_for_current_answer = False
                    # Close out this call's answer before the next one starts,
                    # then mark the seam so the two halves stay apart.
                    for payload in _flush_pending_answer_text():
                        yield payload
                    answer_interrupted_by_tool = True
                    for packet in document_progress.on_tool_calls(chat_message.tool_calls):
                        yield f"data: {json.dumps(packet)}\n\n"
                    for tc in chat_message.tool_calls:
                        tc_name = (
                            tc.get("name", "tool")
                            if isinstance(tc, dict)
                            else getattr(tc, "name", "tool")
                        )
                        tc_args = (
                            tc.get("args") if isinstance(tc, dict) else getattr(tc, "args", None)
                        )
                        tc_id = (
                            tc.get("id") if isinstance(tc, dict) else getattr(tc, "id", None)
                        ) or tc_name
                        if tc_id not in emitted_tool_call_ids:
                            emitted_tool_call_ids.add(tc_id)
                            # Document tools already have their own lifecycle
                            # packets (document_generation_*), which the frontend
                            # keeps on the current answer's turn. The generic
                            # custom_tool_start is exempt from that and would
                            # reset the in-progress answer's streaming state.
                            if not is_document_tool(tc_name):
                                web_search_packets = (
                                    web_search_progress.on_tool_call(tc_name, tc_args, tc_id)
                                    if is_web_search_tool(tc_name)
                                    else None
                                )
                                if web_search_packets is not None:
                                    for packet in web_search_packets:
                                        yield f"data: {json.dumps(packet)}\n\n"
                                else:
                                    yield f"data: {json.dumps({'type': 'custom_tool_start', 'tool_name': tc_name, 'args': tc_args, 'call_id': tc_id})}\n\n"
                    continue
                elif chat_message.type == "tool":
                    tool_name = getattr(message, "name", "") or ""
                    tool_call_id = getattr(message, "tool_call_id", None)
                    # Keep subsequent assistant phase visible even when prior phase streamed tokens.
                    saw_visible_answer_tokens = False
                    saw_reasoning_for_current_answer = False

                    generated_file = parse_generated_file_payload(chat_message.content)
                    web_search_packets = (
                        web_search_progress.on_tool_result(
                            tool_name, chat_message.content, tool_call_id
                        )
                        if generated_file is None and is_web_search_tool(tool_name)
                        else None
                    )
                    if (
                        generated_file is None
                        and web_search_packets is None
                        and not is_document_tool(tool_name)
                    ):
                        yield f"data: {json.dumps({'type': 'custom_tool_delta', 'tool_name': tool_name, 'response_type': 'tool_result', 'data': chat_message.content, 'call_id': tool_call_id})}\n\n"

                    if web_search_packets is not None:
                        for packet in web_search_packets:
                            yield f"data: {json.dumps(packet)}\n\n"

                    if generated_file is not None:
                        file_id = generated_file.get("file_id")
                        if file_id not in emitted_file_ids:
                            emitted_file_ids.add(file_id)
                            yield f"data: {json.dumps(build_generated_file_packet_obj(generated_file))}\n\n"

                    for packet in document_progress.on_tool_result(tool_name, chat_message.content):
                        yield f"data: {json.dumps(packet)}\n\n"
                    continue

                # Some providers do not stream reasoning chunks and only attach
                # reasoning to final AI message metadata. Emit fallback packets so
                # live timeline matches refresh reconstruction behavior.
                if chat_message.type == "ai":
                    elapsed_duration = max(1, int(time.time() - start_time))
                    if hasattr(message, "additional_kwargs") and isinstance(
                        getattr(message, "additional_kwargs", None), dict
                    ):
                        message.additional_kwargs["processing_duration_seconds"] = elapsed_duration

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
                # `saw_visible_answer_tokens` is reset at every tool boundary, so
                # it cannot cover a graph that reports all of its messages at
                # once (the chatbot tool loop) — match on the message id too.
                if chat_message.type == "ai" and user_input.stream_tokens:
                    if saw_visible_answer_tokens:
                        continue
                    if getattr(message, "id", None) in streamed_message_ids:
                        continue

                # Strip <think>/<thinking> tags from AI responses
                if chat_message.type == "ai" and chat_message.content:
                    cleaned = re.sub(
                        r"<think>.*?</think>", "", chat_message.content, flags=re.DOTALL
                    )
                    cleaned = re.sub(r"<thinking>.*?</thinking>", "", cleaned, flags=re.DOTALL)
                    cleaned = re.sub(r"<think>(?:(?!</think>).)*$", "", cleaned, flags=re.DOTALL)
                    cleaned = re.sub(
                        r"<thinking>(?:(?!</thinking>).)*$", "", cleaned, flags=re.DOTALL
                    )
                    chat_message.content = cleaned.strip()
                    if not chat_message.content:
                        continue

                yield f"data: {json.dumps({'type': 'message', 'content': chat_message.model_dump()})}\n\n"

            if stream_mode == "messages":
                msg, metadata = event
                if "skip_stream" in metadata.get("tags", []):
                    continue
                if not isinstance(msg, AIMessageChunk):
                    continue

                # A document body streams as tool-call arguments, never as
                # tokens, so this runs regardless of `stream_tokens`.
                for packet in document_progress.on_chunk(msg):
                    yield f"data: {json.dumps(packet)}\n\n"

                if not user_input.stream_tokens:
                    continue

                # Filter out tokens from secondary LLM calls (e.g. memory extraction).
                # Each model.ainvoke() produces AIMessageChunks with a unique `id`.
                # We only stream tokens from the first (main response) call.
                msg_id = getattr(msg, "id", None)
                if msg_id:
                    if first_llm_call_id is None:
                        first_llm_call_id = msg_id
                        current_call_made_tool_calls = False
                    elif msg_id != first_llm_call_id:
                        # A call that ended in tool calls is always followed by
                        # the answer call. When both happen inside one node (the
                        # chatbot graph runs its whole tool loop in `call_model`)
                        # the updates event that would reset this id only arrives
                        # after the node returns — so without this the entire
                        # answer is dropped and then dumped at once as a single
                        # `message` packet, with no streaming animation.
                        if not current_call_made_tool_calls:
                            continue
                        first_llm_call_id = msg_id
                        current_call_made_tool_calls = False
                        # Same seam as the tool-call branch above, but reached
                        # when the whole loop runs inside one node, so the
                        # `updates` event that would have flagged it has not
                        # arrived yet. `_token_payload` decides whether the
                        # halves actually need separating.
                        for payload in _flush_pending_answer_text():
                            yield payload
                        answer_interrupted_by_tool = True

                if getattr(msg, "tool_call_chunks", None):
                    current_call_made_tool_calls = True
                    # The tag processor is still holding this call's last word
                    # (it buffers up to the final whitespace). Release it now,
                    # while it still belongs to the text above the tool steps —
                    # the `updates` event that also flushes arrives only after
                    # these `custom_tool_start` packets, which would strand the
                    # word in a display group of its own below them.
                    for payload in _flush_pending_answer_text():
                        yield payload
                    for tc_chunk in msg.tool_call_chunks:
                        tc_name = (
                            tc_chunk.get("name")
                            if isinstance(tc_chunk, dict)
                            else getattr(tc_chunk, "name", None)
                        )
                        tc_args = (
                            tc_chunk.get("args")
                            if isinstance(tc_chunk, dict)
                            else getattr(tc_chunk, "args", None)
                        )
                        tc_id = (
                            tc_chunk.get("id")
                            if isinstance(tc_chunk, dict)
                            else getattr(tc_chunk, "id", None)
                        ) or tc_name
                        if tc_name and tc_id not in emitted_tool_call_ids:
                            # web_search/fetch_webpage need their full args
                            # (the query/URL) to emit a meaningful
                            # search_tool_*/open_url_* packet, but only the
                            # first of these streamed chunks carries the name
                            # — args arrive fragmented across the chunks that
                            # follow. Defer entirely to the `updates` event
                            # below, which reports the complete tool call
                            # once the node returns (same pattern Ollama-style
                            # non-streaming providers already rely on).
                            if is_web_search_tool(tc_name):
                                continue
                            emitted_tool_call_ids.add(tc_id)
                            # Same exemption as above: document tools are
                            # represented by document_generation_* packets only,
                            # so this must not reset the in-progress answer.
                            if not is_document_tool(tc_name):
                                yield f"data: {json.dumps({'type': 'custom_tool_start', 'tool_name': tc_name, 'args': tc_args, 'call_id': tc_id})}\n\n"

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
                                for doc_packet in document_progress.on_tool_call_text(
                                    thinking_text
                                ):
                                    yield f"data: {json.dumps(doc_packet)}\n\n"
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
                                if msg_id:
                                    streamed_message_ids.add(msg_id)
                                yield _token_payload(text)
                    if reasoning_text and not emitted_reasoning:
                        if not saw_reasoning_for_current_answer:
                            yield f"data: {json.dumps({'type': 'reasoning_start'})}\n\n"
                            saw_reasoning_for_current_answer = True
                        yield f"data: {json.dumps({'type': 'reasoning_delta', 'reasoning': reasoning_text})}\n\n"
                else:
                    # Tag tabanlı modeller (DeepSeek, Qwen vb.)
                    # A native reasoning field (e.g. Ollama's reasoning_content)
                    # can land on the same chunk as visible content. Emitting
                    # reasoning only when content was empty (the old `elif`)
                    # silently dropped it whenever both were present on one
                    # chunk — the model looked like it abruptly left its
                    # thinking phase, wrote a token or two, then "went back"
                    # to thinking on a later chunk once content emptied out
                    # again, with that dropped reasoning never having been
                    # shown in between. Emit both, independently, in order.
                    if reasoning_text:
                        if not saw_reasoning_for_current_answer:
                            yield f"data: {json.dumps({'type': 'reasoning_start'})}\n\n"
                            saw_reasoning_for_current_answer = True
                        yield f"data: {json.dumps({'type': 'reasoning_delta', 'reasoning': reasoning_text})}\n\n"

                    token_str = convert_message_content_to_string(content)
                    if token_str:
                        for evt in thinking_processor.feed(token_str):
                            # Tool-call markup never reaches the chat; it only
                            # tells us a document is being written.
                            if evt.get("type") == "tool_call_text":
                                for packet in document_progress.on_tool_call_text(
                                    evt.get("content", "")
                                ):
                                    yield f"data: {json.dumps(packet)}\n\n"
                                continue
                            if evt.get("type") in ("reasoning_start", "reasoning_delta"):
                                saw_reasoning_for_current_answer = True
                            if evt.get("type") == "token" and evt.get("content"):
                                saw_visible_answer_tokens = True
                                if msg_id:
                                    streamed_message_ids.add(msg_id)
                                yield _token_payload(evt["content"])
                                continue
                            yield f"data: {json.dumps(evt)}\n\n"

        # The stream itself never carries a real, persisted message id for
        # the turn it just produced (ids only exist as positions computed by
        # ChatController.get_chat_session on read). Without this, anything
        # that needs a real messageId right after sending — retrying this
        # very message, switching between regenerated alternates — silently
        # does nothing until the page is reloaded. Resolve it once, now that
        # generation is done, by reading back the just-persisted checkpoint.
        if user_input.thread_id:
            try:
                from controller import ChatController, get_thread_controller

                id_controller = ChatController(
                    thread_controller=get_thread_controller(),
                    user_id=user_id or "",
                )
                session = await id_controller.get_chat_session(user_input.thread_id)
                session_messages = session.get("messages") or []
                if session_messages:
                    last_message = session_messages[-1]
                    # A turn that produced no visible content (e.g. an error
                    # cut generation short before any assistant message was
                    # appended) leaves the human message as the last entry —
                    # only emit ids when reconstruction actually ends on the
                    # assistant turn we just generated.
                    if last_message.get("message_type") == "assistant":
                        assistant_message_id = last_message.get("message_id")
                        user_message_id = last_message.get("parent_message")
                    else:
                        assistant_message_id = None
                        user_message_id = None
                    if assistant_message_id is not None:
                        yield (
                            "data: "
                            + json.dumps(
                                {
                                    "user_message_id": user_message_id,
                                    "reserved_assistant_message_id": assistant_message_id,
                                }
                            )
                            + "\n\n"
                        )
            except Exception:
                logger.warning(
                    "Failed to resolve real message ids after streaming",
                    exc_info=True,
                )

    except Exception as e:
        payload = _stream_error_payload(e)
        if payload["error_code"].startswith("provider_"):
            logger.warning(
                "Provider error in message generator: %s: %s",
                type(e).__name__,
                e,
            )
        else:
            import traceback

            logger.error("Error in message generator: %s\n%s", e, traceback.format_exc())
        yield f"data: {json.dumps(payload)}\n\n"
    finally:
        for evt in thinking_processor.flush():
            # Unterminated tool-call markup must not spill into the chat either.
            if evt.get("type") == "tool_call_text":
                continue
            yield f"data: {json.dumps(evt)}\n\n"
        # Never leave the frontend showing a skeleton for a generation that
        # died with the stream.
        for packet in document_progress.flush():
            yield f"data: {json.dumps(packet)}\n\n"
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
            "reasoning",  # Some OpenAI-compatible providers
            "thinking",  # Some providers
            "reasoning_text",  # Some providers
            "thoughts",  # Some providers
            "thought",  # Alternative key used by some providers
            "chain_of_thought",  # Some providers
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
