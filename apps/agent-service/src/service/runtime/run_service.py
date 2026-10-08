"""Run service.

Holds business logic for SDK-compatible streaming runs.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
import time
from typing import Any
import uuid

from error_contract import ConfigurationError
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig

from core.http.response_models import StreamEventModel
from core.observability.logger import get_logger
from core.types.run_kinds import RunKind
from infrastructure.runtime.checkpointer import get_checkpointer
from service.chat.message_conversion import (
    extract_reasoning_from_metadata,
    split_message_content_reasoning,
)
from service.common.base import BaseService
from service.common.domain_errors import translate_domain_errors
from service.runtime.active_runs_service import (
    RunContext,
    cancel_run as active_cancel_run,
    get_run_context,
    register_run,
    unregister_run,
)
from service.stream.error_events import stream_error_event

logger = get_logger(__name__)

_connection_close_tasks: set[asyncio.Task[None]] = set()


_TOOL_PAYLOAD_CHAR_CAP = 10_000


def _cap_str(value: str) -> str:
    if len(value) > _TOOL_PAYLOAD_CHAR_CAP:
        return value[:_TOOL_PAYLOAD_CHAR_CAP] + "…"
    return value


def _json_safe(value: Any) -> Any:
    """Best-effort reduction of an arbitrary tool input/output to something
    ``json.dumps`` can serialize, with a size cap so a huge blob can't blow
    up the SSE frame."""
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return _cap_str(value)
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in list(value.items())[:200]}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in list(value)[:200]]
    return _cap_str(str(value))


def _serialize_tool_output(output: Any) -> Any:
    """A tool's result arrives as a ToolMessage, a raw string, or an
    arbitrary Python object depending on the tool — normalize to a
    JSON-serializable, size-capped shape."""
    content = getattr(output, "content", None)
    if content is not None:
        return _json_safe(content)
    return _json_safe(output)


class RunService(BaseService):
    """Service layer for run execution and run history."""

    @staticmethod
    def _extract_stage_names(config: RunnableConfig) -> list[str]:
        configurable = config.get("configurable", {}) if config else {}

        raw_stage_configs = configurable.get("stages") or configurable.get("pipeline_stages") or []
        stage_names: list[str] = []

        if isinstance(raw_stage_configs, list):
            for stage in raw_stage_configs:
                if not isinstance(stage, dict):
                    continue
                name = stage.get("name")
                if isinstance(name, str) and name.strip():
                    stage_names.append(name.strip())

        if not stage_names:
            raw_sub_agents = configurable.get("sub_agents") or []
            if isinstance(raw_sub_agents, list):
                for agent in raw_sub_agents:
                    if not isinstance(agent, dict):
                        continue
                    name = agent.get("name")
                    if isinstance(name, str) and name.strip():
                        stage_names.append(name.strip())

        return list(dict.fromkeys(stage_names))

    @staticmethod
    def _sanitize_checkpoint_values(values: dict[str, Any]) -> dict[str, Any]:
        from langgraph.types import Send

        sanitized: dict[str, Any] = {}
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

    @staticmethod
    async def _force_close_llm_connection(config: RunnableConfig) -> None:
        from langchain_ollama import ChatOllama

        configurable = config.get("configurable", {})
        model = configurable.get("llm", None)

        if model is None or not isinstance(model, ChatOllama):
            return

        try:
            client = getattr(model, "_async_client", None)
            if client is None:
                return
            await client.aclose()
            logger.info("Closed existing Ollama client for cancelled run")
        except Exception as exc:
            logger.error("Error closing Ollama client: %s", exc)

    @staticmethod
    async def _persist_partial_messages(
        thread_id: str, _run_id: str, ctx: RunContext | None, agent: Any, run_id_str: str
    ) -> None:
        if not ctx or not ctx.checkpointer:
            return

        partial_lc_messages = ctx.all_messages
        if not partial_lc_messages:
            return

        try:
            config = {"configurable": {"thread_id": thread_id}}
            current_state = await agent.aget_state(config=config)
            existing_messages = current_state.values.get("messages", []) if current_state else []
            merged_messages = list(existing_messages) + partial_lc_messages

            from langgraph.checkpoint.base import BaseCheckpointSaver

            if isinstance(ctx.checkpointer, BaseCheckpointSaver):
                channel_data = {}
                for msg in merged_messages:
                    msg_key = f"messages_bot:{msg.id}" if hasattr(msg, "id") else "messages_bot"
                    channel_data[msg_key] = msg
                await ctx.checkpointer.aput(
                    config=config,
                    channel_values=channel_data,
                    metadata={"created_by": "run-persist", "run_id": run_id_str},
                )
                logger.info(
                    "Persisted %d partial messages for thread %s",
                    len(merged_messages),
                    thread_id,
                )
        except Exception as exc:
            logger.error("Exception during persist: %s", exc)

    @staticmethod
    def _extract_final_message_text(output: Any) -> str | None:
        """Pull a human-readable reply out of a root run's ``on_chain_end``
        output.

        For a compiled LangGraph, that output is the graph's whole final
        state (``{"messages": [...], ...other state keys}``), not a plain
        string — blindly ``str()``-ing it used to leak the raw Python repr
        of the state dict (and, for nested sub-chains before the
        parent_ids filter was added, of individual BaseMessage objects
        like the system prompt) straight into the chat transcript.
        """
        messages: Any = None
        if isinstance(output, dict):
            messages = output.get("messages")
        elif isinstance(output, list):
            messages = output
        elif hasattr(output, "content"):
            content = output.content
            return content if isinstance(content, str) and content else None
        elif isinstance(output, str):
            return output or None

        if not messages:
            return None

        for message in reversed(messages):
            msg_type = message.get("type") if isinstance(message, dict) else getattr(message, "type", None)
            if msg_type != "ai":
                continue
            content = message.get("content") if isinstance(message, dict) else message.content
            if isinstance(content, str) and content:
                return content
        return None

    @staticmethod
    def _serialize_message_for_sdk(message: Any) -> dict[str, Any]:
        if hasattr(message, "model_dump"):
            return message.model_dump()
        if hasattr(message, "dict"):
            return message.dict()
        if isinstance(message, dict):
            return message
        return {"type": getattr(message, "type", "unknown"), "content": str(message)}

    async def event_generator(
        self,
        agent: Any,
        input_messages: list[Any],
        config: RunnableConfig,
        thread_id: str,
        run_id: str,
        stream_mode: list[str],
        user_id: str | None = None,  # noqa: ARG002
    ) -> AsyncGenerator[str, None]:
        run_id_str = str(uuid.uuid4())[:8]
        stage_names = self._extract_stage_names(config)
        stage_name_set = set(stage_names)
        active_stage_name: str | None = None
        reasoning_active = False

        # The flow-canvas playground wants Langflow-style extras — per-tool
        # call blocks and a token/duration footer. The raw material already
        # flows through astream_events; forward it as dedicated SSE events,
        # but ONLY for playground runs so the SDK run_route stream stays
        # byte-for-byte unchanged.
        configurable = config.get("configurable", {}) if config else {}
        emit_rich_events = configurable.get("run_kind") == RunKind.PLAYGROUND
        run_started = time.monotonic()
        usage_totals = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

        if isinstance(input_messages, dict):
            # Already a state dict (e.g. {"messages": [...]}); pass through.
            graph_input = input_messages
        else:
            if input_messages and isinstance(input_messages[0], dict):
                input_messages = [HumanMessage(**msg) for msg in input_messages]
            # Compiled LangGraph state graphs require dict input; a bare message
            # list raises InvalidUpdateError on the __start__ write. Wrap it in
            # the canonical "messages" state shape (same as AgentHelpers._handle_input).
            graph_input = {"messages": input_messages}

        if not hasattr(agent, "astream_events"):
            raise ConfigurationError(
                code="agent.streaming_unsupported", message_key="errors.agent.streaming_unsupported"
            )

        async def stream_producer() -> AsyncGenerator[str, None]:
            # Stage tracking lives in the enclosing scope so the finally-block
            # below can close a stage left open by an error mid-run.
            nonlocal active_stage_name, reasoning_active
            try:
                async for event in agent.astream_events(graph_input, config, stream_mode=stream_mode, version="v2"):
                    if cancel_event.is_set():
                        break

                    event_type = event.get("event")
                    event_name = event.get("name")
                    metadata = event.get("metadata") or {}
                    langgraph_node = metadata.get("langgraph_node")

                    stage_candidate = None
                    for candidate in (event_name, langgraph_node):
                        if isinstance(candidate, str) and candidate.strip() in stage_name_set:
                            stage_candidate = candidate.strip()
                            break

                    if stage_candidate and event_type == "on_chain_start":
                        if active_stage_name and active_stage_name != stage_candidate:
                            yield StreamEventModel(
                                event="message", data={"type": "graph_stage_end", "stage_name": active_stage_name}
                            ).to_sse()
                        if active_stage_name != stage_candidate:
                            active_stage_name = stage_candidate
                            yield StreamEventModel(
                                event="message",
                                data={
                                    "type": "graph_stage_start",
                                    "stage_name": stage_candidate,
                                    "stage_index": stage_names.index(stage_candidate),
                                },
                            ).to_sse()
                        continue

                    if stage_candidate and event_type == "on_chain_end" and active_stage_name == stage_candidate:
                        yield StreamEventModel(
                            event="message",
                            data={
                                "type": "graph_stage_end",
                                "stage_name": stage_candidate,
                                "stage_index": stage_names.index(stage_candidate),
                            },
                        ).to_sse()
                        active_stage_name = None
                        continue

                    if event_type in {"custom", "on_custom_event"}:
                        payload = event.get("data", {})
                        if isinstance(payload, dict):
                            yield StreamEventModel(event="message", data=payload).to_sse()
                        continue

                    if emit_rich_events and event_type == "on_tool_start":
                        yield StreamEventModel(
                            event="message",
                            data={
                                "type": "tool_call_start",
                                "call_id": event.get("run_id"),
                                "name": event.get("name") or "tool",
                                "input": _json_safe(event.get("data", {}).get("input")),
                            },
                        ).to_sse()
                        continue
                    if emit_rich_events and event_type == "on_tool_end":
                        yield StreamEventModel(
                            event="message",
                            data={
                                "type": "tool_call_end",
                                "call_id": event.get("run_id"),
                                "name": event.get("name") or "tool",
                                "output": _serialize_tool_output(event.get("data", {}).get("output")),
                            },
                        ).to_sse()
                        continue
                    if emit_rich_events and event_type == "on_chat_model_end":
                        model_out = event.get("data", {}).get("output")
                        usage = getattr(model_out, "usage_metadata", None) or {}
                        if not usage:
                            resp_meta = getattr(model_out, "response_metadata", {}) or {}
                            token_usage = resp_meta.get("token_usage") or resp_meta.get("usage") or {}
                            usage = {
                                "input_tokens": token_usage.get("prompt_tokens")
                                or token_usage.get("input_tokens")
                                or 0,
                                "output_tokens": token_usage.get("completion_tokens")
                                or token_usage.get("output_tokens")
                                or 0,
                                "total_tokens": token_usage.get("total_tokens") or 0,
                            }
                        input_tokens = int(usage.get("input_tokens") or 0)
                        output_tokens = int(usage.get("output_tokens") or 0)
                        total_tokens = int(usage.get("total_tokens") or (input_tokens + output_tokens))
                        if input_tokens or output_tokens or total_tokens:
                            usage_totals["input_tokens"] += input_tokens
                            usage_totals["output_tokens"] += output_tokens
                            usage_totals["total_tokens"] += total_tokens
                            yield StreamEventModel(event="message", data={"type": "usage", **usage_totals}).to_sse()
                        continue

                    if event_type == "on_chat_model_stream":
                        chunk = event.get("data", {}).get("chunk")
                        if chunk is None:
                            continue
                        # Reasoning-capable models surface "thinking" text in one
                        # of two shapes: some Ollama/DeepSeek variants attach it to
                        # a chunk's additional_kwargs; Anthropic and Gemini stream
                        # it inline as `content` blocks alongside the visible
                        # answer. Pull both out and surface a reasoning_start/
                        # reasoning_delta/reasoning_done trio so the client can
                        # show a live "Thinking…" block, same as the main chat.
                        block_reasoning, visible_content = split_message_content_reasoning(chunk.content)
                        reasoning_piece = extract_reasoning_from_metadata(chunk, strip=False) or block_reasoning
                        if reasoning_piece:
                            if not reasoning_active:
                                reasoning_active = True
                                yield StreamEventModel(event="message", data={"type": "reasoning_start"}).to_sse()
                            yield StreamEventModel(
                                event="message", data={"type": "reasoning_delta", "reasoning": reasoning_piece}
                            ).to_sse()
                        if visible_content:
                            if reasoning_active:
                                reasoning_active = False
                                yield StreamEventModel(event="message", data={"type": "reasoning_done"}).to_sse()
                            yield StreamEventModel(
                                event="message", data={"type": "token", "content": visible_content}
                            ).to_sse()
                    elif (
                        event_type == "on_chain_end"
                        and event.get("run_id")
                        # astream_events v2 fires on_chain_end for every
                        # nested runnable (prompt templates, tool calls,
                        # individual graph nodes), not just the graph's own
                        # completion — only the root run (empty parent_ids)
                        # is a candidate for "the assistant's reply".
                        and not event.get("parent_ids")
                    ):
                        output = event.get("data", {}).get("output")
                        text = self._extract_final_message_text(output)
                        if text:
                            yield StreamEventModel(event="message", data={"type": "message", "content": text}).to_sse()
            except Exception as exc:
                logger.exception("Run stream producer failed")
                # Surface the failure to the client instead of a silent empty stream.
                yield stream_error_event(exc).to_sse()

        cancel_event = register_run(thread_id, run_id_str)
        ctx = get_run_context(thread_id, run_id_str)
        try:
            if ctx:
                ctx.agent = agent
                ctx.config = config
                ctx.checkpointer = getattr(agent, "checkpointer", None)
            async for line in stream_producer():
                if cancel_event.is_set():
                    break
                yield line
        except asyncio.CancelledError:
            logger.info("Run generator cancelled for thread %s", thread_id)
        except Exception as exc:
            logger.exception("Run event generator failed")
            yield stream_error_event(exc).to_sse()
        finally:
            unregister_run(thread_id, run_id_str)
            if ctx:
                try:
                    await self._persist_partial_messages(thread_id, run_id_str, ctx, agent, str(run_id))
                except Exception as exc:
                    logger.error("Persist error: %s", exc)
            if active_stage_name:
                yield StreamEventModel(
                    event="message", data={"type": "graph_stage_end", "stage_name": active_stage_name}
                ).to_sse()
            if reasoning_active:
                yield StreamEventModel(event="message", data={"type": "reasoning_done"}).to_sse()
            if emit_rich_events:
                yield StreamEventModel(
                    event="message",
                    data={"type": "run_end", "duration_ms": int((time.monotonic() - run_started) * 1000)},
                ).to_sse()
            yield "data: [DONE]\n\n"

    @translate_domain_errors
    async def cancel_run(self, thread_id: str, run_id: str) -> dict[str, Any]:
        cancelled = active_cancel_run(thread_id, run_id)
        ctx = get_run_context(thread_id, run_id)

        if ctx and ctx.config is not None:
            task = asyncio.create_task(self._force_close_llm_connection(ctx.config))
            _connection_close_tasks.add(task)
            task.add_done_callback(_connection_close_tasks.discard)

        if cancelled:
            return {"status": "ok", "thread_id": thread_id, "run_id": run_id}

        if ctx:
            await self._persist_partial_messages(thread_id, run_id, ctx, ctx.agent, run_id)

        return {"status": "accepted"}

    @translate_domain_errors
    async def get_thread_history(
        self, thread_id: str, limit: int = 100, before: str | None = None
    ) -> list[dict[str, Any]]:
        saver = get_checkpointer()
        if not saver:
            raise ConfigurationError(
                code="agent.checkpointer_unavailable", message_key="errors.agent.checkpointer_unavailable"
            )

        config = {"configurable": {"thread_id": thread_id}}
        history: list[dict[str, Any]] = []

        async for checkpoint in saver.alist(config, limit=limit, before=before):
            raw_values = checkpoint.checkpoint.get("channel_values", {}) if checkpoint.checkpoint else {}
            values = self._sanitize_checkpoint_values(raw_values)

            if "messages" in values:
                values["messages"] = [self._serialize_message_for_sdk(m) for m in values.get("messages", [])]

            parent_checkpoint = None
            if checkpoint.parent_config and checkpoint.parent_config.get("configurable"):
                parent_checkpoint = {
                    "thread_id": checkpoint.parent_config["configurable"].get("thread_id", thread_id),
                    "checkpoint_id": checkpoint.parent_config["configurable"].get("checkpoint_id"),
                    "checkpoint_ns": checkpoint.parent_config["configurable"].get("checkpoint_ns", ""),
                }

            history.append(
                {
                    "values": values,
                    "next": [],
                    "checkpoint": {
                        "thread_id": thread_id,
                        "checkpoint_id": checkpoint.checkpoint["id"] if checkpoint.checkpoint else None,
                    },
                    "metadata": checkpoint.metadata,
                    "created_at": checkpoint.metadata.get("created_at") if checkpoint.metadata else None,
                    "parent_config": checkpoint.parent_config,
                    "parent_checkpoint": parent_checkpoint,
                }
            )

        return history


# Singleton instance
_run_service: RunService | None = None


def get_run_service() -> RunService:
    """Get the singleton RunService instance."""
    global _run_service
    if _run_service is None:
        _run_service = RunService()
    return _run_service
