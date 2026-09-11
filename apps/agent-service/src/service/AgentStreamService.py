"""The SSE streaming engine behind ``POST /agents/{id}/stream``.

Extracted from ``api/routes/AgentsRoute.py``, where it had grown to ~1,700
lines around six thin route handlers — two things changing for two different
reasons in one module, and business logic in the route layer that
``docs/coding-standards.md`` puts in ``service/``.

Nothing here changed in the move: same generator, same helpers, same packet
shapes. ``AgentsRoute`` now imports ``message_generator`` and stays a router.
"""

import asyncio
import json
import re
import time
from collections.abc import AsyncGenerator, AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import httpx
from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage
from langgraph.errors import GraphRecursionError
from langgraph.types import Interrupt

from agents import DEFAULT_AGENT
from agents.clarification import is_clarification_tool
from agents.graphs import PASSTHROUGH_NODE_TYPES as _flow_passthrough_node_types
from core import settings
from core.logger import get_logger
from models.chat import (
    StreamInput,
)
from service.AgentHelpers import _handle_input
from service.ai_message import _create_ai_message
from service.AssistantAgentService import AssistantAgentService
from service.DocumentProgressTracker import DocumentProgressTracker, is_document_tool
from service.GeneratedFilePacket import (
    build_generated_file_packet_obj,
    parse_generated_file_payload,
)
from service.message_conversion import (
    convert_message_content_to_string,
    langchain_to_chat_message,
    remove_tool_calls,
)
from service.thinking_tag_processor import ThinkingTagProcessor
from service.WebSearchProgressTracker import WebSearchProgressTracker, is_web_search_tool

logger = get_logger(__name__)


# Flow node types that never become a numbered "stage" in the per-stage
# timeline: control flow, boundary no-ops and plain value producers. They emit
# no answer text, so a stage for them is an empty group in the chat.
#
# Derived from the compiler's own passthrough set rather than restated here —
# a hand-written copy went stale every time a node type was added (Phase 0's
# SetVariable, Phase 3's While, Phase 4's HumanInput all leaked through).
# Loop iterations still surface via the body's nodes re-running, not the Loop.
_NON_STAGE_NODE_TYPES = frozenset(_flow_passthrough_node_types)

# LangGraph's own node names, which must never be reported as a stage.
_GRAPH_INTERNAL_NODES = frozenset({"__start__", "__end__", "__interrupt__"})
# A compiled agent subgraph's internal steps. These only ever arrive under a
# namespace, so they are infrastructure *inside a subgraph only*: a top-level
# canvas node id is user-authored and may legitimately be called "agent"
# (hand-written or imported specs do it), in which case it is a real stage.
_SUBGRAPH_STEP_NODES = frozenset({"tools", "agent", "model", "call_model"})


def _is_infra_node(node_name: str, *, is_top_level: bool) -> bool:
    """Whether a node name should be hidden from stage reporting."""
    if node_name in _GRAPH_INTERNAL_NODES:
        return True
    return not is_top_level and node_name in _SUBGRAPH_STEP_NODES


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
    # One producer owns the iterator for its entire lifetime. Async generators
    # may set ContextVar tokens across yields, so advancing each item in a new
    # task (or closing it in the consumer) would invalidate those tokens.
    queue: asyncio.Queue[tuple[bool, Any]] = asyncio.Queue(maxsize=1)
    closing = False

    async def produce() -> None:
        iterator = source.__aiter__()
        try:
            try:
                async for item in iterator:
                    await queue.put((True, item))
            finally:
                close = getattr(iterator, "aclose", None)
                if close is not None:
                    await close()
        except Exception as exc:
            if not closing:
                await queue.put((False, exc))
        else:
            if not closing:
                await queue.put((False, None))

    producer = asyncio.create_task(produce())
    pending: asyncio.Task | None = None
    try:
        while True:
            pending = asyncio.create_task(queue.get())
            quiet_since = time.monotonic()
            while True:
                done, _ = await asyncio.wait(
                    {pending, producer}, timeout=interval,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if pending in done:
                    break
                if producer in done:
                    # Propagate cancellation or failures outside the iterator
                    # loop; normal completion has already queued its outcome.
                    await producer
                    await pending
                    break
                yield _Heartbeat(time.monotonic() - quiet_since)
            has_item, item = pending.result()
            pending = None
            if not has_item:
                if item is not None:
                    raise item
                return
            yield item
    finally:
        # The consumer no longer drains the queue during cancellation. Cleanup
        # failures must not block the producer trying to publish a final result.
        closing = True
        tasks = [producer] + ([pending] if pending is not None else [])
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


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


class _SseFramer:
    """How one run turns tokens, reasoning and tool packets into SSE frames.

    A FlowAgent run tags every frame with the stage that produced it so the
    client can nest it under that stage's header; a plain agent run has no
    tracker and the same methods answer both cases. The answer-seam state
    (``answer_interrupted_by_tool``, ``last_visible_char``) lives here because
    only these methods read or write it — it was six closures sharing two
    ``nonlocal`` variables before.
    """

    def __init__(
        self,
        thinking_processor: Any,
        stage_tracker: Any | None,
        nodes_by_id: dict[str, Any],
    ) -> None:
        self.thinking_processor = thinking_processor
        self.stage_tracker = stage_tracker
        self.nodes_by_id = nodes_by_id
        # A model routinely breaks off mid-answer to call a tool and resumes
        # after; these two remember where it stopped so the halves do not run
        # together ("AramalarıHarika").
        self.answer_interrupted_by_tool = False
        self.last_visible_char = ""

    def token_payload(self, text: str) -> str:
        """Serialise one visible token.

        For a FlowAgent stage that does NOT feed ChatOutput, the text is
        folded into that stage's timeline entry (`flow_stage_output_delta`)
        instead of the answer bubble; the final stage's text still streams as
        a normal `token`. Non-flow agents are unaffected — `self.stage_tracker`
        is None. Seam-healing only matters for the answer bubble.
        """
        if self.stage_tracker is not None:
            self.stage_tracker.add_output(text)
            if self.stage_tracker.current_is_known_nonfinal():
                cur = self.stage_tracker.current
                return (
                    "data: "
                    + json.dumps(
                        {
                            "type": "flow_stage_output_delta",
                            "stage_key": cur.key,
                            "stage_order": cur.order,
                            "iteration": cur.iteration,
                            "content": text,
                        }
                    )
                    + "\n\n"
                )
        if self.answer_interrupted_by_tool:
            self.answer_interrupted_by_tool = False
            # Separate the halves only when they would actually run together.
            # The model usually resumes an unfinished sentence after the tool
            # call, and breaking there would split the sentence instead.
            if (
                self.last_visible_char
                and not self.last_visible_char.isspace()
                and not text[:1].isspace()
            ):
                text = "\n\n" + text
        self.last_visible_char = text[-1:] or self.last_visible_char
        return f"data: {json.dumps({'type': 'token', 'content': text})}\n\n"

    def flush_pending_answer_text(self, hard: bool = False) -> list[str]:
        """Release any partial word the tag processor is still holding.

        Its buffer holds back text up to the last whitespace so a split tag
        is never mistaken for answer text, and that buffer spans LLM calls.
        A call that stops mid-word therefore merges with the next call's
        first word *inside* the buffer, before anything downstream can tell
        the two apart. Draining it at the seam keeps them separate.

        ``hard=True`` marks a FlowAgent stage boundary: also clear the
        processor's ``<think>`` / ``<tool_call>`` state so an unterminated
        tag from the finished stage cannot swallow the next stage's visible
        output as reasoning (see ``ThinkingTagProcessor.reset``).
        """
        payloads: list[str] = []
        for evt in self.thinking_processor.reset() if hard else self.thinking_processor.flush():
            if evt.get("type") == "token" and evt.get("content"):
                payloads.append(self.token_payload(evt["content"]))
            elif evt.get("type") != "tool_call_text":
                payloads.append(f"data: {json.dumps(evt)}\n\n")
        return payloads

    def flush_idle_answer_text(self) -> list[str]:
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
        if "<" in self.thinking_processor.buffer:
            return []
        return self.flush_pending_answer_text()

    def reasoning_delta_frame(self, text: str) -> str:
        """A `reasoning_delta` SSE frame, stage-tagged and recorded on the
        tracker when a FlowAgent stage is running so it nests under that
        stage's timeline header. Identical to before for non-flow agents."""
        if self.stage_tracker is not None:
            self.stage_tracker.add_reasoning(text)
            cur = self.stage_tracker.current
            if cur is not None:
                return (
                    "data: "
                    + json.dumps(
                        {
                            "type": "reasoning_delta",
                            "reasoning": text,
                            "stage_key": cur.key,
                            "stage_order": cur.order,
                            "iteration": cur.iteration,
                        }
                    )
                    + "\n\n"
                )
        return f"data: {json.dumps({'type': 'reasoning_delta', 'reasoning': text})}\n\n"

    def reasoning_start_frame(self) -> str:
        """A `reasoning_start` SSE frame, stage-tagged so its `reasoning_delta`
        siblings stay in the same stage group instead of orphaning the
        opener into the inline timeline."""
        if self.stage_tracker is not None and self.stage_tracker.current is not None:
            cur = self.stage_tracker.current
            # Tell the tracker a new thinking block opens here, so a stage
            # that thinks, calls a tool and thinks again replays as two
            # bubbles after a refresh rather than one run-on paragraph.
            self.stage_tracker.begin_reasoning()
            return (
                "data: "
                + json.dumps(
                    {
                        "type": "reasoning_start",
                        "stage_key": cur.key,
                        "stage_order": cur.order,
                        "iteration": cur.iteration,
                    }
                )
                + "\n\n"
            )
        return f"data: {json.dumps({'type': 'reasoning_start'})}\n\n"

    def cur_stage_node_id(self) -> str | None:
        """The canvas node id of the FlowAgent stage running right now, or
        None when no stage is active / this is not a FlowAgent run. The
        tracker keeps `current` pointed at a stage until the next one
        begins, so a tool call's trailing result still resolves here."""
        if self.stage_tracker is not None and self.stage_tracker.current is not None:
            return self.stage_tracker.current.node_id
        return None

    def stage_tag(self, obj: dict[str, Any]) -> dict[str, Any]:
        """Inject stage_key/stage_order/iteration plus the running stage's
        canvas node id and type into a tool/step packet when a FlowAgent
        stage is running; a passthrough otherwise. `stage_node_id` lets the
        chat-side graph strip attribute the tool to its parent stage
        exactly, instead of guessing from graph position or timing."""
        if self.stage_tracker is not None and self.stage_tracker.current is not None:
            cur = self.stage_tracker.current
            return {
                **obj,
                "stage_key": cur.key,
                "stage_order": cur.order,
                "iteration": cur.iteration,
                "stage_node_id": cur.node_id,
                "stage_node_type": (self.nodes_by_id.get(cur.node_id) or {}).get("type"),
            }
        return obj

    def emit_stage(self, packet: dict[str, Any]) -> str:
        """SSE frame for a tracker-produced packet (web search / document
        generation), stage-tagged so it nests under the running stage."""
        return f"data: {json.dumps(self.stage_tag(packet))}\n\n"


@dataclass
class _RunContext:
    """One streaming run's collaborators and the state its event loop carries.

    These were twenty-odd locals in ``message_generator``, read and rebound
    across a 600-line loop. Naming them as one object is what lets the mode
    handlers below be ordinary functions instead of closures.

    The ``emitted_*`` / ``streamed_*`` sets are dedupe memory: LangGraph
    re-delivers a node's whole accumulated message list at every later node
    boundary, so without them a tool that ran in stage 1 is re-closed in
    stages 2 and 3.
    """

    agent: Any
    user_input: Any
    run_id: Any
    start_time: float
    framer: _SseFramer
    thinking_processor: Any
    document_progress: Any
    web_search_progress: Any
    stage_tracker: Any | None
    flow_stage_runs: list[dict[str, Any]] = field(default_factory=list)
    streamed_message_ids: set[str] = field(default_factory=set)
    streamed_reasoning_message_ids: set[str] = field(default_factory=set)
    emitted_ai_message_ids: set[str] = field(default_factory=set)
    emitted_file_ids: set[str] = field(default_factory=set)
    emitted_tool_call_ids: set[str] = field(default_factory=set)
    emitted_tool_result_ids: set[str] = field(default_factory=set)

    # Carried across events, not per-event: an LLM call spans many chunks and
    # the answer that follows a tool call is a *different* message id that
    # must still be let through.
    saw_reasoning_for_current_answer: bool = False
    first_llm_call_id: str | None = None
    current_call_made_tool_calls: bool = False
    current_stage_ns: str | None = None
    saw_visible_answer_tokens: bool = False


async def _stream_completed_messages(
    ctx: _RunContext,
    processed_messages: list[Any],
) -> AsyncGenerator[str, None]:
    """Emit the frames for messages a node finished producing.

    This is the ``updates`` side of the stream: a node has returned and
    reports its whole accumulated message list, so the same ToolMessage
    arrives again at every later node boundary. The dedupe sets on ``ctx``
    are what keep a tool that ran in stage 1 from being re-closed in stages
    2 and 3.
    """
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
                for packet in ctx.document_progress.adopt_live_packet(message):
                    yield ctx.framer.emit_stage(packet)
                if msg_type == "generated_file":
                    file_id = message.get("file_id")
                    if file_id in ctx.emitted_file_ids:
                        continue
                    ctx.emitted_file_ids.add(file_id)
                if msg_type == "document_generation_end":
                    # The tool closed the generation itself; keep the
                    # tracker from emitting a second end packet.
                    ctx.document_progress.close()
                yield f"data: {json.dumps(message)}\n\n"
                continue

        try:
            chat_message = langchain_to_chat_message(message)
            chat_message.run_id = str(ctx.run_id)
        except Exception as e:
            logger.error(f"Error parsing message: {e}")
            yield f"data: {json.dumps({'type': 'error', 'content': 'Unexpected error'})}\n\n"
            continue

        if chat_message.type == "human" and chat_message.content == ctx.user_input.message:
            continue

        if chat_message.type == "ai":
            ai_msg_id = getattr(message, "id", None) or getattr(chat_message, "id", None)
            if not ai_msg_id:
                ai_msg_id = f"ai_hash_{hash((getattr(chat_message, 'content', ''), str(getattr(chat_message, 'tool_calls', []))))}"
            if ai_msg_id in ctx.emitted_ai_message_ids:
                continue
            ctx.emitted_ai_message_ids.add(ai_msg_id)

        # Emit tool call lifecycle packets for frontend timeline
        # Skip the regular 'message' yield for tool-related messages
        # so they only appear in the timeline, not duplicated in chat
        if chat_message.type == "ai" and chat_message.tool_calls:
            # New tool phase: allow post-tool model call tokens/reasoning through.
            ctx.first_llm_call_id = None
            ctx.current_call_made_tool_calls = False
            ctx.saw_visible_answer_tokens = False
            ctx.saw_reasoning_for_current_answer = False
            # Close out this call's answer before the next one starts,
            # then mark the seam so the two halves stay apart.
            for payload in ctx.framer.flush_pending_answer_text():
                yield payload
            ctx.framer.answer_interrupted_by_tool = True
            for packet in ctx.document_progress.on_tool_calls(chat_message.tool_calls):
                yield ctx.framer.emit_stage(packet)
            for tc in chat_message.tool_calls:
                tc_name = (
                    tc.get("name", "tool") if isinstance(tc, dict) else getattr(tc, "name", "tool")
                )
                tc_args = tc.get("args") if isinstance(tc, dict) else getattr(tc, "args", None)
                tc_id = (
                    tc.get("id") if isinstance(tc, dict) else getattr(tc, "id", None)
                ) or tc_name
                if tc_id not in ctx.emitted_tool_call_ids:
                    ctx.emitted_tool_call_ids.add(tc_id)
                    # Document tools already have their own lifecycle
                    # packets (document_generation_*), which the frontend
                    # keeps on the current answer's turn. The generic
                    # custom_tool_start is exempt from that and would
                    # reset the in-progress answer's streaming state.
                    # `ask_user` is likewise its own card (user_clarification):
                    # a generic tool row here is the live twin of E4's double
                    # draw and would steal the card's renderer.
                    if not is_document_tool(tc_name) and not is_clarification_tool(tc_name):
                        tool_ts = int(time.time() * 1000)
                        web_search_packets = (
                            ctx.web_search_progress.on_tool_call(tc_name, tc_args, tc_id)
                            if is_web_search_tool(tc_name)
                            else None
                        )
                        if web_search_packets is not None:
                            for packet in web_search_packets:
                                packet_with_ts = dict(packet)
                                if "timestamp" not in packet_with_ts:
                                    packet_with_ts["timestamp"] = tool_ts
                                yield f"data: {json.dumps(ctx.framer.stage_tag(packet_with_ts))}\n\n"
                        else:
                            yield f"data: {json.dumps(ctx.framer.stage_tag({'type': 'custom_tool_start', 'tool_name': tc_name, 'args': tc_args, 'call_id': tc_id, 'timestamp': tool_ts}))}\n\n"
                        if ctx.stage_tracker is not None:
                            ctx.stage_tracker.add_tool(tc_name, tc_id, tc_args, tool_ts)

                        ctx.flow_stage_runs.append(
                            {
                                "tool_name": tc_name,
                                "event": "tool_start",
                                "call_id": tc_id,
                                "args": tc_args,
                                "timestamp": tool_ts,
                                "stage_node_id": ctx.framer.cur_stage_node_id(),
                            }
                        )
            continue
        elif chat_message.type == "tool":
            tool_name = getattr(message, "name", "") or ""
            tool_call_id = getattr(message, "tool_call_id", None)
            # A ToolMessage this run already closed is a re-delivery
            # from a later node's `updates`, not new activity: drop it
            # whole, before it can touch any streaming state.
            if tool_call_id:
                if tool_call_id in ctx.emitted_tool_result_ids:
                    continue
                ctx.emitted_tool_result_ids.add(tool_call_id)
            # Keep subsequent assistant phase visible even when prior phase streamed tokens.
            ctx.saw_visible_answer_tokens = False
            ctx.saw_reasoning_for_current_answer = False

            generated_file = parse_generated_file_payload(chat_message.content)
            web_search_packets = (
                ctx.web_search_progress.on_tool_result(
                    tool_name, chat_message.content, tool_call_id
                )
                if generated_file is None and is_web_search_tool(tool_name)
                else None
            )
            tool_ts = int(time.time() * 1000)
            if (
                generated_file is None
                and not is_document_tool(tool_name)
                and not is_clarification_tool(tool_name)
            ):
                # Web tools render as search_tool_*/open_url_* packets,
                # emitted below, rather than a generic tool row.
                if web_search_packets is None:
                    yield f"data: {json.dumps(ctx.framer.stage_tag({'type': 'custom_tool_delta', 'tool_name': tool_name, 'response_type': 'tool_result', 'data': chat_message.content, 'call_id': tool_call_id, 'timestamp': tool_ts}))}\n\n"
                # Their result and end time are still recorded, though:
                # without them a reloaded page shows an unfinished,
                # empty "web_search" row where the live run showed the
                # search widget with its queries and hits.
                if ctx.stage_tracker is not None:
                    ctx.stage_tracker.add_tool_result(tool_call_id, chat_message.content, tool_ts)
                ctx.flow_stage_runs.append(
                    {
                        "tool_name": tool_name,
                        "event": "tool_end",
                        "call_id": tool_call_id,
                        "data": chat_message.content,
                        "timestamp": tool_ts,
                        "stage_node_id": ctx.framer.cur_stage_node_id(),
                    }
                )

            if web_search_packets is not None:
                for packet in web_search_packets:
                    # Stamp the result packets the same way the start
                    # side does (line ~977). The graph stage strip
                    # measures the "Web Tools" node from the start/end
                    # packet timestamps; without one here it clamps the
                    # span to its 10ms floor live, then shows the real
                    # duration only after a reload rebuilds both ends
                    # from the persisted blob.
                    packet_with_ts = dict(packet)
                    packet_with_ts.setdefault("timestamp", tool_ts)
                    yield ctx.framer.emit_stage(packet_with_ts)

            if generated_file is not None:
                file_id = generated_file.get("file_id")
                if file_id not in ctx.emitted_file_ids:
                    ctx.emitted_file_ids.add(file_id)
                    yield f"data: {json.dumps(build_generated_file_packet_obj(generated_file))}\n\n"

            for packet in ctx.document_progress.on_tool_result(tool_name, chat_message.content):
                yield ctx.framer.emit_stage(packet)
            continue

        # Some providers do not stream reasoning chunks and only attach
        # reasoning to final AI message metadata. Emit fallback packets so
        # live timeline matches refresh reconstruction behavior.
        if chat_message.type == "ai":
            elapsed_duration = max(1, int(time.time() - ctx.start_time))
            if hasattr(message, "additional_kwargs") and isinstance(
                getattr(message, "additional_kwargs", None), dict
            ):
                message.additional_kwargs["processing_duration_seconds"] = elapsed_duration

        if chat_message.type == "ai" and not ctx.saw_reasoning_for_current_answer:
            if not (ai_msg_id and ai_msg_id in ctx.streamed_reasoning_message_ids):
                final_reasoning = _extract_reasoning_text_from_message(message)
                if final_reasoning:
                    yield ctx.framer.reasoning_start_frame()
                    yield ctx.framer.reasoning_delta_frame(final_reasoning)
                    ctx.saw_reasoning_for_current_answer = True

        # When token streaming is enabled, the frontend already receives
        # the assistant answer incrementally via `token` packets.
        # Emitting the final full `message` packet as well causes the UI
        # to render the full answer and then animate tokens on top of it.
        # `ctx.saw_visible_answer_tokens` is reset at every tool boundary, so
        # it cannot cover a graph that reports all of its messages at
        # once (the chatbot tool loop) — match on the message id too.
        if chat_message.type == "ai" and ctx.user_input.stream_tokens:
            if ctx.saw_visible_answer_tokens:
                continue
            if getattr(message, "id", None) in ctx.streamed_message_ids:
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

        # stream_tokens=False: the full AI message of an intermediate
        # FlowAgent stage folds into the timeline, not the bubble. The
        # final stage's message still goes through unchanged.
        if (
            chat_message.type == "ai"
            and chat_message.content
            and ctx.stage_tracker is not None
            and ctx.stage_tracker.current_is_known_nonfinal()
        ):
            cur = ctx.stage_tracker.current
            ctx.stage_tracker.add_output(chat_message.content)
            yield f"data: {json.dumps({'type': 'flow_stage_output_delta', 'stage_key': cur.key, 'stage_order': cur.order, 'iteration': cur.iteration, 'content': chat_message.content})}\n\n"
            continue

        yield f"data: {json.dumps({'type': 'message', 'content': chat_message.model_dump()})}\n\n"


async def _stream_token_events(
    ctx: _RunContext,
    event: Any,
    stream_mode: str,
) -> AsyncGenerator[str, None]:
    """Emit the frames for tokens as the model produces them.

    This is the ``messages`` side of the stream — partial chunks, not finished
    messages. It decides what the user actually sees: which call's tokens
    belong to the answer, when reasoning opens and closes, and where a tool
    call interrupts the sentence.

    The block this replaces ended the loop iteration with ``continue``; as a
    generator the equivalent is returning, which the caller's ``async for``
    treats identically.
    """
    from agents.flow_agent import FlowAgent

    if stream_mode == "messages":
        msg, metadata = event
        if "skip_stream" in metadata.get("tags", []):
            return
        if not isinstance(msg, AIMessageChunk):
            return

        # A document body streams as tool-call arguments, never as
        # tokens, so this runs regardless of `stream_tokens`.
        for packet in ctx.document_progress.on_chunk(msg):
            yield ctx.framer.emit_stage(packet)

        if not ctx.user_input.stream_tokens:
            return

        # A FlowAgent runs each stage as its own subgraph node, and a
        # single stage legitimately makes several model calls (react
        # loop, provider-split streams) each with its own chunk id —
        # so the `ctx.first_llm_call_id` "one main call" guard below would
        # drop most of every non-first stage's reasoning/answer until
        # a tool call reset it. Background calls (memory, llama-guard)
        # are already dropped above by their `skip_stream` tag, so the
        # guard is redundant here: bypass it and stream every stage.
        # A new stage (different `langgraph_checkpoint_ns` prefix) gets
        # its own reasoning block and a seam flush.
        msg_id = getattr(msg, "id", None)
        if isinstance(ctx.agent, FlowAgent):
            _stage_ns = (metadata.get("langgraph_checkpoint_ns") or "").split("|", 1)[0]
            if _stage_ns and _stage_ns != ctx.current_stage_ns:
                ctx.current_stage_ns = _stage_ns
                ctx.saw_reasoning_for_current_answer = False
                # Each stage's answer-streaming state is independent:
                # an intermediate stage's diverted output must not
                # suppress a later stage's real `message` packet.
                ctx.saw_visible_answer_tokens = False
                # `hard=True`: a stage boundary also clears an
                # unterminated <think> / <tool_call> the previous
                # stage left open (its close tag can arrive folded
                # into that stage's `updates` message), which would
                # otherwise consume this stage's answer as reasoning.
                for payload in ctx.framer.flush_pending_answer_text(hard=True):
                    yield payload
        elif msg_id:
            # Non-flow agents: filter tokens from secondary LLM calls
            # (memory extraction etc.). Each model.ainvoke() produces
            # AIMessageChunks with a unique `id`; only the first (main
            # response) call streams.
            if ctx.first_llm_call_id is None:
                ctx.first_llm_call_id = msg_id
                ctx.current_call_made_tool_calls = False
            elif msg_id != ctx.first_llm_call_id:
                # A call that ended in tool calls is always followed by
                # the answer call. When both happen inside one node (the
                # chatbot graph runs its whole tool loop in `call_model`)
                # the updates event that would reset this id only arrives
                # after the node returns — so without this the entire
                # answer is dropped and then dumped at once as a single
                # `message` packet, with no streaming animation.
                if not ctx.current_call_made_tool_calls:
                    return
                ctx.first_llm_call_id = msg_id
                ctx.current_call_made_tool_calls = False
                # Same seam as the tool-call branch above, but reached
                # when the whole loop runs inside one node, so the
                # `updates` event that would have flagged it has not
                # arrived yet. `_token_payload` decides whether the
                # halves actually need separating.
                for payload in ctx.framer.flush_pending_answer_text():
                    yield payload
                ctx.framer.answer_interrupted_by_tool = True

        if getattr(msg, "tool_call_chunks", None):
            ctx.current_call_made_tool_calls = True
            # The tag processor is still holding this call's last word
            # (it buffers up to the final whitespace). Release it now,
            # while it still belongs to the text above the tool steps —
            # the `updates` event that also flushes arrives only after
            # these `custom_tool_start` packets, which would strand the
            # word in a display group of its own below them.
            for payload in ctx.framer.flush_pending_answer_text():
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
                if tc_name and tc_id not in ctx.emitted_tool_call_ids:
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
                        return
                    ctx.emitted_tool_call_ids.add(tc_id)
                    # Same exemption as above: document tools are
                    # represented by document_generation_* packets only,
                    # and `ask_user` by its user_clarification card — so
                    # neither gets a generic tool row here.
                    if not is_document_tool(tc_name) and not is_clarification_tool(tc_name):
                        tool_ts = int(time.time() * 1000)
                        yield f"data: {json.dumps(ctx.framer.stage_tag({'type': 'custom_tool_start', 'tool_name': tc_name, 'args': tc_args, 'call_id': tc_id, 'timestamp': tool_ts}))}\n\n"
                        if ctx.stage_tracker is not None:
                            ctx.stage_tracker.add_tool(tc_name, tc_id, tc_args, tool_ts)
                        ctx.flow_stage_runs.append(
                            {
                                "tool_name": tc_name,
                                "event": "tool_start",
                                "call_id": tc_id,
                                "args": tc_args,
                                "timestamp": tool_ts,
                                "stage_node_id": ctx.framer.cur_stage_node_id(),
                            }
                        )

        content = remove_tool_calls(msg.content)
        reasoning_text = _extract_reasoning_text(msg)
        if not content and not reasoning_text:
            return

        # Anthropic extended thinking: content list'te "thinking" type block'lar
        if isinstance(content, list):
            emitted_reasoning = False
            for block in content:
                if not isinstance(block, dict):
                    return
                btype = block.get("type")
                if btype == "thinking":
                    # Anthropic extended thinking block
                    thinking_text = block.get("thinking", "")
                    if thinking_text:
                        for doc_packet in ctx.document_progress.on_tool_call_text(thinking_text):
                            yield f"data: {json.dumps(doc_packet)}\n\n"
                        if not ctx.saw_reasoning_for_current_answer:
                            yield ctx.framer.reasoning_start_frame()
                            ctx.saw_reasoning_for_current_answer = True
                        if msg_id:
                            ctx.streamed_reasoning_message_ids.add(msg_id)
                        yield ctx.framer.reasoning_delta_frame(thinking_text)
                        emitted_reasoning = True
                elif btype == "text" and block.get("thought"):
                    # Google Gemini thought block (thought=True in content part)
                    thought_text = block.get("text", "")
                    if thought_text:
                        if not ctx.saw_reasoning_for_current_answer:
                            yield ctx.framer.reasoning_start_frame()
                            ctx.saw_reasoning_for_current_answer = True
                        if msg_id:
                            ctx.streamed_reasoning_message_ids.add(msg_id)
                        yield ctx.framer.reasoning_delta_frame(thought_text)
                        emitted_reasoning = True
                elif btype == "text":
                    text = block.get("text", "")
                    if text:
                        ctx.saw_visible_answer_tokens = True
                        if msg_id:
                            ctx.streamed_message_ids.add(msg_id)
                        yield ctx.framer.token_payload(text)
            if reasoning_text and not emitted_reasoning:
                if not ctx.saw_reasoning_for_current_answer:
                    yield ctx.framer.reasoning_start_frame()
                    ctx.saw_reasoning_for_current_answer = True
                if msg_id:
                    ctx.streamed_reasoning_message_ids.add(msg_id)
                yield ctx.framer.reasoning_delta_frame(reasoning_text)
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
                if not ctx.saw_reasoning_for_current_answer:
                    yield ctx.framer.reasoning_start_frame()
                    ctx.saw_reasoning_for_current_answer = True
                if msg_id:
                    ctx.streamed_reasoning_message_ids.add(msg_id)
                yield ctx.framer.reasoning_delta_frame(reasoning_text)

            token_str = convert_message_content_to_string(content)
            if token_str:
                for evt in ctx.thinking_processor.feed(token_str):
                    # Tool-call markup never reaches the chat; it only
                    # tells us a document is being written.
                    if evt.get("type") == "tool_call_text":
                        for packet in ctx.document_progress.on_tool_call_text(
                            evt.get("content", "")
                        ):
                            yield f"data: {json.dumps(packet)}\n\n"
                        return
                    if evt.get("type") in ("reasoning_start", "reasoning_delta"):
                        ctx.saw_reasoning_for_current_answer = True
                        if msg_id:
                            ctx.streamed_reasoning_message_ids.add(msg_id)
                    if evt.get("type") == "token" and evt.get("content"):
                        ctx.saw_visible_answer_tokens = True
                        if msg_id:
                            ctx.streamed_message_ids.add(msg_id)
                        yield ctx.framer.token_payload(evt["content"])
                        return
                    yield f"data: {json.dumps(evt)}\n\n"


async def _collect_update_messages(
    ctx: _RunContext,
    event: Any,
    stream_mode: str,
    is_dynamic_agent: bool,
    new_messages: list[Any],
) -> AsyncGenerator[str, None]:
    """Gather the messages a returning node reports, and announce the step.

    Also the interrupt seam: a paused run surfaces here as a typed packet so
    the client can render decision buttons instead of a dead stream.
    ``new_messages`` is filled in place for the caller to process.
    """
    from agents.clarification.packets import packet_from_interrupt
    from agents.flow_agent import FlowAgent
    from agents.interrupts.classify import (
        HUMAN_INPUT,
        USER_CLARIFICATION,
        classify_interrupt,
    )

    if stream_mode == "updates":
        for node, updates in event.items():
            if node == "__interrupt__":
                interrupt: Interrupt
                for interrupt in updates:
                    value = interrupt.value
                    # A structured interrupt ships as its own typed SSE
                    # packet so the client can render the right controls
                    # instead of a dead stream; anything else stays a
                    # plain AI message.
                    kind = classify_interrupt(value)
                    if kind == HUMAN_INPUT:
                        yield f"data: {json.dumps({'type': 'human_input', **value})}\n\n"
                    elif kind == USER_CLARIFICATION:
                        packet = packet_from_interrupt(
                            value, str(getattr(interrupt, "id", "") or "")
                        )
                        if packet:
                            yield f"data: {json.dumps(packet)}\n\n"
                            # The turn's streaming really is over — it now
                            # waits on the user. Without a `stop` the client's
                            # pacing keeps the card queued and never reveals
                            # it live (a reload, which rebuilds a `stop`, then
                            # shows it). Its own turn: streamingUtils already
                            # advanced turn_index past the card.
                            yield f"data: {json.dumps({'type': 'stop', 'stop_reason': 'finished'})}\n\n"
                    else:
                        new_messages.append(
                            AIMessage(
                                content=value if isinstance(value, str) else json.dumps(value)
                            )
                        )
                continue
            updates = updates or {}
            update_messages = updates.get("messages", [])

            if not update_messages:
                continue

            # Emit step-start event for DynamicAgent non-infrastructure
            # nodes. FlowAgent is excluded: its nodes are user-authored
            # canvas node ids (e.g. "ReActAgent-f296f72f"), which read
            # as raw internal identifiers here — GraphStageStrip
            # already shows the same progress properly labeled, via
            # graph_stage_start/end.
            if (
                is_dynamic_agent
                and not isinstance(ctx.agent, FlowAgent)
                and node not in _INFRA_NODES
            ):
                yield f"data: {json.dumps({'type': 'custom_step_start', 'step_name': node})}\n\n"

            if "supervisor" in node or "sub-ctx.agent" in node:
                filtered_messages = []
                for msg in update_messages:
                    if isinstance(msg, AIMessage) and hasattr(msg, "tool_calls") and msg.tool_calls:
                        filtered_messages.append(msg)
                    elif isinstance(msg, ToolMessage):
                        filtered_messages.append(msg)
                    elif isinstance(msg, AIMessage) and msg.content:
                        filtered_messages.append(msg)
                update_messages = filtered_messages

            new_messages.extend(update_messages)


async def _stream_flow_stage_events(
    ctx: _RunContext,
    event: Any,
    stream_mode: str,
    is_top_level_event: bool,
    nodes_by_id: dict[str, Any],
) -> AsyncGenerator[str, None]:
    """Open and close a FlowAgent's per-stage timeline entries.

    LangGraph's ``debug`` stream is the only place a node's start and end are
    both reported, which is what makes real per-stage timing possible. Only
    stages count: control flow and boundary nodes emit no answer text, so a
    stage for them would be an empty group in the chat.
    """
    from agents.flow_agent import FlowAgent

    if stream_mode == "debug" and isinstance(ctx.agent, FlowAgent):
        debug_type = event.get("type")
        payload = event.get("payload") or {}
        node_name = payload.get("name")
        if isinstance(node_name, str) and not _is_infra_node(
            node_name, is_top_level=is_top_level_event
        ):
            # Stamp a real epoch-ms timestamp so GraphStageStrip shows
            # accurate per-stage durations both live and — via
            # ctx.flow_stage_runs, persisted below — after a refresh.
            stage_ts = int(time.time() * 1000)
            _node_type = (nodes_by_id.get(node_name) or {}).get("type") or ""
            _is_timeline_stage = (
                ctx.stage_tracker is not None
                # only nodes of the TOP-LEVEL flow graph are stages;
                # a compiled ctx.agent subgraph's internal steps ("model",
                # "call_model", …) arrive under a namespace and must
                # not be mistaken for canvas stages / loop iterations
                and is_top_level_event
                and _node_type not in _NON_STAGE_NODE_TYPES
            )
            if debug_type == "task":
                ctx.flow_stage_runs.append(
                    {"stage_name": node_name, "event": "start", "timestamp": stage_ts}
                )
                yield f"data: {json.dumps({'type': 'graph_stage_start', 'stage_name': node_name, 'timestamp': stage_ts})}\n\n"
                if _is_timeline_stage:
                    _ref = ctx.stage_tracker.begin_stage(node_name, stage_ts)
                    yield f"data: {json.dumps({'type': 'flow_stage_start', 'stage_key': _ref.key, 'node_id': _ref.node_id, 'label': _ref.label, 'iteration': _ref.iteration, 'stage_order': _ref.order, 'is_final_stage': node_name in ctx.agent.final_stage_node_ids, 'timestamp': stage_ts})}\n\n"
            elif debug_type == "task_result":
                ctx.flow_stage_runs.append(
                    {"stage_name": node_name, "event": "end", "timestamp": stage_ts}
                )
                yield f"data: {json.dumps({'type': 'graph_stage_end', 'stage_name': node_name, 'timestamp': stage_ts})}\n\n"
                if _is_timeline_stage and ctx.stage_tracker is not None:
                    # Drain the tag processor's held-back trailing word
                    # NOW, while this stage is still `current`, so it is
                    # attributed here rather than leaking into the next
                    # stage's context when the ns-change flush fires.
                    # `hard=True`: also clear an unterminated <think> /
                    # <tool_call> so it can't swallow the next stage's
                    # answer as reasoning.
                    for payload in ctx.framer.flush_pending_answer_text(hard=True):
                        yield payload
                    _rec = ctx.stage_tracker.end_stage(node_name, stage_ts, status="done")
                    if _rec is not None:
                        yield f"data: {json.dumps({'type': 'flow_stage_end', 'stage_key': _rec.ref.key, 'status': _rec.status, 'duration_ms': stage_ts - _rec.started_at, 'timestamp': stage_ts})}\n\n"


async def _emit_resumed_flow_answer(
    ctx: _RunContext, agent: Any, kwargs: dict[str, Any]
) -> AsyncGenerator[str, None]:
    """Finish a FlowAgent turn that resumed from an interrupt but streamed
    nothing.

    When a HumanInput branch goes straight to ChatOutput, resuming re-runs
    only the HumanInput node — no model call, no new message — so the stream
    ends silent and the turn looks like it died. The real answer is the last
    AI message already in state, produced before the pause. Emit it once so
    the resumed turn shows the outcome and matches what a reload reconstructs.
    Skipped when the run is still parked (another interrupt) or when this run
    already showed that message.
    """
    from langgraph.types import Command

    from agents.flow_agent import FlowAgent

    if not isinstance(agent, FlowAgent) or not isinstance(kwargs.get("input"), Command):
        return
    try:
        state = await agent.aget_state(kwargs.get("config"))
    except Exception:
        return
    if any(getattr(task, "interrupts", None) for task in getattr(state, "tasks", ()) or ()):
        return  # resume hit a fresh interrupt — its packet already went out

    messages = (getattr(state, "values", {}) or {}).get("messages", []) or []

    def _mtype(m: Any) -> str | None:
        return m.get("type") if isinstance(m, dict) else getattr(m, "type", None)

    def _mget(m: Any, key: str, default: Any = None) -> Any:
        return m.get(key, default) if isinstance(m, dict) else getattr(m, key, default)

    final_ai = next(
        (
            m
            for m in reversed(messages)
            if _mtype(m) == "ai" and _mget(m, "content") and not _mget(m, "tool_calls")
        ),
        None,
    )
    if final_ai is None:
        return
    msg_id = _mget(final_ai, "id")
    if msg_id and (msg_id in ctx.emitted_ai_message_ids or msg_id in ctx.streamed_message_ids):
        return
    try:
        chat_message = langchain_to_chat_message(final_ai)
        chat_message.run_id = str(ctx.run_id)
    except Exception:
        logger.warning("Could not finalise resumed flow answer", exc_info=True)
        return
    yield f"data: {json.dumps({'type': 'message', 'content': chat_message.model_dump()})}\n\n"


async def message_generator(
    user_input: StreamInput,
    agent_id: str = DEFAULT_AGENT,
    user_id: str | None = None,
) -> AsyncGenerator[str, None]:
    """
    Generate a stream of messages from the agent.

    This is the workhorse method for the /stream endpoint.
    """

    logger = get_logger(__name__)

    service = AssistantAgentService.get_instance()
    _, stored_config = await service.get_graph_and_config(agent_id)
    if stored_config:
        final_config = stored_config.copy()
        if user_input.agent_config:
            final_config.update(user_input.agent_config)
        user_input.agent_config = final_config

    agent = await service.get_configured_agent(agent_id, user_input.agent_config or {})

    # Detect DynamicAgent/FlowAgent so we can emit step events per meaningful
    # node — both are multi-node graphs users benefit from seeing progress on.
    from agents.dynamic_agent import DynamicAgent
    from agents.flow_agent import FlowAgent

    is_dynamic_agent = isinstance(agent, (DynamicAgent, FlowAgent))
    # Infrastructure nodes that should NOT produce step events

    kwargs, run_id = await _handle_input(user_input, agent, user_id)

    thinking_processor = ThinkingTagProcessor()
    # Document tools write their whole payload into tool-call arguments, which
    # produce no visible tokens — this turns that silence into progress packets.
    document_progress = DocumentProgressTracker()
    web_search_progress = WebSearchProgressTracker()
    # Track the first LLM call's message ID so that subsequent LLM calls
    # (e.g. background memory extraction) don't emit tokens to the stream.
    # Whether the LLM call we are currently streaming produced tool calls. A
    # call that did is always followed by an answer call, which must be let
    # through even though it has a different message id.
    # FlowAgent only: the checkpoint-ns prefix of the stage currently
    # streaming, so a stage change can open a fresh reasoning block.
    # Message ids whose tokens already reached the client, so the final full
    # `message` packet for them can be dropped without guessing.
    streamed_message_ids: set[str] = set()
    # Message ids whose reasoning tokens were streamed incrementally via
    # `reasoning_delta` packets. Prevents re-emitting reasoning as a fallback block.
    streamed_reasoning_message_ids: set[str] = set()
    # Set of AI message ids already processed in `updates`. Prevents accumulated
    # historical messages from previous subgraphs/stages being re-processed
    # in later stages and leaking reasoning/output or resetting streaming flags.
    emitted_ai_message_ids: set[str] = set()
    # Generated files already announced (a tool may emit its own live packet
    # before the node's ToolMessage reaches this loop).
    emitted_file_ids: set[str] = set()
    # Keyed by tool_call id, not name: a deep-research loop can call the same
    # tool (e.g. web_search) many times in one turn, and each call needs its
    # own custom_tool_start. This set only dedupes the *same* call appearing
    # in both the `messages` stream (tool_call_chunks) and the `updates`
    # stream (the full AI message, reported again once the node returns).
    emitted_tool_call_ids: set[str] = set()
    # The result side of the same dedupe. A node's `updates` event reports its
    # whole accumulated message list when it returns, so every ToolMessage the
    # run has produced so far arrives again at each node boundary. Without
    # this, a tool that finished in stage 1 gets re-closed in stages 2 and 3:
    # its duration stretches to the later stage's end, phantom tool badges
    # appear under stages that never called it, and the re-delivered result
    # resets `ctx.saw_reasoning_for_current_answer`, which makes the final AI
    # message re-emit reasoning that already streamed.
    emitted_tool_result_ids: set[str] = set()
    start_time = time.time()
    # Ordered flow node start/end events for this run (FlowAgent only),
    # persisted after the stream so a refreshed page can replay graph_stage_*
    # packets with real timing instead of a flat client-side clock.
    flow_stage_runs: list[dict[str, Any]] = []

    # Per-stage flow timeline (FlowAgent only): every stage but the one that
    # feeds ChatOutput has its reasoning + visible output + tool activity
    # folded into AgentTimeline under a numbered header instead of streaming
    # into the answer bubble. Gated solely on isinstance(agent, FlowAgent) —
    # a classic agent's SSE stream is provably unchanged (no flow_stage_*
    # packet is ever emitted for it).

    # The published flow version this run executes (FlowAgent only). Announced
    # once up front and persisted with the message so the chat-side flow strip
    # pins its list/canvas to the version that actually ran — a later publish
    # must not retroactively rewrite what older messages show. None when
    # nothing is published yet: the strip then falls back to the live flow.
    _flow_version_no: int | None = (
        getattr(agent, "flow_version_no", None) if isinstance(agent, FlowAgent) else None
    )

    _stage_tracker = None
    # Empty for a non-flow run: only a FlowAgent has canvas nodes, and the
    # framer is built unconditionally.
    _nodes_by_id: dict[str, Any] = {}
    if isinstance(agent, FlowAgent):
        from api.routes.flow_stage_labels import flow_stage_label
        from api.routes.flow_stage_tracker import _LiveStageTracker

        _nodes_by_id = {
            n["id"]: n
            for n in (getattr(agent, "_flow_spec_raw", None) or {}).get("nodes", [])
            if isinstance(n, dict) and "id" in n
        }
        # A final node on a loop cycle runs several times; live can't tell
        # which iteration is last, so fold every one and let the end-of-run
        # `fallbackAnswerText` (frontend) promote the last stage's text.
        _final_ids = (
            set() if getattr(agent, "final_stage_in_cycle", False) else agent.final_stage_node_ids
        )
        _stage_tracker = _LiveStageTracker(
            _final_ids,
            label_fn=lambda nid: flow_stage_label(nid, _nodes_by_id),
        )

    framer = _SseFramer(thinking_processor, _stage_tracker, _nodes_by_id)

    ctx = _RunContext(
        agent=agent,
        user_input=user_input,
        run_id=run_id,
        start_time=start_time,
        framer=framer,
        thinking_processor=thinking_processor,
        document_progress=document_progress,
        web_search_progress=web_search_progress,
        stage_tracker=_stage_tracker,
        flow_stage_runs=flow_stage_runs,
        streamed_message_ids=streamed_message_ids,
        streamed_reasoning_message_ids=streamed_reasoning_message_ids,
        emitted_ai_message_ids=emitted_ai_message_ids,
        emitted_file_ids=emitted_file_ids,
        emitted_tool_call_ids=emitted_tool_call_ids,
        emitted_tool_result_ids=emitted_tool_result_ids,
    )

    _timeline_persisted = False

    if _flow_version_no is not None:
        yield f"data: {json.dumps({'type': 'flow_version', 'version_no': _flow_version_no})}\n\n"

    try:
        async for stream_event in _with_idle_heartbeat(
            agent.astream(
                **kwargs,
                stream_mode=["updates", "messages", "custom", "debug"],
                subgraphs=True,
            ),
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
                for payload in framer.flush_idle_answer_text():
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
                _ns, stream_mode, event = stream_event
            else:
                _ns, stream_mode, event = (), *stream_event
            # Empty namespace == a node of the TOP-LEVEL flow graph. A
            # populated one (e.g. ("PipelineStage-x:uuid",)) is a step inside
            # a compiled agent subgraph — its `debug` task events must not be
            # mistaken for canvas stages.
            _is_top_level_event = not _ns

            new_messages: list = []
            if stream_mode == "updates":
                async for _frame in _collect_update_messages(
                    ctx, event, stream_mode, is_dynamic_agent, new_messages
                ):
                    yield _frame

            if stream_mode == "custom":
                new_messages = [event]

            if stream_mode == "debug" and isinstance(agent, FlowAgent):
                async for _frame in _stream_flow_stage_events(
                    ctx, event, stream_mode, _is_top_level_event, _nodes_by_id
                ):
                    yield _frame
                continue

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

            async for _frame in _stream_completed_messages(ctx, processed_messages):
                yield _frame

            async for _frame in _stream_token_events(ctx, event, stream_mode):
                yield _frame

        async for _frame in _emit_resumed_flow_answer(ctx, agent, kwargs):
            yield _frame

        # The stream itself never carries a real, persisted message id for
        # the turn it just produced (ids only exist as positions computed by
        # ChatController.get_chat_session on read). Without this, anything
        # that needs a real messageId right after sending — retrying this
        # very message, switching between regenerated alternates — silently
        # does nothing until the page is reloaded. Resolve it once, now that
        # generation is done, by reading back the just-persisted checkpoint.
        if user_input.thread_id:
            _timeline_persisted = True
            await _persist_run_timeline(
                agent,
                user_input.thread_id,
                flow_stage_runs,
                _stage_tracker,
                flow_version_no=_flow_version_no,
            )

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
        # A run cancelled or errored mid-stream never reached the happy-path
        # persist; save whatever stages completed so a refresh still shows the
        # partial per-stage timeline instead of nothing.
        if not _timeline_persisted and user_input.thread_id:
            try:
                await _persist_run_timeline(
                    agent,
                    user_input.thread_id,
                    flow_stage_runs,
                    _stage_tracker,
                    flow_version_no=_flow_version_no,
                )
            except Exception:
                logger.warning("Failed to persist partial flow timeline", exc_info=True)
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


# How many turns' worth of flow stage timelines to keep in a thread's
# metadata blob. Bounds growth on a long conversation; older turns simply
# lose their refresh-time stage timing (they still reconstruct fine).
STAGE_TIMELINE_MAX_KEPT = 60


async def _persist_run_timeline(
    agent: Any,
    thread_id: str,
    flow_stage_runs: list[dict[str, Any]],
    stage_tracker: Any | None,
    flow_version_no: int | None = None,
) -> None:
    """Close any still-open stage and persist both the legacy
    ``flow_stage_timelines`` event log and the structured ``flow_timelines``
    blob for this run. Never raises."""
    blob: dict[str, Any] | None = None
    if stage_tracker is not None:
        if stage_tracker.stage_open and stage_tracker.current is not None:
            stage_tracker.end_stage(
                stage_tracker.current.node_id, int(time.time() * 1000), status="done"
            )
        blob = stage_tracker.build_blob(stage_tracker.resolve_final_stage_key())
    await _persist_flow_stage_timeline(
        agent, thread_id, flow_stage_runs, blob, flow_version_no=flow_version_no
    )


async def _persist_flow_stage_timeline(
    agent: Any,
    thread_id: str,
    flow_stage_runs: list[dict[str, Any]],
    flow_timeline_blob: dict[str, Any] | None = None,
    flow_version_no: int | None = None,
) -> None:
    """Persist this run's ordered flow node start/end events onto the thread
    metadata, keyed by the final AI message's LangChain id (unique per
    branch — unlike the shared human message, and unlike the positional
    message_id which shifts as earlier turns change).

    graph_stage_* SSE events are otherwise live-only; without this the flow
    stage strip has no real timing after a refresh and collapses every stage
    to its ~10 ms floor. Never raises — a failure here must not break the
    stream's [DONE].
    """
    from agents.flow_agent import FlowAgent

    if not isinstance(agent, FlowAgent) or not thread_id:
        return
    if (
        not flow_stage_runs
        and not (flow_timeline_blob and flow_timeline_blob.get("stages"))
        and flow_version_no is None
    ):
        return

    try:
        from service.StoreService import get_thread_from_store, update_thread_in_store

        state = await agent.aget_state({"configurable": {"thread_id": thread_id}})
        raw_messages = (getattr(state, "values", {}) or {}).get("messages", []) or []
        ai_id: str | None = None
        for msg in reversed(raw_messages):
            msg_type = msg.get("type") if isinstance(msg, dict) else getattr(msg, "type", None)
            if msg_type != "ai":
                continue
            candidate = msg.get("id") if isinstance(msg, dict) else getattr(msg, "id", None)
            if isinstance(candidate, str) and candidate:
                ai_id = candidate
            break
        if not ai_id:
            return

        thread = await get_thread_from_store(thread_id)
        metadata = (thread or {}).get("metadata", {}) or {}
        metadata_update: dict[str, Any] = {}

        if flow_stage_runs:
            timelines = dict(metadata.get("flow_stage_timelines") or {})
            timelines[ai_id] = flow_stage_runs
            if len(timelines) > STAGE_TIMELINE_MAX_KEPT:
                for stale_key in list(timelines)[: len(timelines) - STAGE_TIMELINE_MAX_KEPT]:
                    timelines.pop(stale_key, None)
            metadata_update["flow_stage_timelines"] = timelines

        if flow_timeline_blob and flow_timeline_blob.get("stages"):
            blobs = dict(metadata.get("flow_timelines") or {})
            blobs[ai_id] = flow_timeline_blob
            if len(blobs) > STAGE_TIMELINE_MAX_KEPT:
                for stale_key in list(blobs)[: len(blobs) - STAGE_TIMELINE_MAX_KEPT]:
                    blobs.pop(stale_key, None)
            metadata_update["flow_timelines"] = blobs

        if flow_version_no is not None:
            versions = dict(metadata.get("flow_versions") or {})
            versions[ai_id] = flow_version_no
            if len(versions) > STAGE_TIMELINE_MAX_KEPT:
                for stale_key in list(versions)[: len(versions) - STAGE_TIMELINE_MAX_KEPT]:
                    versions.pop(stale_key, None)
            metadata_update["flow_versions"] = versions

        if not metadata_update:
            return

        await update_thread_in_store(
            thread_id,
            {"metadata": metadata_update},
            update_timestamp=False,
        )
    except Exception:
        logger.warning("Failed to persist flow stage timeline", exc_info=True)


# Graph nodes that are plumbing, not a step worth reporting to the user.
_INFRA_NODES = frozenset(
    {"__start__", "__end__", "__interrupt__", "tools", "agent", "model", "call_model"}
)


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
