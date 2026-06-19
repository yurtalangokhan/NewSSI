"""Run service.

Holds business logic for SDK-compatible streaming runs.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import AsyncGenerator
from typing import Any

from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig

from service.ActiveRunsService import (
    RunContext,
    get_run_context,
    register_run,
    unregister_run,
)
from service.ActiveRunsService import (
    cancel_run as active_cancel_run,
)
from service.CheckpointerService import get_checkpointer

logger = logging.getLogger(__name__)


class RunService:
    """Service layer for run execution and run history."""

    @staticmethod
    def _sanitize_checkpoint_values(values: dict[str, Any]) -> dict[str, Any]:
        from langgraph.types import Send

        sanitized: dict[str, Any] = {}
        for key, value in values.items():
            if isinstance(value, Send):
                sanitized[key] = {"__type__": "Send", "node": value.node, "arg": str(value.arg)[:500]}
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
        thread_id: str, run_id: str, ctx: RunContext | None, agent: Any, run_id_str: str
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
        user_id: str | None = None,
    ) -> AsyncGenerator[str, None]:
        run_id_str = str(uuid.uuid4())[:8]
        cancel_event = register_run(thread_id, run_id_str)

        ctx = get_run_context(thread_id, run_id_str)
        if ctx:
            ctx.agent = agent
            ctx.config = config
            ctx.checkpointer = getattr(agent, "checkpointer", None)

        if input_messages and isinstance(input_messages[0], dict):
            input_messages = [HumanMessage(**msg) for msg in input_messages]

        if not hasattr(agent, "astream_events"):
            raise RuntimeError("Agent does not support streaming")

        async def stream_producer() -> AsyncGenerator[str, None]:
            try:
                async for event in agent.astream_events(
                    input_messages, config, stream_mode=stream_mode, version="v2"
                ):
                    if cancel_event.is_set():
                        break

                    event_type = event.get("event")
                    if event_type in {"custom", "on_custom_event"}:
                        payload = event.get("data", {})
                        if isinstance(payload, dict):
                            yield f"data: {json.dumps(payload)}\n\n"
                        continue
                    if event_type == "on_chat_model_stream":
                        chunk = event.get("data", {}).get("chunk")
                        if chunk and chunk.content:
                            yield f"data: {json.dumps({'type': 'token', 'content': chunk.content})}\n\n"
                    elif event_type == "on_chain_end" and event.get("run_id"):
                        output = event.get("data", {}).get("output")
                        if output:
                            yield f"data: {json.dumps({'type': 'message', 'content': str(output)})}\n\n"
            except Exception as exc:
                logger.error("stream_producer error: %s", exc)
            finally:
                return

        try:
            async for line in stream_producer():
                if cancel_event.is_set():
                    break
                yield line
        except asyncio.CancelledError:
            logger.info("Run generator cancelled for thread %s", thread_id)
        except Exception as exc:
            logger.error("Error in event_generator: %s", exc)
            yield f"data: {json.dumps({'type': 'error', 'content': str(exc)})}\n\n"
        finally:
            if ctx:
                try:
                    await self._persist_partial_messages(thread_id, run_id_str, ctx, agent, str(run_id))
                except Exception as exc:
                    logger.error("Persist error: %s", exc)
            unregister_run(thread_id, run_id_str)
            yield "data: [DONE]\n\n"

    async def cancel_run(self, thread_id: str, run_id: str) -> dict[str, Any]:
        cancelled = active_cancel_run(thread_id, run_id)
        ctx = get_run_context(thread_id, run_id)

        if ctx and ctx.config is not None:
            asyncio.create_task(self._force_close_llm_connection(ctx.config))

        if cancelled:
            return {"status": "ok", "thread_id": thread_id, "run_id": run_id}

        if ctx:
            await self._persist_partial_messages(thread_id, run_id, ctx, ctx.agent, run_id)

        return {"status": "accepted"}

    async def get_thread_history(
        self, thread_id: str, limit: int = 100, before: str | None = None
    ) -> list[dict[str, Any]]:
        saver = get_checkpointer()
        if not saver:
            raise RuntimeError("Checkpointer not initialized")

        config = {"configurable": {"thread_id": thread_id}}
        history: list[dict[str, Any]] = []

        async for checkpoint in saver.alist(config, limit=limit, before=before):
            raw_values = checkpoint.checkpoint.get("channel_values", {}) if checkpoint.checkpoint else {}
            values = self._sanitize_checkpoint_values(raw_values)

            if "messages" in values:
                values["messages"] = [
                    self._serialize_message_for_sdk(m) for m in values.get("messages", [])
                ]

            parent_checkpoint = None
            if checkpoint.parent_config and checkpoint.parent_config.get("configurable"):
                parent_checkpoint = {
                    "thread_id": checkpoint.parent_config["configurable"].get(
                        "thread_id", thread_id
                    ),
                    "checkpoint_id": checkpoint.parent_config["configurable"].get("checkpoint_id"),
                    "checkpoint_ns": checkpoint.parent_config["configurable"].get(
                        "checkpoint_ns", ""
                    ),
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
