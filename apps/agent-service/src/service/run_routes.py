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
import logging
import traceback
import uuid as uuid_module
from datetime import datetime, timezone
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from agents import get_agent_or_lazy, get_all_agent_info
from core import settings
from service.active_runs import (
    register_run,
    unregister_run,
    cancel_run,
    cancel_all_for_thread,
    is_cancelled,
    get_run_context,
)
from service.auth import extract_user_id_from_token, verify_bearer
from service.checkpointer import get_checkpointer
from service.schemas import RunCreate, RunCancel, ThreadHistoryRequest, ThreadState
from service.utils import convert_input_messages

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(verify_bearer)])


# =============================================================================
# Helpers
# =============================================================================

# Track the httpx client we intend to close so double-calls are harmless.
_closing_httpx_ids: set[int] = set()


async def _force_close_llm_connection(config: dict | None = None) -> None:
    """Close the httpx TCP connection used by the cached ChatOllama singleton.

    ``get_model()`` returns a **cached singleton** ChatOllama.  Its internal
    path is: ``ChatOllama._async_client._client`` → ``httpx.AsyncClient``.
    Closing that httpx client kills the TCP stream to Ollama, which makes
    Ollama stop token generation immediately.

    After closing we create a **fresh** httpx client with the same settings
    and swap it in so that subsequent requests still work.

    This function is idempotent — if the *same* httpx client has already
    been closed (or is being closed) by a concurrent call, we skip it.
    """
    try:
        from core import get_model, settings
        import httpx as _httpx

        model_name = settings.DEFAULT_MODEL
        if config and config.get("configurable", {}).get("model"):
            model_name = config["configurable"]["model"]

        model = get_model(model_name)
        # ChatOllama → ._async_client (ollama.AsyncClient) → ._client (httpx.AsyncClient)
        ollama_aclient = getattr(model, "_async_client", None)
        if ollama_aclient is None:
            print(f"[_force_close_llm_connection] No _async_client on model {type(model).__name__}")
            return

        old_httpx = getattr(ollama_aclient, "_client", None)
        if old_httpx is None or not isinstance(old_httpx, _httpx.AsyncClient):
            print(
                f"[_force_close_llm_connection] No httpx client on {type(ollama_aclient).__name__}"
            )
            return

        # Guard: if this exact httpx client is already being/been closed, skip
        old_id = id(old_httpx)
        if old_id in _closing_httpx_ids:
            print("[_force_close_llm_connection] Already closed/closing this client, skipping")
            return
        _closing_httpx_ids.add(old_id)

        # Create a fresh httpx client with the same base_url & headers
        new_httpx = _httpx.AsyncClient(
            base_url=old_httpx._base_url,
            follow_redirects=True,
            timeout=None,
            headers=dict(old_httpx.headers),
        )
        # Swap BEFORE closing so any concurrent code sees the new client
        ollama_aclient._client = new_httpx
        # Now close the old one — this sends TCP FIN/RST to Ollama
        await old_httpx.aclose()
        print("[_force_close_llm_connection] Closed old httpx client & swapped in new one")

        # Cleanup tracking set (keep it small)
        _closing_httpx_ids.discard(old_id)
    except Exception as exc:
        print(f"[_force_close_llm_connection] Error: {exc}")
        logger.warning("_force_close_llm_connection failed: %s", exc)


def _sanitize_checkpoint_values(values: dict) -> dict:
    """Remove non-serializable types like Send from checkpoint values."""
    from langgraph.types import Send

    sanitized: dict = {}
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


async def _persist_partial_messages(
    agent: Any,
    config: dict,
    all_messages: list[dict],
    checkpointer: Any,
) -> None:
    """Write partially-streamed messages into the thread checkpoint.

    When a run is cancelled mid-stream the LLM node hasn't completed, so
    LangGraph never persists the partial AI reply.  We use
    ``graph.aupdate_state()`` to inject accumulated messages so they
    survive a page refresh.
    """
    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

    print(
        f"[_persist_partial_messages] all_messages types: {[m.get('type') for m in all_messages]}"
    )

    def _dict_to_message(d: dict):
        """Convert a serialized message dict back to a LangChain message."""
        msg_type = d.get("type", "ai")
        content = d.get("content", "")
        kwargs: dict[str, Any] = {}
        if d.get("id"):
            kwargs["id"] = d["id"]
        if d.get("name"):
            kwargs["name"] = d["name"]
        if d.get("tool_calls"):
            kwargs["tool_calls"] = d["tool_calls"]
        if msg_type == "human":
            return HumanMessage(content=content, **kwargs)
        if msg_type == "tool":
            kwargs["tool_call_id"] = d.get("tool_call_id", "")
            return ToolMessage(content=content, **kwargs)
        return AIMessage(content=content, **kwargs)

    print("[_persist_partial_messages] ENTERED")
    logger.debug("[_persist_partial_messages] ENTERED")
    try:
        print(
            f"[_persist_partial_messages] called: agent={type(agent)}, config={config is not None}, all_messages={len(all_messages)}, checkpointer={checkpointer is not None}"
        )
        logger.debug(
            f"[_persist_partial_messages] called: agent={type(agent)}, config={config is not None}, all_messages={len(all_messages)}, checkpointer={checkpointer is not None}"
        )
        # Only persist AI / tool messages (the human message is already in
        # the checkpoint from the invoke).
        partial_lc_messages = [
            _dict_to_message(m) for m in all_messages if m.get("type") in ("ai", "tool")
        ]
        print(f"[_persist_partial_messages] partial_lc_messages: {len(partial_lc_messages)}")
        logger.debug(f"[_persist_partial_messages] partial_lc_messages: {len(partial_lc_messages)}")
        if not partial_lc_messages:
            print("[_persist_partial_messages] No partial messages to persist, returning.")
            logger.debug("[_persist_partial_messages] No partial messages to persist, returning.")
            return

        # Get the compiled graph so we can call aupdate_state
        graph = None
        from agents.lazy_agent import LazyLoadingAgent

        if isinstance(agent, LazyLoadingAgent):
            graph = agent.get_graph()
        else:
            graph = agent

        print(
            f"[_persist_partial_messages] graph: {type(graph)}, has aupdate_state: {hasattr(graph, 'aupdate_state')}"
        )
        logger.debug(
            f"[_persist_partial_messages] graph: {type(graph)}, has aupdate_state: {hasattr(graph, 'aupdate_state')}"
        )

        if graph and hasattr(graph, "aupdate_state"):
            # We need a valid node name for as_node.  Pick the first node
            # from the graph that looks like it handles messages.
            # Fall back to the first node if nothing better is found.
            node_name = None
            if hasattr(graph, "nodes"):
                node_names = [n for n in graph.nodes if n not in ("__start__", "__end__")]
                print(f"[_persist_partial_messages] graph.nodes: {node_names}")
                logger.debug(f"[_persist_partial_messages] graph.nodes: {node_names}")
                # Prefer "agent" or "supervisor" node names (common in ReAct / supervisor graphs)
                for candidate in ("agent", "supervisor", "chatbot"):
                    if candidate in node_names:
                        node_name = candidate
                        break
                if node_name is None and node_names:
                    node_name = node_names[0]
            print(f"[_persist_partial_messages] node_name: {node_name}")
            logger.debug(f"[_persist_partial_messages] node_name: {node_name}")

            # Ensure checkpointer is available via config so aupdate_state
            # can find it even if the graph's own checkpointer is None.
            update_config = dict(config)
            update_config.setdefault("configurable", {})
            update_config["configurable"]["__pregel_checkpointer"] = checkpointer

            print(
                f"[_persist_partial_messages] calling aupdate_state with {len(partial_lc_messages)} messages"
            )
            logger.debug(
                f"[_persist_partial_messages] calling aupdate_state with {len(partial_lc_messages)} messages"
            )
            await graph.aupdate_state(
                update_config,
                {"messages": partial_lc_messages},
                as_node=node_name,
            )
            print(
                f"[_persist_partial_messages] Persisted {len(partial_lc_messages)} partial messages to checkpoint for thread {config.get('configurable', {}).get('thread_id')}"
            )
            logger.info(
                "Persisted %d partial messages to checkpoint for thread %s",
                len(partial_lc_messages),
                config.get("configurable", {}).get("thread_id"),
            )
            print("[_persist_partial_messages] EXITING (success)")
            logger.debug("[_persist_partial_messages] EXITING (success)")
        else:
            print(
                "[_persist_partial_messages] Cannot persist: graph does not support aupdate_state"
            )
            logger.warning("Cannot persist partial messages: graph does not support aupdate_state")
    except Exception as exc:
        print(f"[_persist_partial_messages] Exception: {exc}")
        logger.exception("Failed to persist partial messages after cancel")
    print("[_persist_partial_messages] EXITING (end)")
    logger.debug("[_persist_partial_messages] EXITING (end)")


def _schedule_persist(
    agent: Any,
    config: dict,
    all_messages: list[dict],
    checkpointer: Any,
    thread_id: str,
    run_id: str,
) -> None:
    """Fire-and-forget: schedule ``_persist_partial_messages`` on the running
    event-loop.  This is safe to call from a generator ``finally`` block
    (where ``await`` is not possible) because we use ``asyncio.ensure_future``
    instead of awaiting directly."""

    async def _do_persist():
        print(
            f"[_schedule_persist/_do_persist] Persist task started for thread_id={thread_id}, run_id={run_id}, {len(all_messages)} messages"
        )
        logger.debug(
            f"[_schedule_persist/_do_persist] Persist task started for thread_id={thread_id}, run_id={run_id}, {len(all_messages)} messages"
        )
        try:
            await _persist_partial_messages(agent, config, all_messages, checkpointer)
            print(
                f"[_schedule_persist/_do_persist] Partial messages persisted successfully for thread_id={thread_id}, run_id={run_id}"
            )
            logger.debug(
                f"[_schedule_persist/_do_persist] Partial messages persisted successfully for thread_id={thread_id}, run_id={run_id}"
            )
        except Exception as exc:
            print(f"Scheduled persist failed for thread_id={thread_id}, run_id={run_id}: {exc}")
            logger.error(
                f"Scheduled persist failed for thread_id={thread_id}, run_id={run_id}: {exc}"
            )
        finally:
            unregister_run(thread_id, run_id)

    try:
        print(
            f"[_schedule_persist] Scheduling persist for thread_id={thread_id}, run_id={run_id}, {len(all_messages)} messages"
        )
        logger.debug(
            f"[_schedule_persist] Scheduling persist for thread_id={thread_id}, run_id={run_id}, {len(all_messages)} messages"
        )
        loop = asyncio.get_running_loop()
        loop.create_task(_do_persist())
    except RuntimeError:
        # No running event loop — should not happen in a server context,
        # but fall-back to cleanup only.
        print(
            f"No running event loop for scheduled persist (thread_id={thread_id}, run_id={run_id})"
        )
        logger.warning(
            f"No running event loop for scheduled persist (thread_id={thread_id}, run_id={run_id})"
        )
        unregister_run(thread_id, run_id)


def _schedule_delayed_cleanup(thread_id: str, run_id: str, delay_seconds: float = 5) -> None:
    """Schedule a delayed unregister_run so that the cancel endpoint
    (which arrives *after* abort kills the generator) still has access
    to the RunContext for persisting partial messages.

    If the cancel endpoint arrives and calls unregister_run itself,
    the delayed cleanup becomes a harmless no-op (pop on missing key)."""

    async def _delayed():
        await asyncio.sleep(delay_seconds)
        unregister_run(thread_id, run_id)
        logger.debug("Delayed cleanup for run %s on thread %s", run_id, thread_id)

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_delayed())
    except RuntimeError:
        unregister_run(thread_id, run_id)


def _message_to_dict(msg, uuid_module_ref=uuid_module) -> dict:
    """Convert a LangChain message to SDK-compatible dict format."""
    msg_class = type(msg).__name__
    type_map = {
        "HumanMessage": "human",
        "AIMessage": "ai",
        "AIMessageChunk": "ai",
        "SystemMessage": "system",
        "ToolMessage": "tool",
        "FunctionMessage": "function",
    }
    msg_type = type_map.get(
        msg_class, msg_class.lower().replace("message", "").replace("chunk", "")
    )

    msg_dict: dict[str, Any] = {
        "type": msg_type,
        "content": msg.content if hasattr(msg, "content") else str(msg),
        "id": getattr(msg, "id", None) or f"msg-{uuid_module_ref.uuid4()}",
    }

    if hasattr(msg, "name") and msg.name:
        msg_dict["name"] = msg.name
    if hasattr(msg, "tool_calls") and msg.tool_calls:
        msg_dict["tool_calls"] = msg.tool_calls
    if hasattr(msg, "tool_call_id") and msg.tool_call_id:
        msg_dict["tool_call_id"] = msg.tool_call_id
    if hasattr(msg, "additional_kwargs") and msg.additional_kwargs:
        msg_dict["additional_kwargs"] = msg.additional_kwargs
    if hasattr(msg, "response_metadata") and msg.response_metadata:
        msg_dict["response_metadata"] = msg.response_metadata

    return msg_dict


def _serialize_message_for_sdk(msg) -> Dict:
    """Convert a LangChain message to SDK-compatible format (used by thread history)."""
    if isinstance(msg, dict):
        result = dict(msg)
        if "type" not in result:
            result["type"] = "unknown"
        return result

    type_map = {
        "HumanMessage": "human",
        "AIMessage": "ai",
        "AIMessageChunk": "ai",
        "SystemMessage": "system",
        "ToolMessage": "tool",
        "FunctionMessage": "function",
    }

    msg_class = msg.__class__.__name__
    msg_type = type_map.get(msg_class, getattr(msg, "type", "unknown"))

    result: dict[str, Any] = {
        "type": msg_type,
        "content": getattr(msg, "content", ""),
        "id": getattr(msg, "id", None),
        "name": getattr(msg, "name", None),
    }

    if hasattr(msg, "additional_kwargs"):
        result["additional_kwargs"] = msg.additional_kwargs
    if hasattr(msg, "response_metadata"):
        result["response_metadata"] = msg.response_metadata
    if hasattr(msg, "tool_calls"):
        result["tool_calls"] = msg.tool_calls
    if hasattr(msg, "invalid_tool_calls"):
        result["invalid_tool_calls"] = msg.invalid_tool_calls
    if hasattr(msg, "usage_metadata"):
        result["usage_metadata"] = msg.usage_metadata
    if hasattr(msg, "tool_call_id"):
        result["tool_call_id"] = msg.tool_call_id
    if hasattr(msg, "artifact"):
        result["artifact"] = msg.artifact
    if hasattr(msg, "status"):
        result["status"] = msg.status

    return result


# =============================================================================
# POST /threads/{thread_id}/runs/stream
# =============================================================================


@router.post("/threads/{thread_id}/runs/stream")
async def stream_run(
    thread_id: str,
    request_obj: Request,
    request: RunCreate,
) -> StreamingResponse:
    """
    Stream a run.
    Compatible with @langchain/langgraph-sdk client.runs.stream()

    User ID is automatically extracted from x-api-key header if present.
    """
    from .store import get_assistant_from_store

    print(f"[DEBUG] stream_run called for thread_id: {thread_id}")
    print(f"[DEBUG] All headers: {dict(request_obj.headers)}")

    # Extract user_id from API key
    api_key = request_obj.headers.get("x-api-key")
    print(f"[DEBUG] api_key: {api_key[:50] if api_key else 'None'}...")

    user_id = extract_user_id_from_token(api_key) if api_key else None
    print(f"[DEBUG] extracted user_id: {user_id}")

    if user_id:
        logger.info(f"stream_run: Using user_id from API key: {user_id}")
    else:
        logger.info("stream_run: No API key found, user_id will not be set")

    # Resolve graph_id from assistant_id
    graph_id = request.assistant_id
    stored_config: dict = {}
    print(f"[DEBUG] stream_run: Looking up assistant_id: {request.assistant_id}")
    stored = await get_assistant_from_store(request.assistant_id)
    print(f"[DEBUG] stream_run: stored result: {stored is not None}")

    if stored:
        graph_id = stored.get("graph_id")
        raw_config = stored.get("config", {})
        stored_config = raw_config.get("configurable", {})
        print(
            f"[DEBUG] stream_run: graph_id={graph_id}, stored_config keys={list(stored_config.keys())}"
        )
        logger.info(
            f"stream_run: Loaded stored config for assistant {request.assistant_id}: "
            f"{list(stored_config.keys())}"
        )
    else:
        print("[DEBUG] stream_run: No stored assistant found, checking if it's a template")
        all_agents = get_all_agent_info()
        if not any(a.key == request.assistant_id for a in all_agents):
            raise HTTPException(
                status_code=404, detail=f"Assistant {request.assistant_id} not found"
            )

    print(f"[DEBUG] stream_run: Getting agent for graph_id: {graph_id}")
    try:
        agent = get_agent_or_lazy(graph_id)
        print(f"[DEBUG] stream_run: Got agent type: {type(agent).__name__}")
    except Exception as e:
        logger.error(f"Failed to get agent {graph_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to load agent {graph_id}")

    # Update / create thread metadata with assistant_id
    try:
        from .store import update_thread_in_store, get_thread_from_store, add_thread

        existing_thread = await get_thread_from_store(thread_id)
        if existing_thread:
            current_metadata = existing_thread.get("metadata", {})
            if current_metadata.get("assistant_id") != request.assistant_id:
                current_metadata["assistant_id"] = request.assistant_id
                await update_thread_in_store(thread_id, {"metadata": current_metadata})
                logger.info(
                    f"Updated thread {thread_id} metadata with assistant_id {request.assistant_id}"
                )
        else:
            now = datetime.now(timezone.utc).isoformat()
            new_thread = {
                "thread_id": thread_id,
                "created_at": now,
                "updated_at": now,
                "metadata": {"assistant_id": request.assistant_id},
                "status": "idle",
            }
            await add_thread(new_thread)
            logger.info(f"Created new thread {thread_id} with assistant_id {request.assistant_id}")
    except Exception as e:
        logger.warning(f"Failed to update/create thread metadata: {e}")

    # Prepare input
    run_input = request.input or {}
    if "messages" in run_input:
        run_input["messages"] = convert_input_messages(run_input["messages"])

    # Config
    config = request.config or {}
    config["configurable"] = config.get("configurable", {})
    config["configurable"]["thread_id"] = thread_id

    if stored_config:
        for key, value in stored_config.items():
            if key not in config["configurable"]:
                config["configurable"][key] = value
        logger.info(f"stream_run: Merged stored config: {list(stored_config.keys())}")
        logger.info(f"stream_run: Final configurable keys: {list(config['configurable'].keys())}")
    else:
        logger.info("stream_run: No stored_config to merge")

    if user_id:
        config["configurable"]["user_id"] = user_id
        logger.info(f"stream_run: Set user_id in configurable: {user_id}")

    # Handle checkpoint for edit/fork (SDK sends checkpoint when user edits a message)
    checkpoint_to_use = None
    if request.checkpoint:
        cp_id = request.checkpoint.get("checkpoint_id")
        cp_ns = request.checkpoint.get("checkpoint_ns", "")
        if cp_id:
            config["configurable"]["checkpoint_id"] = cp_id
            config["configurable"]["checkpoint_ns"] = cp_ns
            checkpoint_to_use = request.checkpoint
            logger.info(f"stream_run: Forking from checkpoint_id={cp_id}, ns={cp_ns}")
    elif request.checkpoint_id:
        config["configurable"]["checkpoint_id"] = request.checkpoint_id
        logger.info(f"stream_run: Forking from checkpoint_id={request.checkpoint_id}")

    checkpointer = get_checkpointer()
    print(
        f"[DEBUG] stream_run: Got checkpointer: "
        f"{type(checkpointer).__name__ if checkpointer else 'None'}"
    )

    # Generate run_id before the generator so we can set it as a response header.
    # The SDK reads Content-Location to extract the run_id and wire up cancel().
    run_id = str(uuid_module.uuid4())

    _STREAM_DONE = object()  # Sentinel for queue

    async def event_generator():  # noqa: C901  — complex but self-contained
        cancel_event = register_run(thread_id, run_id)
        # Populate the RunContext so the finally block can persist
        # partial messages even when the HTTP connection is aborted.
        run_ctx = get_run_context(thread_id, run_id)
        if run_ctx is not None:
            run_ctx.agent = agent
            run_ctx.config = config
            run_ctx.checkpointer = checkpointer

        # Queue-based approach: agent stream runs in a separate task that
        # puts events into a queue.  The generator reads from the queue.
        # On cancel/disconnect the task is cancelled, which interrupts
        # any in-flight LLM HTTP request.
        event_queue: asyncio.Queue = asyncio.Queue()
        _agent_task: asyncio.Task | None = None

        try:

            def default_serializer(obj: Any) -> Any:
                if hasattr(obj, "dict"):
                    return obj.dict()
                if hasattr(obj, "model_dump"):
                    return obj.model_dump()
                return str(obj)

            def _check_cancelled() -> bool:
                """Return True if this run has been cancelled."""
                return cancel_event.is_set()

            # First, send metadata event
            metadata_event = {"run_id": run_id, "thread_id": thread_id}
            yield f"event: metadata\ndata: {json.dumps(metadata_event)}\n\n"

            all_messages: list[dict] = []

            # Add input messages
            if run_input.get("messages"):
                for msg in run_input["messages"]:
                    all_messages.append(_message_to_dict(msg))

            # Share the all_messages list with RunContext so the finally
            # block can access accumulated messages even after abort.
            if run_ctx is not None:
                run_ctx.all_messages = all_messages

            print(f"[DEBUG] event_generator: Starting stream with run_id={run_id}")
            print(
                f"[DEBUG] event_generator: Using checkpointer: "
                f"{type(checkpointer).__name__ if checkpointer else 'None'}"
            )

            from agents.lazy_agent import LazyLoadingAgent

            def _is_handoff_tool(name: str) -> bool:
                """Check if a tool name is an internal LangGraph handoff/transfer tool."""
                return name.startswith("transfer_to_") or name.startswith("transfer_back_to_")

            use_astream_events = isinstance(agent, LazyLoadingAgent)
            print(f"[DEBUG] event_generator: Agent is LazyLoadingAgent: {use_astream_events}")

            # These must be defined before the if/else so the finally
            # block can always access them to flush partial AI content.
            current_message_id = None
            current_message_content = ""
            current_message_name = None
            last_chunk_dict = None  # used by the astream (non-lazy) path

            # --- Agent stream producer task ---
            # Runs the agent stream in a separate asyncio.Task so it can
            # be cancelled (.cancel()) which interrupts in-flight awaits
            # (LLM HTTP calls, tool executions, etc.).

            async def _stream_producer():
                """Iterate agent stream and put events into event_queue.

                On cancel we kill the TCP connection to Ollama by closing
                the httpx.AsyncClient on the cached ChatOllama singleton
                (obtained via ``get_model()``).  We then replace it with a
                fresh client so subsequent requests still work.

                ``get_model()`` returns a **cached singleton**, so every
                graph type (chatbot, supervisor, react, etc.) shares the
                same ``ChatOllama._async_client._client`` httpx instance.
                This means we don't need to walk the graph — we just grab
                the model directly.
                """
                _aiter = None

                try:
                    if use_astream_events:
                        stream_kwargs: dict[str, Any] = {"version": "v2"}
                        if hasattr(agent, "astream_events") and checkpointer:
                            sig = inspect.signature(agent.astream_events)
                            if "checkpointer" in sig.parameters:
                                stream_kwargs["checkpointer"] = checkpointer
                        _aiter = agent.astream_events(
                            run_input, config=config, **stream_kwargs
                        ).__aiter__()
                        async for event in _aiter:
                            await event_queue.put(("event", event))
                    else:
                        stream_kwargs_simple: dict[str, Any] = {"stream_mode": "messages"}
                        if hasattr(agent, "astream") and checkpointer:
                            astream_sig = inspect.signature(agent.astream)
                            if "checkpointer" in astream_sig.parameters:
                                stream_kwargs_simple["checkpointer"] = checkpointer
                        _aiter = agent.astream(
                            run_input, config=config, **stream_kwargs_simple
                        ).__aiter__()
                        async for chunk, metadata in _aiter:
                            await event_queue.put(("chunk", (chunk, metadata)))
                except Exception as exc:
                    await event_queue.put(("error", exc))
                finally:
                    # 1) Close the async iterator to try the clean path first
                    if _aiter is not None:
                        try:
                            await _aiter.aclose()
                        except Exception:
                            pass

                    # 2) NUCLEAR: If cancelled, kill the httpx TCP connection
                    #    directly on the cached ChatOllama singleton so Ollama
                    #    stops generating immediately.
                    is_cancelled = cancel_event.is_set()
                    if not is_cancelled:
                        try:
                            cur = asyncio.current_task()
                            is_cancelled = cur is not None and cur.cancelled()
                        except Exception:
                            pass

                    if is_cancelled:
                        try:
                            await _force_close_llm_connection(config)
                        except Exception as exc:
                            print(f"[stream_producer] _force_close_llm_connection error: {exc}")

                    # Signal the consumer that no more items are coming.
                    try:
                        event_queue.put_nowait(("done", None))
                    except Exception:
                        pass
                    print(f"[stream_producer] Exiting for run {run_id} (cancelled={is_cancelled})")

            _agent_task = asyncio.create_task(_stream_producer())
            # Store task in RunContext so cancel_run() can cancel it
            if run_ctx is not None:
                run_ctx.agent_task = _agent_task
            print(f"[event_generator] Started stream_producer task for run {run_id}")

            if use_astream_events:
                # Read events from the queue (produced by _stream_producer)
                while True:
                    try:
                        msg_type, msg_data = await asyncio.wait_for(event_queue.get(), timeout=0.5)
                    except asyncio.TimeoutError:
                        # Check for cancel/disconnect while waiting
                        if _check_cancelled() or await request_obj.is_disconnected():
                            if not cancel_event.is_set():
                                cancel_event.set()
                            print(f"[event_generator] Cancel/disconnect detected for run {run_id}")
                            if _agent_task and not _agent_task.done():
                                _agent_task.cancel()
                                print(f"[event_generator] Cancelled agent task for run {run_id}")
                            break
                        continue

                    if msg_type == "done":
                        break
                    if msg_type == "error":
                        raise msg_data

                    event = msg_data
                    event_type = event.get("event")
                    event_name = event.get("name", "")
                    event_metadata = event.get("metadata", {})
                    langgraph_node = event_metadata.get("langgraph_node", "unknown")

                    if event_type in (
                        "on_tool_start",
                        "on_tool_end",
                        "on_chain_start",
                        "on_chain_end",
                    ):
                        print(
                            f"[DEBUG] event_generator: event_type={event_type}, "
                            f"name={event_name}, node={langgraph_node}"
                        )

                    # --- chat model stream ---
                    if event_type == "on_chat_model_stream":
                        chunk = event.get("data", {}).get("chunk")
                        if chunk and hasattr(chunk, "content") and chunk.content:
                            msg_id = (
                                getattr(chunk, "id", None)
                                or current_message_id
                                or f"msg-{uuid_module.uuid4()}"
                            )
                            current_message_id = msg_id
                            current_message_content += chunk.content

                            if hasattr(chunk, "name") and chunk.name:
                                current_message_name = chunk.name

                            chunk_dict: dict[str, Any] = {
                                "type": "ai",
                                "content": chunk.content,
                                "id": msg_id,
                            }
                            if current_message_name:
                                chunk_dict["name"] = current_message_name

                            messages_data = [
                                chunk_dict,
                                {"langgraph_node": langgraph_node},
                            ]
                            yield (
                                f"event: messages\n"
                                f"data: {json.dumps(messages_data, default=default_serializer)}\n\n"
                            )

                        if chunk and hasattr(chunk, "tool_call_chunks") and chunk.tool_call_chunks:
                            for tc_chunk in chunk.tool_call_chunks:
                                tool_call_msg = {
                                    "type": "ai",
                                    "content": "",
                                    "id": current_message_id or f"msg-{uuid_module.uuid4()}",
                                    "tool_calls": [
                                        {
                                            "id": tc_chunk.get("id", ""),
                                            "name": tc_chunk.get("name", ""),
                                            "args": tc_chunk.get("args", ""),
                                            "type": "tool_call",
                                        }
                                    ],
                                }
                                messages_data = [
                                    tool_call_msg,
                                    {"langgraph_node": langgraph_node},
                                ]
                                yield (
                                    f"event: messages\n"
                                    f"data: {json.dumps(messages_data, default=default_serializer)}\n\n"
                                )

                    # --- tool start ---
                    elif event_type == "on_tool_start":
                        tool_name = event_name
                        tool_input = event.get("data", {}).get("input", {})
                        tool_run_id = event.get("run_id", "")
                        is_handoff = _is_handoff_tool(tool_name)

                        tool_call_id = (
                            f"call_{tool_run_id[:8]}"
                            if tool_run_id
                            else f"call_{uuid_module.uuid4().hex[:8]}"
                        )
                        ai_msg_with_tool = {
                            "type": "ai",
                            "content": "",
                            "id": (
                                f"ai-tool-{tool_run_id[:8]}"
                                if tool_run_id
                                else f"ai-tool-{uuid_module.uuid4().hex[:8]}"
                            ),
                            "tool_calls": [
                                {
                                    "id": tool_call_id,
                                    "name": tool_name,
                                    "args": (
                                        tool_input
                                        if isinstance(tool_input, dict)
                                        else {"input": str(tool_input)}
                                    ),
                                    "type": "tool_call",
                                }
                            ],
                        }
                        messages_data = [
                            ai_msg_with_tool,
                            {"langgraph_node": langgraph_node, "tool_start": True},
                        ]
                        yield (
                            f"event: messages\n"
                            f"data: {json.dumps(messages_data, default=default_serializer)}\n\n"
                        )
                        # Handoff tools are streamed in real-time but NOT added
                        # to all_messages so they don't appear twice in the
                        # final values event.
                        if not is_handoff:
                            all_messages.append(ai_msg_with_tool)

                    # --- tool end ---
                    elif event_type == "on_tool_end":
                        tool_name = event_name
                        tool_output = event.get("data", {}).get("output", "")
                        tool_run_id = event.get("run_id", "")
                        is_handoff = _is_handoff_tool(tool_name)

                        tool_call_id = (
                            f"call_{tool_run_id[:8]}"
                            if tool_run_id
                            else f"call_{uuid_module.uuid4().hex[:8]}"
                        )
                        tool_result_msg = {
                            "type": "tool",
                            "content": str(tool_output) if tool_output else "",
                            "id": (
                                f"tool-{tool_run_id[:8]}"
                                if tool_run_id
                                else f"tool-{uuid_module.uuid4().hex[:8]}"
                            ),
                            "name": tool_name,
                            "tool_call_id": tool_call_id,
                        }
                        messages_data = [
                            tool_result_msg,
                            {"langgraph_node": langgraph_node, "tool_end": True},
                        ]
                        yield (
                            f"event: messages\n"
                            f"data: {json.dumps(messages_data, default=default_serializer)}\n\n"
                        )
                        if not is_handoff:
                            all_messages.append(tool_result_msg)

                    # --- chat model end ---
                    elif event_type == "on_chat_model_end":
                        output = event.get("data", {}).get("output")
                        if output and hasattr(output, "content"):
                            msg_dict = _message_to_dict(output)
                            # Skip messages whose only purpose is a handoff
                            # tool_call (transfer_to_* / transfer_back_to_*).
                            # These are already streamed in real-time above.
                            tool_calls = msg_dict.get("tool_calls") or []
                            only_handoff = (
                                tool_calls
                                and all(_is_handoff_tool(tc.get("name", "")) for tc in tool_calls)
                                and not msg_dict.get("content")
                            )
                            if not only_handoff and not any(
                                m.get("id") == msg_dict.get("id") for m in all_messages
                            ):
                                all_messages.append(msg_dict)
                        current_message_id = None
                        current_message_content = ""
                        current_message_name = None

            else:
                # Read chunks from the queue (produced by _stream_producer)
                while True:
                    try:
                        msg_type, msg_data = await asyncio.wait_for(event_queue.get(), timeout=0.5)
                    except asyncio.TimeoutError:
                        if _check_cancelled() or await request_obj.is_disconnected():
                            if not cancel_event.is_set():
                                cancel_event.set()
                            print(
                                f"[event_generator] Cancel/disconnect detected for run {run_id} (astream)"
                            )
                            if _agent_task and not _agent_task.done():
                                _agent_task.cancel()
                                print(f"[event_generator] Cancelled agent task for run {run_id}")
                            break
                        continue

                    if msg_type == "done":
                        break
                    if msg_type == "error":
                        raise msg_data

                    chunk, metadata = msg_data

                    serialized_chunk = _message_to_dict(chunk)
                    last_chunk_dict = serialized_chunk
                    # print(
                    #     f"[DEBUG] event_generator: Sending message chunk: "
                    #     f"type={serialized_chunk.get('type')}, id={serialized_chunk.get('id')}"
                    # )

                    # Accumulate AI content across chunks (same id = same message)
                    chunk_id = serialized_chunk.get("id")
                    chunk_content = serialized_chunk.get("content", "")
                    chunk_type = serialized_chunk.get("type", "")
                    if chunk_type == "ai" and chunk_content:
                        if chunk_id and chunk_id == current_message_id:
                            current_message_content += chunk_content
                        else:
                            current_message_id = chunk_id
                            current_message_content = chunk_content
                        if hasattr(chunk, "name") and chunk.name:
                            current_message_name = chunk.name

                    messages_data = [serialized_chunk, metadata]
                    yield (
                        f"event: messages\n"
                        f"data: {json.dumps(messages_data, default=default_serializer)}\n\n"
                    )

                    if hasattr(chunk, "response_metadata") and chunk.response_metadata.get("done"):
                        all_messages.append(serialized_chunk)
                        # Reset accumulator since message is complete
                        current_message_id = None
                        current_message_content = ""
                        current_message_name = None

            # Final values event
            final_values = {"messages": all_messages}
            print(
                f"[DEBUG] event_generator: Sending values event with {len(all_messages)} messages"
            )
            for i, msg in enumerate(all_messages):
                print(f"[DEBUG]   message[{i}]: type={msg.get('type')}, id={msg.get('id')}")
            yield f"event: values\ndata: {json.dumps(final_values, default=default_serializer)}\n\n"

            yield "event: end\ndata: {}\n\n"
            print("[DEBUG] event_generator: Stream completed")

        except Exception as e:
            logger.error(f"Stream run error: {e}")
            traceback.print_exc()
            yield f"event: error\ndata: {json.dumps({'error': str(e), 'message': str(e)})}\n\n"
        finally:
            print(
                f"[event_generator finally] Entered for thread_id={thread_id}, run_id={run_id}, cancel_event={cancel_event.is_set()}, messages={len(all_messages)}"
            )
            logger.debug(
                f"[event_generator finally] Entered for thread_id={thread_id}, run_id={run_id}, cancel_event={cancel_event.is_set()}, messages={len(all_messages)}"
            )

            # Cancel the agent stream task to stop in-flight LLM calls.
            # asyncio.Task.cancel() sends CancelledError into the task's
            # current await point, which interrupts HTTP requests to the
            # model provider.
            if _agent_task and not _agent_task.done():
                _agent_task.cancel()
                try:
                    await _agent_task
                except (asyncio.CancelledError, Exception):
                    pass
                print(f"[event_generator finally] Agent task cancelled for run {run_id}")
            elif _agent_task:
                print(f"[event_generator finally] Agent task already done for run {run_id}")

            # Force-close the LLM TCP connection ONLY if cancelled/disconnected.
            # (Normal completion must not close the shared httpx client.)
            # The idempotency guard in _force_close_llm_connection ensures
            # that if cancel_run() already closed it, this is a harmless no-op.
            if cancel_event.is_set():
                try:
                    await _force_close_llm_connection(config)
                except Exception as exc:
                    print(f"[event_generator finally] _force_close_llm_connection error: {exc}")

            # Flush any partial AI message that was being streamed when
            # the connection was aborted.
            #
            # Both astream_events and astream paths accumulate AI text in
            # current_message_content.  This is only added to all_messages
            # when the message completes (on_chat_model_end / done flag)
            # or _check_cancelled() fires.  Neither happens when the HTTP
            # connection is killed by abort(), so we flush here.
            if current_message_id and current_message_content:
                partial_msg: dict[str, Any] = {
                    "type": "ai",
                    "content": current_message_content,
                    "id": current_message_id,
                }
                if current_message_name:
                    partial_msg["name"] = current_message_name
                if not any(m.get("id") == current_message_id for m in all_messages):
                    all_messages.append(partial_msg)
                    print(
                        f"[event_generator finally] Flushed partial AI message id={current_message_id}, len={len(current_message_content)}"
                    )

            print(
                f"[event_generator finally] all_messages types after flush: {[m.get('type') for m in all_messages]}"
            )

            # The SDK calls abort() first (kills the HTTP connection, which
            # triggers this finally block) and THEN sends the cancel API
            # request.  So at this point cancel_event is NOT yet set.
            #
            # We delay cleanup so the cancel endpoint (which arrives a few
            # hundred ms later) still finds the RunContext and can persist
            # partial messages.
            _schedule_delayed_cleanup(thread_id, run_id, delay_seconds=5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Content-Location": f"/threads/{thread_id}/runs/{run_id}",
        },
    )


# =============================================================================
# POST /threads/{thread_id}/runs/{run_id}/cancel
# =============================================================================


@router.post("/threads/{thread_id}/runs/{run_id}/cancel")
async def cancel_run_endpoint(
    thread_id: str,
    run_id: str,
    request: RunCancel = RunCancel(),
) -> dict:
    """
    Cancel a running agent run.

    Compatible with ``@langchain/langgraph-sdk`` ``client.runs.cancel()``.
    The *action* parameter is accepted for compatibility but currently only
    ``interrupt`` behaviour is implemented (stop the stream as soon as possible).

    Because the SDK calls ``abort()`` (kills the HTTP connection) **before**
    sending this cancel request, the streaming generator has already exited
    by the time we get here.  We use the ``RunContext`` (which is kept alive
    for a few seconds after the generator exits) to persist the partial
    messages that were accumulated during the stream.
    """
    print(f"[cancel_run_endpoint] Called for thread_id={thread_id}, run_id={run_id}")
    logger.debug(f"[cancel_run_endpoint] Called for thread_id={thread_id}, run_id={run_id}")
    found = cancel_run(thread_id, run_id)
    if not found:
        logger.debug(f"Cancel requested for run {run_id} on thread {thread_id} but run not active")
    else:
        logger.info(f"Cancel accepted for run {run_id} on thread {thread_id}")

    # Persist partial messages from the RunContext.
    ctx = get_run_context(thread_id, run_id)
    print(
        f"[cancel_run_endpoint] RunContext: ctx is not None: {ctx is not None}, messages: {len(ctx.all_messages) if ctx else 'n/a'}, checkpointer: {ctx.checkpointer is not None if ctx else 'n/a'}"
    )
    if ctx and ctx.all_messages:
        print(
            f"[cancel_run_endpoint] ctx.all_messages types: {[m.get('type') for m in ctx.all_messages]}"
        )
    logger.debug(
        f"[cancel_run_endpoint] RunContext: ctx is not None: {ctx is not None}, messages: {len(ctx.all_messages) if ctx else 'n/a'}, checkpointer: {ctx.checkpointer is not None if ctx else 'n/a'}"
    )

    try:
        if ctx and ctx.all_messages and ctx.checkpointer:
            ai_messages = [m for m in ctx.all_messages if m.get("type") in ("ai", "tool")]
            if ai_messages:
                print(
                    f"Cancel endpoint: persisting {len(ai_messages)} partial messages for run {run_id}"
                )
                logger.info(
                    f"Cancel endpoint: persisting {len(ai_messages)} partial messages for run {run_id}"
                )
                print(
                    f"Cancel endpoint: message types: {[m.get('type') for m in ctx.all_messages]}"
                )
                try:
                    print("Cancel endpoint: calling _persist_partial_messages...")
                    logger.info("Cancel endpoint: calling _persist_partial_messages...")
                    await _persist_partial_messages(
                        ctx.agent, ctx.config, ctx.all_messages, ctx.checkpointer
                    )
                    print("Cancel endpoint: partial messages persisted successfully")
                    logger.info("Cancel endpoint: partial messages persisted successfully")
                except Exception as exc:
                    print(f"Cancel endpoint: persist failed: {exc}")
                    logger.error(f"Cancel endpoint: persist failed: {exc}")
                print("Cancel endpoint: after _persist_partial_messages call")
                logger.info("Cancel endpoint: after _persist_partial_messages call")
        else:
            print(
                f"Cancel endpoint: no partial messages to persist (ctx={ctx is not None}, msgs={len(ctx.all_messages) if ctx else 0}, cp={ctx.checkpointer is not None if ctx else False})"
            )
            logger.debug(
                f"Cancel endpoint: no partial messages to persist (ctx={ctx is not None}, msgs={len(ctx.all_messages) if ctx else 0}, cp={ctx.checkpointer is not None if ctx else False})"
            )
    except Exception as exc:
        print(f"Cancel endpoint: unexpected error during persist: {exc}")
        logger.error(f"Cancel endpoint: unexpected error during persist: {exc}")

    # Clean up now that we've persisted
    unregister_run(thread_id, run_id)
    return {"status": "accepted"}


# =============================================================================
# POST /threads/{thread_id}/history
# =============================================================================


@router.post("/threads/{thread_id}/history")
async def get_thread_history(
    thread_id: str,
    request: ThreadHistoryRequest,
) -> List[ThreadState]:
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
                    "checkpoint_id": (
                        checkpoint.checkpoint["id"] if checkpoint.checkpoint else None
                    ),
                },
                metadata=checkpoint.metadata,
                created_at=(checkpoint.metadata.get("created_at") if checkpoint.metadata else None),
                parent_config=checkpoint.parent_config,
                parent_checkpoint=parent_checkpoint,
            )
            history.append(state)

        return history
    except Exception as e:
        logger.error(f"Error fetching history for thread {thread_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
