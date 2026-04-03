"""
Run routes — SDK-compatible streaming.

POST /threads/{thread_id}/runs/stream
POST /threads/{thread_id}/history

These endpoints power the ``@langchain/langgraph-sdk`` client and
Open Agent Platform's chat interface.
"""

import asyncio
import inspect
import json
import traceback
import uuid as uuid_module
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from langchain_core.runnables import RunnableConfig

from agents import get_agent_or_lazy, get_all_agent_info
from core.logger import get_logger
from service.ActiveRunsService import (
    RunContext,
    cancel_run,
    get_run_context,
    register_run,
    unregister_run,
)
from service.AuthService import extract_user_id_from_token, verify_bearer
from service.CheckpointerService import get_checkpointer
from service.Schemas import RunCancel, RunCreate, ThreadHistoryRequest, ThreadState
from service.Utils import convert_input_messages

logger = get_logger(__name__)

router = APIRouter(tags=["threads"], dependencies=[Depends(verify_bearer)])


# =============================================================================
# Helpers
# =============================================================================


def _sanitize_checkpoint_values(values: dict) -> dict:
    """Remove non-serializable types like Send from checkpoint values."""
    from langgraph.types import Send

    sanitized: dict = {}
    for key, value in values.items():
        if isinstance(value, Send):
            sanitized[key] = {"__type__": "Send", "node": value.node, "arg": str(value.arg)[:500]}
        elif isinstance(value, list):
            sanitized[key] = [
                {"__type__": "Send", "node": v.node, "arg": str(v.arg)[:500]}
                if isinstance(v, Send)
                else v
                for v in value
            ]
        else:
            sanitized[key] = value
    return sanitized


async def _force_close_llm_connection(config: RunnableConfig) -> None:
    """Force-close the httpx client so the TCP stream to Ollama is terminated."""
    import httpx
    from langchain_ollama import ChatOllama

    configurable = config.get("configurable", {})
    model = configurable.get("llm", None)

    if model is None:
        logger.debug("No model in config, skipping close")
        return
    if not isinstance(model, ChatOllama):
        logger.debug("No _async_client on model %s", type(model).__name__)
        return

    try:
        client = getattr(model, "_async_client", None)
        if client is None:
            logger.debug("Already closed/closing this client, skipping")
            return
        await client.aclose()
        logger.info("Closed old httpx client & swapped in new one")
    except Exception as exc:
        logger.error("Error closing httpx client: %s", exc)


async def _persist_partial_messages(
    thread_id: str, run_id: str, ctx: RunContext | None, agent: Any, run_id_str: str
) -> None:
    """Persist any messages accumulated so far into the checkpoint."""
    if not ctx or not ctx.checkpointer:
        logger.debug("No checkpointer, skipping persist")
        return

    partial_lc_messages = ctx.all_messages
    logger.debug("partial_lc_messages: %d", len(partial_lc_messages))

    if not partial_lc_messages:
        logger.debug("No partial messages to persist, returning.")
        return

    try:
        config = {"configurable": {"thread_id": thread_id}}
        current_state = await agent.aget_state(config=config)
        existing_messages = current_state.values.get("messages", []) if current_state else []
        merged_messages = list(existing_messages) + partial_lc_messages
        logger.debug("Merged messages count: %d", len(merged_messages))

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
            logger.info("Persisted %d messages for thread %s", len(merged_messages), thread_id)
    except Exception as exc:
        logger.error("Exception during persist: %s", exc)


# Add this to imports if missing
from dataclasses import dataclass
from typing import TYPE_CHECKING

from langchain_core.runnables import RunnableConfig

if TYPE_CHECKING:
    from service.ActiveRunsService import RunContext

router = APIRouter(tags=["threads"], dependencies=[Depends(verify_bearer)])


# =============================================================================
# POST /threads/{thread_id}/runs/stream
# =============================================================================


@dataclass
class StreamInput:
    """Schema for stream input."""

    assistant_id: str | None = None
    input: dict | None = None
    model: str | None = None
    stream_tokens: bool = True


async def _parse_input(request: Request) -> tuple[dict, str, str, str | None, str]:
    """Parse request body and extract relevant fields."""
    try:
        body = await request.json()
    except Exception:
        body = {}

    assistant_id = body.get("assistant_id")
    user_input = body.get("input", {})
    if isinstance(user_input, str):
        user_input = {"messages": [{"type": "human", "content": user_input}]}

    model = body.get("model")
    thread_id = body.get("thread_id", "")
    run_id = str(uuid_module.uuid4())

    api_key = request.headers.get("x-api-key")
    user_id = extract_user_id_from_token(api_key) if api_key else None

    return user_input, thread_id, run_id, model, user_id


@router.post("/threads/{thread_id}/runs/stream")
async def stream_run(
    request: Request, thread_id: str, request_obj: StreamInput
) -> StreamingResponse:
    """Stream runs for a thread using SDK-compatible format."""
    logger.debug("stream_run called for thread_id: %s", thread_id)
    logger.debug("All headers: %s", dict(request.headers))

    api_key = request.headers.get("x-api-key")
    user_id = extract_user_id_from_token(api_key) if api_key else None
    logger.debug("extracted user_id: %s", user_id)

    stored = None
    assistant_id = request_obj.assistant_id
    if not assistant_id:
        from service.StoreService import get_assistant_from_store

        stored = await get_assistant_from_store(thread_id)
        assistant_id = stored.get("assistant_id") if stored else None

    if not assistant_id:
        logger.debug("No stored assistant found")
        raise HTTPException(status_code=400, detail="assistant_id is required")

    graph_id = assistant_id
    logger.debug("stream_run: Getting agent for graph_id: %s", graph_id)

    agent = get_agent_or_lazy(graph_id)
    logger.debug("stream_run: Got agent type: %s", type(agent).__name__)

    from dataclasses import asdict

    input_messages = convert_input_messages(request_obj.input or {})
    stream_mode = (
        ["values", "updates", "custom"] if request_obj.stream_tokens else ["values", "updates"]
    )

    config = RunnableConfig(
        configurable={
            "thread_id": thread_id,
            "user_id": user_id,
            "model": request_obj.model or "ollama",
        },
        tags=request_obj.stream_tokens and ["stream-tokens"] or [],
    )

    return StreamingResponse(
        event_generator(agent, input_messages, config, thread_id, run_id, stream_mode, user_id),
        media_type="text/event-stream",
    )


async def event_generator(
    agent: Any,
    input_messages: list[Any],
    config: RunnableConfig,
    thread_id: str,
    run_id: str,
    stream_mode: list[str],
    user_id: str | None = None,
) -> AsyncGenerator[str, None]:
    """Core async generator that yields SSE events."""
    from langchain_core.messages import HumanMessage

    run_id_str = str(uuid_module.uuid4())[:8]
    cancel_event = register_run(thread_id, run_id_str)

    ctx = get_run_context(thread_id, run_id_str)
    if ctx:
        ctx.agent = agent
        ctx.config = config
        ctx.checkpointer = agent.checkpointer

    if input_messages and isinstance(input_messages[0], dict):
        input_messages = [HumanMessage(**msg) for msg in input_messages]

    try:
        logger.debug("event_generator: Starting stream with run_id=%s", run_id_str)

        use_astream_events = hasattr(agent, "astream_events")

        logger.debug("event_generator: Agent is LazyLoadingAgent: %s", use_astream_events)

        async def stream_producer():
            try:
                async for event in agent.astream_events(
                    input_messages, config, stream_mode=stream_mode, version="v2"
                ):
                    if cancel_event.is_set():
                        logger.info("Exiting for run %s (cancelled=True)", run_id_str)
                        break

                    event_type = event.get("event")
                    if event_type == "on_chat_model_stream":
                        chunk = event.get("data", {}).get("chunk")
                        if chunk and chunk.content:
                            yield f"data: {json.dumps({'type': 'token', 'content': chunk.content})}\n\n"
                    elif event_type == "on_chain_end" and event.get("run_id"):
                        run_id_val = str(event["run_id"])[:8]
                        output = event.get("data", {}).get("output")
                        if output:
                            yield f"data: {json.dumps({'type': 'message', 'content': str(output)})}\n\n"

            except Exception as exc:
                logger.error("_force_close_llm_connection error: %s", exc)
            finally:
                logger.info("Exiting for run %s", run_id_str)

        task = asyncio.create_task(stream_producer(), name=f"stream-{run_id_str}")
        if ctx:
            ctx.agent_task = task

        logger.info("Started stream_producer task for run %s", run_id_str)

        try:
            async for line in task:
                if cancel_event.is_set():
                    logger.info("Cancel/disconnect detected for run %s", run_id_str)
                    if task and not task.done():
                        task.cancel()
                        logger.info("Cancelled agent task for run %s", run_id_str)
                    break
                yield line
        except asyncio.CancelledError:
            logger.info("Task cancelled for run %s", run_id_str)
            if task and not task.done():
                task.cancel()
                logger.info("Cancelled agent task for run %s", run_id_str)

        logger.debug("event_generator: Stream completed")

    except Exception as exc:
        logger.error("Error in event_generator: %s", exc)
        yield f"data: {json.dumps({'type': 'error', 'content': str(exc)})}\n\n"
    finally:
        if ctx:
            ctx.agent_task = None

        if ctx and ctx.checkpointer:
            try:
                await _persist_partial_messages(thread_id, run_id_str, ctx, agent, str(run_id))
            except Exception as exc:
                logger.error("Persist error: %s", exc)

        unregister_run(thread_id, run_id_str)
        yield "data: [DONE]\n\n"


# =============================================================================
# POST /threads/{thread_id}/runs/{run_id}/cancel
# =============================================================================


@router.post("/threads/{thread_id}/runs/{run_id}/cancel")
async def cancel_run_endpoint(thread_id: str, run_id: str) -> dict:
    """Cancel an active run."""
    logger.info("cancel_run_endpoint called for thread_id=%s, run_id=%s", thread_id, run_id)

    cancelled = cancel_run(thread_id, run_id)
    if cancelled:
        return {"status": "ok", "thread_id": thread_id, "run_id": run_id}

    ctx = get_run_context(thread_id, run_id)
    if ctx:
        logger.info("Persisting partial messages before cancel")
        try:
            await _persist_partial_messages(thread_id, run_id, ctx, ctx.agent, run_id)
            logger.info("Partial messages persisted successfully")
        except Exception as exc:
            logger.error("Persist failed: %s", exc)

    return {"status": "accepted"}


# =============================================================================
# POST /threads/{thread_id}/history
# =============================================================================


@router.post("/threads/{thread_id}/history")
async def get_thread_history(thread_id: str, request: ThreadHistoryRequest) -> list[ThreadState]:
    """Get thread history specific checkpointer states."""
    saver = get_checkpointer()
    if not saver:
        raise HTTPException(status_code=503, detail="Checkpointer not initialized")

    config = {"configurable": {"thread_id": thread_id}}

    try:
        history: list[ThreadState] = []
        async for checkpoint in saver.alist(config, limit=request.limit, before=request.before):
            raw_values = (
                checkpoint.checkpoint.get("channel_values", {}) if checkpoint.checkpoint else {}
            )
            values = _sanitize_checkpoint_values(raw_values)

            if "messages" in values:
                values["messages"] = [
                    _serialize_message_for_sdk(m) for m in values.get("messages", [])
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

            state = ThreadState(
                values=values,
                next=[],
                checkpoint={
                    "thread_id": thread_id,
                    "checkpoint_id": checkpoint.checkpoint["id"] if checkpoint.checkpoint else None,
                },
                metadata=checkpoint.metadata,
                created_at=checkpoint.metadata.get("created_at") if checkpoint.metadata else None,
                parent_config=checkpoint.parent_config,
                parent_checkpoint=parent_checkpoint,
            )
            history.append(state)

        return history
    except Exception as e:
        logger.error("Error fetching history for thread %s: %s", thread_id, e)
        raise HTTPException(status_code=500, detail=str(e))


def _serialize_message_for_sdk(message: Any) -> dict:
    """Serialize a message for SDK response."""
    if hasattr(message, "model_dump"):
        return message.model_dump()
    elif hasattr(message, "dict"):
        return message.dict()
    elif isinstance(message, dict):
        return message
    else:
        return {"type": getattr(message, "type", "unknown"), "content": str(message)}
