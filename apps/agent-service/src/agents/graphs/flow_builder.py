"""FlowGraphBuilder — compiles a validated FlowSpec into a LangGraph graph.

Assumes the caller (FlowService, P1 Task 6) has already validated the spec.
This module does not re-validate; a pre-validated spec is its precondition.

See .tmp/flow-canvas-design.md sections 4.3 and 4.5.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Annotated, Any, TypedDict
from uuid import UUID

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AnyMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import interrupt

from agents.graphs.schemas import GraphSchemaType
from client.rag_http import rag_auth_headers, rag_timeout_seconds, rag_url
from core.exceptions import FlowBuildError, NotAResourceNodeError, UnknownComponentError
from core.logger import get_logger
from domain.flows.comparison import evaluate_comparison
from domain.flows.guardrails import (
    DEFAULT_HEURISTIC_THRESHOLD,
    HEURISTIC_CHECKS,
    build_check_prompt,
    checks_to_run,
    heuristic_jailbreak_score,
    justification_for,
    parse_guardrail_decision,
    sanitize_input,
)
from domain.flows.migrations import migrate_spec
from domain.flows.registry import ComponentRegistry, get_registry
from models.flows import ComponentKind, ComponentTemplate, FlowEdge, FlowNode, FlowSpec

logger = get_logger(__name__)

_MODEL_RESOURCE_TYPES = frozenset({"LLMModel", "OllamaModel"})
_TOOL_RESOURCE_TYPES = frozenset(
    {
        "CalculatorTools",
        "CodeTools",
        "CommandTools",
        "DockerTools",
        "FileTools",
        "GitTools",
        "JavaTools",
        "JsonTools",
        "PdfTools",
        "ServiceTools",
        "TextTools",
        "TimeTools",
        "UtilityTools",
        "WebTools",
        "MailTools",
        "ExternalMCPServer",
    }
)


def _merge_scratch(current: dict[str, Any], update: dict[str, Any]) -> dict[str, Any]:
    """Shallow-merge scratch updates. Same key: last write wins — deliberate,
    since a node re-run (e.g. inside a Loop) should overwrite its own prior
    output, not accumulate it."""
    return {**current, **update}


def _merge_arrivals(
    current: list[tuple[str, Any]], update: list[tuple[str, Any]] | None
) -> list[tuple[str, Any]]:
    """Append arrivals, except that ``None`` clears the channel.

    ``arrivals`` is checkpointed, so a plain accumulating reducer would carry
    a thread's turn-one arrivals into turn two and a "first" Merge would keep
    answering with the earlier turn's branch forever. A write cannot express
    "empty" against an accumulator, so ``None`` is the reset signal — the same
    role ChatInput's zeroed counters play for While / If-Else / foreach.
    """
    if update is None:
        return []
    return [*current, *update]


class FlowState(TypedDict):
    """Shared state every compiled flow uses.

    ``messages`` reuses LangGraph's own accumulation reducer — no custom
    message-merging logic. ``scratch`` carries node-to-node non-message data
    (e.g. a TextInput's configured value, a PromptTemplate's rendered text).
    ``arrivals`` records ``(merge_id, message)`` pairs in super-step order so
    a first/last Merge can tell which branch reached it first — the flat
    ``messages`` list cannot answer that.
    """

    messages: Annotated[list[AnyMessage], add_messages]
    scratch: Annotated[dict[str, Any], _merge_scratch]
    arrivals: Annotated[list[tuple[str, Any]], _merge_arrivals]


def is_tool_mode(node: FlowNode, template: ComponentTemplate) -> bool:
    """Whether this node is configured as an agent tool rather than a step.

    The capability is declared by the template (``tool_mode_field``); a value
    on a component that never declared it is ignored, not honoured.
    """
    field = template.tool_mode_field
    return bool(field) and bool(node.values.get(field, False))


def partition_nodes(
    nodes: list[FlowNode], registry: ComponentRegistry
) -> tuple[list[FlowNode], list[FlowNode]]:
    """Split nodes into (resources, executions), preserving original order.

    Resources are build-time injected into whichever execution node they
    feed; only executions become StateGraph nodes. See design spec 4.3.

    Raises UnknownComponentError for a node type the registry doesn't know —
    by this point (post-validation) that is a programming error, not a
    user-facing validation result.
    """
    resources: list[FlowNode] = []
    executions: list[FlowNode] = []
    for node in nodes:
        if node.type in ("note", "noteNode"):
            continue
        template = registry.get(node.type)  # raises UnknownComponentError
        # A tool-mode node is a resource for this run: the agent calls it, the
        # flow does not run it. That is a per-node mode, so `kind` alone is
        # not enough to decide.
        if template.kind is ComponentKind.RESOURCE or is_tool_mode(node, template):
            resources.append(node)
        else:
            executions.append(node)
    return resources, executions


@dataclass(frozen=True)
class ResolvedResources:
    """What execution nodes consume, keyed by the resource node's own id."""

    models: dict[str, BaseChatModel] = field(default_factory=dict)
    tool_names: dict[str, list[str]] = field(default_factory=dict)
    mail_config_ids: dict[str, str] = field(default_factory=dict)
    datasource_ids: dict[str, str] = field(default_factory=dict)


def _resolve_model(node: FlowNode) -> BaseChatModel:
    """Resolve a Model resource to a real BaseChatModel."""
    from core import get_model, settings

    model_name = node.values.get("model") or settings.DEFAULT_MODEL
    return get_model(model_name)


def resolve_resources(
    resource_nodes: list[FlowNode], tool_mode_ids: set[str] | None = None
) -> ResolvedResources:
    """Resolve every resource node to the object its consumers actually need.

    Raises NotAResourceNodeError for an execution-kind node — partition_nodes
    should already have kept those out; reaching this is a contract violation
    upstream, not a recoverable condition.

    ``tool_mode_ids`` names the nodes that are resources only because they are
    in tool mode. They are execution components by kind, so they have nothing
    to resolve here — ``make_component_tool`` builds their tool instead.
    """
    skip = tool_mode_ids or set()
    models: dict[str, BaseChatModel] = {}
    tool_names: dict[str, list[str]] = {}
    mail_config_ids: dict[str, str] = {}
    datasource_ids: dict[str, str] = {}
    for node in resource_nodes:
        if node.id in skip:
            continue
        if node.type in _MODEL_RESOURCE_TYPES:
            models[node.id] = _resolve_model(node)
        elif node.type in _TOOL_RESOURCE_TYPES:
            tools = node.values.get("tools") or []
            if isinstance(tools, list):
                tool_names[node.id] = [str(t) for t in tools]
            elif isinstance(tools, str):
                tool_names[node.id] = [tools]
            else:
                tool_names[node.id] = []
        elif node.type == "MailConfig":
            mail_config_ids[node.id] = str(node.values.get("config_id") or "")
        elif node.type == "AirbyteDatasource":
            datasource_ids[node.id] = str(node.values.get("datasource_id") or "")
        elif node.type in {"LongTermMemory", "ThreadCheckpointer"}:
            pass
        else:
            raise NotAResourceNodeError(node.id, node.type)
    return ResolvedResources(
        models=models,
        tool_names=tool_names,
        mail_config_ids=mail_config_ids,
        datasource_ids=datasource_ids,
    )


# ---------------------------------------------------------------------------
# Execution node runnables (Core)
# ---------------------------------------------------------------------------

_AGENT_SCHEMA_BY_TYPE = {
    "Chatbot": GraphSchemaType.ZERO_SHOT,
    "ZeroShotAgent": GraphSchemaType.ZERO_SHOT,
    "ReActAgent": GraphSchemaType.REACT,
    "PlanExecuteAgent": GraphSchemaType.PLAN_EXECUTE,
    "SelfReflectAgent": GraphSchemaType.SELF_REFLECT,
    "PipelineStage": GraphSchemaType.REACT,
}


async def _noop_node(state: FlowState, config: RunnableConfig) -> dict[str, Any]:
    """ChatInput/ChatOutput: addressable no-ops. Edges need somewhere to
    originate/terminate; no state transformation happens here."""
    return {}


def _make_chat_input_node(
    while_ids: Sequence[str],
    condrouter_ids: Sequence[str],
    foreach_ids: Sequence[str] = (),
) -> Any:
    """ChatInput resets every per-turn iteration state, making each bound per
    *turn*.

    ``scratch`` is checkpointed, so without this a thread's second turn would
    start at the previous turn's count (While / If-Else) or think a Loop is
    mid-iteration, and the loop would misbehave. The ordered ``arrivals``
    channel is checkpointed too and is cleared here for the same reason: a
    "first" Merge must name this turn's earliest branch, not turn one's.

    ChatInput is the right place for it: it declares no input handle, so no
    edge can route back into it, and ``START -> ChatInput`` therefore runs
    exactly once per turn — before any router reads its state. An interrupt
    resume deliberately does *not* re-run it, because the same turn must keep
    counting.
    """
    reset: dict[str, Any] = {}
    for i in while_ids:
        reset[_loop_counter_key(i)] = 0
    for i in condrouter_ids:
        reset[_condrouter_counter_key(i)] = 0
    for i in foreach_ids:
        reset[_foreach_items_key(i)] = None
        reset[_foreach_idx_key(i)] = 0
        reset[_foreach_agg_key(i)] = []

    async def _run(state: FlowState, config: RunnableConfig) -> dict[str, Any]:
        return {"scratch": dict(reset), "arrivals": None}

    return _run


def _make_text_input_node(node: FlowNode) -> Any:
    """Langflow's Text Input emits a ``Message``. It also keeps its
    ``scratch[node.id]`` slot so a downstream Prompt Template can still read it
    as ``{node-id}``; the message is what lets it feed an agent or Chat Output.
    """
    text = node.values.get("text", "")

    async def _run(state: FlowState, config: RunnableConfig) -> dict[str, Any]:
        return {"scratch": {node.id: text}, "messages": [HumanMessage(content=str(text))]}

    return _run


def _make_file_input_node(node: FlowNode) -> Any:
    file_meta = node.values.get("file")

    async def _run(state: FlowState, config: RunnableConfig) -> dict[str, Any]:
        return {"scratch": {node.id: file_meta}}

    return _run


def _make_prompt_template_node(node: FlowNode) -> Any:
    """Substitutes `{node_id}` / `{variable}` placeholders from `scratch`.

    Placeholders are the *source node id* of an incoming edge, or a Set
    Variable name (Phase 0). Like Langflow's Prompt Template this emits the
    rendered text as a ``Message`` so it can feed an agent or Chat Output;
    it also keeps writing ``scratch[node.id]`` so a chained Prompt Template
    can still interpolate ``{node-id}``.
    """
    template = node.values.get("template", "")

    async def _run(state: FlowState, config: RunnableConfig) -> dict[str, Any]:
        try:
            rendered = template.format(**state.get("scratch", {}))
        except KeyError as exc:
            raise KeyError(
                f"PromptTemplate '{node.id}' references {exc}, which is not "
                "present in scratch — check the incoming edge is wired"
            ) from exc
        return {
            "scratch": {node.id: rendered},
            "messages": [HumanMessage(content=rendered)],
        }

    return _run


def _select_model(resources: ResolvedResources, model_node_id: str | None) -> BaseChatModel | None:
    """Pick the model for one agent node.

    An explicit `model_node_id` (the resource actually wired to this node via
    a Model-typed edge — Task 10 supplies it) always wins. Without one, a
    single-model flow falls back to its only resource; with zero or multiple
    unresolved candidates there is no safe guess, so this returns None and
    GraphBuilder falls back to settings.DEFAULT_MODEL, matching a classic
    agent with no LLM override.
    """
    if model_node_id is not None:
        return resources.models.get(model_node_id)
    if len(resources.models) == 1:
        return next(iter(resources.models.values()))
    return None


async def _make_agent_node(
    node: FlowNode,
    resources: ResolvedResources,
    *,
    user_id: str | None = None,
    mcp_tools_map: dict[str, Any] | None = None,
    model_node_id: str | None = None,
    mcp_tools: list[str] | None = None,
    mcp_tool_configs: dict[str, Any] | None = None,
    memory_enabled: bool = False,
) -> CompiledStateGraph:
    """Reuses agents/graphs/builder.py's existing per-schema logic directly —
    the returned compiled graph *is* GraphBuilder's own output, embedded as a
    subgraph. There is no separate agent-behavior code path to diverge from
    the classic builder; Task 0's spike proved this embedding pattern is safe.
    """
    from agents.graphs.builder import GraphBuilder

    schema_type = _AGENT_SCHEMA_BY_TYPE[node.type]
    model = _select_model(resources, model_node_id)

    builder = GraphBuilder(
        model=model,
        mcp_tools_map=mcp_tools_map or {},
        checkpointer=None,  # the parent flow's checkpointer owns persistence
        memory_enabled=memory_enabled,
    )
    config: dict[str, Any] = {
        "system_prompt": node.values.get("system_prompt", ""),
        "user_id": user_id,
    }
    if schema_type != GraphSchemaType.ZERO_SHOT:
        if mcp_tools:
            config["mcp_tools"] = mcp_tools
        if mcp_tool_configs:
            config["mcp_tool_configs"] = mcp_tool_configs

    if node.type == "SelfReflectAgent":
        config["reflection_prompt"] = node.values.get("reflection_prompt", "")
        config["max_iterations"] = node.values.get("max_iterations", 3)
    # The per-schema strategies are async (they may load referenced sub-agents
    # from the database), so the embedded subgraph is built through
    # ``build_async`` — the sync ``build`` would hand LangGraph a coroutine.
    return await builder.build_async(schema_type, config)


def _handle_source_id(node_id: str, handle: str, edges: list[FlowEdge]) -> str | None:
    """The id of the node wired into ``node_id``'s ``handle`` input port.

    Langflow passes a value into a component along an edge; we carry the same
    idea by naming the *producer* and reading its scratch slot at runtime
    (``_resolve_port_value``). Returns ``None`` when nothing is wired, which is
    what lets a caller fall back to the handle's declared ``fallback_field``.
    """
    return next(
        (e.source for e in edges if e.target == node_id and e.target_handle == handle),
        None,
    )


def _resolve_port_value(state: FlowState, source_id: str | None) -> Any | None:
    """The value a wired input port carries.

    The producer's ``scratch`` slot when it wrote one, else the latest message
    text — an agent-terminated branch publishes no scratch value, but what it
    just said is the value it produced.

    ``None`` means *nothing is wired*, deliberately distinct from an edge
    carrying an empty value: only the former may fall back to a field.
    """
    if source_id is None:
        return None
    scratch = state.get("scratch", {})
    if source_id in scratch:
        return scratch[source_id]
    return _extract_last_message_text(state)


def _make_arrival_stamp(merge_id: str, source_id: str) -> Any:
    """Sits on one edge into a first/last Merge and records that branch's
    value on the ordered ``arrivals`` channel, then passes through.

    It runs in the super-step after its upstream node, so a shorter branch
    stamps before a longer one — that ordering is what first/last read. The
    branch value is ``scratch[source_id]`` when the upstream node produced one
    (TextInput, PromptTemplate, Set Variable), else the latest message text
    (best effort for an agent-terminated branch)."""

    async def _run(state: FlowState, config: RunnableConfig) -> dict[str, Any]:
        return {"arrivals": [(merge_id, str(_resolve_port_value(state, source_id)))]}

    return _run


def _make_merge_node(node: FlowNode) -> Any:
    """ "concat" is a pure passthrough — `add_messages` already accumulated
    every branch's contribution before this node runs.

    "first"/"last" read the ``arrivals`` channel (populated by the compiler's
    arrival-stamp nodes on each incoming edge) and emit the earliest / latest
    branch's value as a fresh message, so it becomes ``messages[-1]``. The
    other branches' messages stay in history — `add_messages` cannot retract
    them — but the merge result is unambiguous.
    """
    strategy = node.values.get("strategy", "concat")
    if strategy == "concat":
        return _noop_node
    if strategy not in ("first", "last"):
        raise NotImplementedError(
            f"Merge strategy {strategy!r} is not implemented — use 'concat', 'first' or 'last'"
        )

    async def _run(state: FlowState, config: RunnableConfig) -> dict[str, Any]:
        values = [value for (merge_id, value) in state.get("arrivals", []) if merge_id == node.id]
        if not values:
            return {}
        chosen = values[0] if strategy == "first" else values[-1]
        return {"messages": [HumanMessage(content=chosen)]}

    return _run


# ---------------------------------------------------------------------------
# Vector RAG execution runnables
# ---------------------------------------------------------------------------


async def _execute_document_search(
    collection_id: str,
    query: str,
    *,
    top_k: int = 4,
    threshold: float | None = None,
    access_token: str | None = None,
) -> list[dict[str, Any]]:
    import httpx

    url = rag_url(f"/collections/{collection_id}/documents/search")
    headers = rag_auth_headers(access_token)

    if not query or not collection_id:
        return []

    try:
        payload: dict[str, Any] = {"query": query, "limit": top_k}
        async with httpx.AsyncClient(timeout=rag_timeout_seconds()) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            results = resp.json()
            if threshold is not None and isinstance(results, list):
                results = [r for r in results if r.get("score", 1.0) >= threshold]
            return results
    except Exception as exc:
        logger.info("RAG search endpoint failed (%s), attempting local vector search fallback", exc)
        try:
            from agents.tools import get_collection_name_from_uuid, load_vector_store

            table_id = get_collection_name_from_uuid(collection_id)
            vs = load_vector_store(table_id)
            docs = vs.similarity_search_with_score(query, k=top_k)
            formatted = []
            for doc, score in docs:
                if threshold is not None and score < threshold:
                    continue
                formatted.append(
                    {
                        "content": doc.page_content,
                        "metadata": doc.metadata,
                        "score": float(score),
                    }
                )
            return formatted
        except Exception as local_exc:
            logger.warning("Local vector search fallback failed: %s", local_exc)
            return []


def _extract_query(state: FlowState) -> str:
    """Extract query from messages or scratch."""
    messages = state.get("messages", [])
    if messages:
        last = messages[-1]
        if hasattr(last, "content"):
            return str(last.content)
        if isinstance(last, dict):
            return str(last.get("content", ""))
    scratch = state.get("scratch", {})
    for val in scratch.values():
        if isinstance(val, str) and val.strip():
            return val
    return ""


def _make_document_search_node(node: FlowNode) -> Any:
    collection_id = str(node.values.get("collection") or "")
    static_query = str(node.values.get("query") or "")
    top_k = int(node.values.get("top_k", 4))
    threshold = (
        float(node.values.get("threshold", 0.7))
        if node.values.get("threshold") is not None
        else None
    )

    async def _run(state: FlowState, config: RunnableConfig) -> dict[str, Any]:
        query = static_query or _extract_query(state)
        token = config.get("configurable", {}).get("access_token") if config else None
        results = await _execute_document_search(
            collection_id, query, top_k=top_k, threshold=threshold, access_token=token
        )
        context_parts = []
        if isinstance(results, list):
            for d in results:
                if isinstance(d, dict):
                    content = d.get("content") or d.get("text") or ""
                    if content:
                        context_parts.append(content)
        context_str = "\n\n".join(context_parts)
        return {
            "scratch": {
                node.id: results,
                f"{node.id}_context": context_str,
            }
        }

    return _run


def _make_document_context_node(node: FlowNode) -> Any:
    template = str(node.values.get("template") or "Context:\n{context}\n\nQuery: {query}")

    async def _run(state: FlowState, config: RunnableConfig) -> dict[str, Any]:
        scratch = state.get("scratch", {})
        query = _extract_query(state)

        docs_list: list[Any] = []
        for v in scratch.values():
            if (
                isinstance(v, list)
                and v
                and isinstance(v[0], dict)
                and ("content" in v[0] or "text" in v[0])
            ):
                docs_list.extend(v)

        formatted_chunks = []
        for d in docs_list:
            content = d.get("content") or d.get("text") or ""
            source = (
                d.get("metadata", {}).get("source") if isinstance(d.get("metadata"), dict) else None
            )
            if source:
                formatted_chunks.append(f"[{source}]: {content}")
            else:
                formatted_chunks.append(content)

        context_str = "\n\n".join(formatted_chunks) if formatted_chunks else ""
        rendered = template.replace("{context}", context_str).replace("{query}", query)
        return {"scratch": {node.id: rendered}}

    return _run


# ---------------------------------------------------------------------------
# Graph RAG execution runnables
# ---------------------------------------------------------------------------


async def _execute_graph_search(
    collection_id: str,
    query: str,
    *,
    limit: int = 10,
    access_token: str | None = None,
) -> list[dict[str, Any]]:
    import httpx

    url = rag_url("/graph/search")
    headers = rag_auth_headers(access_token)

    payload = {"query": query, "collection_ids": [collection_id], "limit": limit}
    async with httpx.AsyncClient(timeout=rag_timeout_seconds()) as client:
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        return resp.json()


async def _execute_graph_entity_search(
    collection_id: str,
    query: str,
    *,
    entity_type: str | None = None,
    limit: int = 10,
    access_token: str | None = None,
) -> list[dict[str, Any]]:
    import httpx

    url = rag_url(f"/graph/collections/{collection_id}/search/entities")
    headers = rag_auth_headers(access_token)

    params = {"q": query, "limit": limit}
    async with httpx.AsyncClient(timeout=rag_timeout_seconds()) as client:
        resp = await client.get(url, params=params, headers=headers)
        resp.raise_for_status()
        return resp.json()


async def _execute_graph_neighborhood(
    collection_id: str,
    entity_id: str,
    *,
    depth: int = 1,
    limit: int = 20,
    access_token: str | None = None,
) -> dict[str, Any]:
    import httpx

    url = rag_url(f"/graph/collections/{collection_id}/neighborhood")
    headers = rag_auth_headers(access_token)

    params = {"node_id": entity_id, "depth": depth, "limit": limit}
    async with httpx.AsyncClient(timeout=rag_timeout_seconds()) as client:
        resp = await client.get(url, params=params, headers=headers)
        resp.raise_for_status()
        return resp.json()


async def _execute_graph_stats(
    collection_id: str,
    *,
    access_token: str | None = None,
) -> dict[str, Any]:
    import httpx

    url = rag_url(f"/graph/collections/{collection_id}/stats")
    headers = rag_auth_headers(access_token)

    async with httpx.AsyncClient(timeout=rag_timeout_seconds()) as client:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        return resp.json()


def _make_graph_search_node(node: FlowNode) -> Any:
    collection_id = str(node.values.get("collection") or "")
    limit = int(node.values.get("limit", 10))

    async def _run(state: FlowState, config: RunnableConfig) -> dict[str, Any]:
        query = _extract_query(state)
        token = config.get("configurable", {}).get("access_token") if config else None
        results = await _execute_graph_search(collection_id, query, limit=limit, access_token=token)
        return {"scratch": {node.id: results}}

    return _run


def _make_graph_entity_search_node(node: FlowNode) -> Any:
    collection_id = str(node.values.get("collection") or "")
    entity_type = node.values.get("entity_type")
    limit = int(node.values.get("limit", 10))

    async def _run(state: FlowState, config: RunnableConfig) -> dict[str, Any]:
        query = _extract_query(state)
        token = config.get("configurable", {}).get("access_token") if config else None
        results = await _execute_graph_entity_search(
            collection_id, query, entity_type=entity_type, limit=limit, access_token=token
        )
        return {"scratch": {node.id: results}}

    return _run


def _make_graph_neighborhood_node(node: FlowNode) -> Any:
    collection_id = str(node.values.get("collection") or "")
    depth = int(node.values.get("depth", 1))
    limit = int(node.values.get("limit", 20))

    async def _run(state: FlowState, config: RunnableConfig) -> dict[str, Any]:
        entity_id = _extract_query(state)
        token = config.get("configurable", {}).get("access_token") if config else None
        results = await _execute_graph_neighborhood(
            collection_id, entity_id, depth=depth, limit=limit, access_token=token
        )
        return {"scratch": {node.id: results}}

    return _run


def _make_graph_stats_node(node: FlowNode) -> Any:
    collection_id = str(node.values.get("collection") or "")

    async def _run(state: FlowState, config: RunnableConfig) -> dict[str, Any]:
        token = config.get("configurable", {}).get("access_token") if config else None
        results = await _execute_graph_stats(collection_id, access_token=token)
        return {"scratch": {node.id: results}}

    return _run


# ---------------------------------------------------------------------------
# Web search and crawling execution runnables (P8 Task 46)
# ---------------------------------------------------------------------------


def _make_web_search_node(
    node: FlowNode,
    resources: ResolvedResources,
    mcp_tools_map: dict[str, Any] | None = None,
) -> Any:
    static_query = str(node.values.get("query") or "")
    max_results = int(node.values.get("max_results", 5))

    async def _run(state: FlowState, config: RunnableConfig) -> dict[str, Any]:
        scratch = state.get("scratch", {})
        query = static_query
        for v in scratch.values():
            if isinstance(v, str) and v.strip():
                query = v

        if not query:
            msgs = state.get("messages") or []
            if msgs:
                last_msg = msgs[-1]
                if hasattr(last_msg, "content"):
                    query = str(last_msg.content)
                elif isinstance(last_msg, dict) and "content" in last_msg:
                    query = str(last_msg["content"])
                elif isinstance(last_msg, str):
                    query = last_msg

        if not query:
            return {"scratch": {node.id: []}}

        tools = mcp_tools_map or {}
        tool = tools.get("web_search") or tools.get("web")
        results: list[dict[str, Any]] = []

        if tool:
            try:
                if hasattr(tool, "ainvoke"):
                    raw = await tool.ainvoke({"query": query, "max_results": max_results})
                elif hasattr(tool, "invoke"):
                    raw = tool.invoke({"query": query, "max_results": max_results})
                elif callable(tool):
                    raw = (
                        await tool(query=query, max_results=max_results)
                        if asyncio.iscoroutinefunction(tool)
                        else tool(query=query, max_results=max_results)
                    )
                else:
                    raw = ""

                if isinstance(raw, list):
                    results = raw
                elif isinstance(raw, str):
                    results = [{"content": raw, "query": query}]
                elif isinstance(raw, dict):
                    results = [raw]
            except Exception as exc:
                logger.warning("WebSearch execution failed for node %s: %s", node.id, exc)
                results = []
        else:
            logger.info("WebSearch: no web_search tool in mcp_tools_map; returning empty results")
            results = []

        return {"scratch": {node.id: results}}

    return _run


def _make_fetch_webpage_node(
    node: FlowNode,
    resources: ResolvedResources,
) -> Any:
    static_url = str(node.values.get("url") or "")

    async def _run(state: FlowState, config: RunnableConfig) -> dict[str, Any]:
        from controller.web_search_controller import get_web_search_controller

        scratch = state.get("scratch", {})
        url = static_url
        for v in scratch.values():
            if isinstance(v, str) and (v.startswith("http://") or v.startswith("https://")):
                url = v

        if not url:
            return {"scratch": {node.id: ""}}

        ctrl = get_web_search_controller()
        try:
            res = ctrl.crawl_url(url)
            content = res.get("content") or ""
            return {"scratch": {node.id: content}}
        except Exception as exc:
            logger.warning("FetchWebpage execution failed for node %s: %s", node.id, exc)
            return {"scratch": {node.id: f"Error: {exc}"}}

    return _run


def _make_content_crawl_node(
    node: FlowNode,
    resources: ResolvedResources,
) -> Any:
    static_urls_str = str(node.values.get("urls") or "")

    async def _run(state: FlowState, config: RunnableConfig) -> dict[str, Any]:
        from controller.web_search_controller import get_web_search_controller

        scratch = state.get("scratch", {})
        urls_str = static_urls_str
        for v in scratch.values():
            if isinstance(v, str) and ("http://" in v or "https://" in v):
                urls_str = v

        urls = [u.strip() for u in urls_str.splitlines() if u.strip()]
        if not urls:
            return {"scratch": {node.id: []}}

        ctrl = get_web_search_controller()
        try:
            crawled = ctrl.crawl_urls(urls)
            docs = [
                {
                    "content": item.get("content", ""),
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "scrape_successful": item.get("scrape_successful", True),
                    "failure_reason": item.get("failure_reason"),
                }
                for item in crawled
            ]
            return {"scratch": {node.id: docs}}
        except Exception as exc:
            logger.warning("ContentCrawl execution failed for node %s: %s", node.id, exc)
            return {"scratch": {node.id: []}}

    return _run


def _make_sync_trigger_node(node: FlowNode) -> Any:
    datasource_id = str(node.values.get("datasource_id") or "")

    async def _run(state: FlowState, config: RunnableConfig) -> dict[str, Any]:
        from controller import get_data_controller

        ctrl = get_data_controller()
        try:
            res = await ctrl.trigger_sync(datasource_id, triggered_by="flow")
            return {"scratch": {node.id: res}}
        except Exception as exc:
            logger.warning(
                "SyncTrigger execution failed for node %s (datasource %s): %s",
                node.id,
                datasource_id,
                exc,
            )
            return {"scratch": {node.id: {"status": "error", "error": str(exc)}}}

    return _run


async def make_node(
    node: FlowNode,
    resources: ResolvedResources,
    *,
    user_id: str | None = None,
    mcp_tools_map: dict[str, Any] | None = None,
    model_node_id: str | None = None,
    mcp_tools: list[str] | None = None,
    mcp_tool_configs: dict[str, Any] | None = None,
    memory_enabled: bool = False,
    port_sources: dict[str, str] | None = None,
    body_end_id: str | None = None,
    extra_frame_sources: Sequence[str] | None = None,
) -> Any:
    """Return the LangGraph-node-compatible value for one execution node.

    For agent types this is a compiled subgraph (GraphBuilder's own output);
    for everything else it's a plain async callable of (FlowState, config).
    `model_node_id` names the resource actually wired to this node's
    Model handle (Task 10 supplies it from the flow's edges); omit it for a
    single-model flow. Raises UnknownComponentError for a type this factory
    doesn't know.

    `port_sources` maps this node's input handle names to the id of the node
    wired to each; `build()` supplies it from the flow's edges. Empty when a
    node is built standalone, which is exactly the "nothing wired" case, so
    every port falls back to its declared field.

    `body_end_id` is the Loop-only companion: the node that closes the foreach
    body (whatever wires back into the Loop's `input` handle), whose value is
    what each pass aggregates. `extra_frame_sources` is the Data Operations
    companion: every table wired into `df` beyond the first, which only
    Concatenate reads.
    """
    if node.type == "ChatInput":
        # The flow's per-turn reset point. ``build()`` calls this same factory
        # with the flow's While / If-Else / foreach ids to zero; standalone
        # there are none, but the arrivals channel is cleared either way.
        return _make_chat_input_node((), (), ())
    if node.type in _NOOP_NODE_TYPES:
        return _noop_node
    # Table defined below, after the factories it names.
    simple_factory = _SIMPLE_NODE_FACTORIES.get(node.type)
    if simple_factory is not None:
        return simple_factory(node)

    # What remains needs more than the node: a model resolved from the flow's
    # edges, the MCP tool map, or the whole resource set.
    if node.type == "ConditionalRouter":
        return _make_condrouter_node(node, port_sources)
    if node.type == "Loop":
        return _make_foreach_node(node, port_sources, body_end_id)
    if node.type == "SmartRouter":
        return _make_smart_router_node(node, _select_model(resources, model_node_id), port_sources)
    if node.type == "Guardrails":
        return _make_guardrails_node(node, _select_model(resources, model_node_id), port_sources)
    if node.type == "Operations":
        return _make_operations_node(node, port_sources, extra_frame_sources)
    if node.type == "SplitText":
        return _make_split_text_node(node, port_sources)
    if node.type == "TypeConverter":
        return _make_type_converter_node(node, port_sources)
    if node.type == "Parser":
        return _make_parser_node(node, port_sources)
    if node.type == "BatchRun":
        return _make_batch_run_node(node, _select_model(resources, model_node_id), port_sources)
    if node.type == "StructuredOutput":
        return _make_structured_output_node(
            node, _select_model(resources, model_node_id), port_sources
        )
    if node.type == "WebSearch":
        return _make_web_search_node(node, resources, mcp_tools_map=mcp_tools_map)
    if node.type == "FetchWebpage":
        return _make_fetch_webpage_node(node, resources)
    if node.type == "ContentCrawl":
        return _make_content_crawl_node(node, resources)
    if node.type in _AGENT_SCHEMA_BY_TYPE:
        return await _make_agent_node(
            node,
            resources,
            user_id=user_id,
            mcp_tools_map=mcp_tools_map,
            model_node_id=model_node_id,
            mcp_tools=mcp_tools,
            mcp_tool_configs=mcp_tool_configs,
            memory_enabled=memory_enabled,
        )
    raise UnknownComponentError(node.type)


# ---------------------------------------------------------------------------
# Condition evaluation — shared by Router (here) and Loop (Task 11)
# ---------------------------------------------------------------------------


def evaluate_condition(condition: str, state: dict[str, Any]) -> bool:
    """Safely evaluate a Router/Loop condition.

    A condition is a `scratch` key name; the route is taken when that key's
    value is truthy. Deliberately **not** `eval()` — a condition string that
    looks like code is treated as a literal (almost certainly nonexistent)
    key name and is never executed. Matches tools-service's own
    `calculate` tool precedent of rejecting arbitrary expression evaluation
    rather than sandboxing one.
    """
    return bool(state.get("scratch", {}).get(condition))


# ---------------------------------------------------------------------------
# Loop node — the concrete implementation of risk R2
# ---------------------------------------------------------------------------


def _loop_counter_key(loop_id: str) -> str:
    return f"_loop_iterations_{loop_id}"


def _make_loop_node(node: FlowNode) -> Any:
    """The Loop's own node: increments its private iteration counter in
    scratch. The bound check happens separately, in the conditional-edge
    routing function below, which reads this counter *after* it updates."""
    counter_key = _loop_counter_key(node.id)

    async def _run(state: FlowState, config: RunnableConfig) -> dict[str, Any]:
        current = state.get("scratch", {}).get(counter_key, 0)
        return {"scratch": {counter_key: current + 1}}

    return _run


def _make_loop_route_fn(loop_node: FlowNode, edges: list[FlowEdge]):
    """continue while the condition holds AND the bound hasn't been hit;
    exit unconditionally once the bound is reached — the R2 guarantee."""
    condition = loop_node.values.get("condition", "")
    max_iterations = loop_node.values.get("max_iterations")
    counter_key = _loop_counter_key(loop_node.id)

    continue_target = next(
        (e.target for e in edges if e.source == loop_node.id and e.source_handle == "continue"),
        None,
    )
    exit_target = next(
        (e.target for e in edges if e.source == loop_node.id and e.source_handle == "exit"),
        None,
    )

    def _route(state: FlowState) -> str:
        iterations = state.get("scratch", {}).get(counter_key, 0)
        # An empty condition means "no early-out test" — a plain bounded loop
        # that runs until max_iterations. A populated condition keeps the
        # original scratch-key-truthiness semantics.
        condition_holds = evaluate_condition(condition, state) if condition else True
        if iterations < max_iterations and condition_holds:
            if continue_target is None:
                raise FlowBuildError(f"While '{loop_node.id}' has no 'continue' edge")
            return continue_target
        if exit_target is None:
            raise FlowBuildError(f"While '{loop_node.id}' has no 'exit' edge")
        return exit_target

    return _route


# ---------------------------------------------------------------------------
# Loop node — a foreach over a collection (Langflow's LoopComponent).
# Sequential: the graph re-enters the node once per item. ``item`` carries the
# current element, ``done`` the collected results once the list is exhausted.
# ---------------------------------------------------------------------------


def _foreach_items_key(node_id: str) -> str:
    return f"_foreach_items_{node_id}"


def _foreach_idx_key(node_id: str) -> str:
    return f"_foreach_idx_{node_id}"


def _foreach_agg_key(node_id: str) -> str:
    return f"_foreach_agg_{node_id}"


def _is_dataframe(value: Any) -> bool:
    """True for a pandas DataFrame, without importing pandas at module load."""
    return type(value).__name__ == "DataFrame" and hasattr(value, "to_dict")


def _resolve_loop_items(
    items_source: str, state: FlowState, port_source: str | None = None
) -> list[Any]:
    """The collection a Loop iterates.

    Precedence is the compiler's one rule: a wired Items port wins, then the
    named Set Variable, then the non-blank lines of the latest message.

    A list is passed through element-wise, so dict rows — a document search
    result, say — reach the body with their structure intact. This is what
    Langflow's ``HandleInput`` accepting DataFrame / Table / Data / Message
    buys, expressed in the types we actually carry.

    A named source (field or port) that holds nothing iterates nothing: it
    must *not* fall back to the message, which would run the body over the
    wrong data and look like it worked.
    """
    raw: Any = None
    named = bool(items_source) or port_source is not None
    if port_source is not None:
        raw = _resolve_port_value(state, port_source)
    # A DataFrame has no truth value, so it must be recognised before any
    # `raw in (None, "")` test rather than after one.
    if not _is_dataframe(raw) and raw in (None, "") and items_source:
        raw = state.get("scratch", {}).get(items_source)
    if _is_dataframe(raw):
        # Langflow expands a DataFrame to its rows; without this the whole
        # table would be a single item. Split Text produces exactly this shape.
        return raw.to_dict(orient="records")
    if isinstance(raw, (list, tuple)):
        return list(raw)
    if isinstance(raw, str) and raw:
        return [line for line in raw.splitlines() if line.strip()]
    if raw not in (None, ""):
        return [raw]
    if named:
        return []
    return [line for line in _extract_last_message_text(state).splitlines() if line.strip()]


def _make_foreach_node(
    node: FlowNode,
    port_sources: dict[str, str] | None = None,
    body_end_id: str | None = None,
) -> Any:
    """First entry resolves the collection; every later entry (from the body
    via the back-edge) collects the body's latest output and advances. Each
    pass places the current item as the message the body consumes; when the
    list is exhausted it emits the joined results and stores the list under
    the node id for ``{node-id}`` interpolation."""
    items_source = str(node.values.get("items_source", "") or "")
    items_port = (port_sources or {}).get("items")
    items_key = _foreach_items_key(node.id)
    idx_key = _foreach_idx_key(node.id)
    agg_key = _foreach_agg_key(node.id)

    async def _run(state: FlowState, config: RunnableConfig) -> dict[str, Any]:
        scratch = state.get("scratch", {})
        if scratch.get(items_key) is None:
            items = _resolve_loop_items(items_source, state, items_port)
            idx = 0
            agg: list[Any] = []
        else:
            items = list(scratch.get(items_key) or [])
            # Langflow aggregates the body end-vertex's output. Reading that
            # node's scratch slot keeps whatever structure it produced;
            # _resolve_port_value falls back to the message for a body that
            # ends in an agent and publishes no slot.
            produced = (
                _resolve_port_value(state, body_end_id)
                if body_end_id
                else _extract_last_message_text(state)
            )
            agg = [*scratch.get(agg_key, []), produced]
            idx = scratch.get(idx_key, 0) + 1

        update: dict[str, Any] = {"scratch": {items_key: items, idx_key: idx, agg_key: agg}}
        if idx < len(items):
            # One slot, two meanings that are never live at once: while the
            # `item` branch runs this is the current element; once the list is
            # exhausted the `done` branch replaces it with the aggregate. The
            # old `_foreach_item_<id>` key was unreadable by any consumer (a
            # leading underscore and a dash make it an invalid placeholder),
            # so the item's structure never left the node.
            update["scratch"][node.id] = items[idx]
            update["messages"] = [HumanMessage(content=str(items[idx]))]
        else:
            update["scratch"][node.id] = agg
            update["messages"] = [HumanMessage(content="\n".join(str(x) for x in agg))]
        return update

    return _run


def _make_foreach_route_fn(node: FlowNode, edges: list[FlowEdge]):
    """Pure read: more items -> ``item`` branch, else -> ``done`` branch."""
    idx_key = _foreach_idx_key(node.id)
    items_key = _foreach_items_key(node.id)
    item_target = next(
        (e.target for e in edges if e.source == node.id and e.source_handle == "item"), None
    )
    done_target = next(
        (e.target for e in edges if e.source == node.id and e.source_handle == "done"), None
    )

    def _route(state: FlowState) -> str:
        scratch = state.get("scratch", {})
        idx = scratch.get(idx_key, 0)
        items = scratch.get(items_key) or []
        if idx < len(items):
            if item_target is None:
                raise FlowBuildError(f"Loop '{node.id}' has no 'item' edge")
            return item_target
        if done_target is None:
            raise FlowBuildError(f"Loop '{node.id}' has no 'done' edge")
        return done_target

    return _route


# ---------------------------------------------------------------------------
# ConditionalRouter ("If-Else") node — a content-driven branch that may own a
# cycle. A faithful port of Langflow's ConditionalRouterComponent, adapted to
# LangGraph's conditional-edge model (mirrors Router/Loop above).
# ---------------------------------------------------------------------------

_CONDROUTER_BRANCHES = ("true_result", "false_result")


def _condrouter_counter_key(node_id: str) -> str:
    return f"_condrouter_iterations_{node_id}"


def _condrouter_result_key(node_id: str) -> str:
    return f"_condrouter_matched_{node_id}"


def _extract_last_message_text(state: FlowState) -> str:
    """The text of the most recent message, or ``""`` if there is none.

    Deliberately narrower than ``_extract_query``: a ConditionalRouter tests
    what the flow just produced, never a stale scratch value."""
    messages = state.get("messages", [])
    if not messages:
        return ""
    last = messages[-1]
    content = getattr(last, "content", None)
    if content is None and isinstance(last, dict):
        content = last.get("content", "")
    return str(content) if content is not None else ""


def _strip_marker(text: str, marker: str, *, case_sensitive: bool) -> str:
    """Remove every occurrence of ``marker`` from ``text`` and tidy the
    trailing whitespace it leaves behind. A no-op if the marker is absent
    (e.g. numeric / regex / negative operators leave nothing to strip)."""
    if not marker:
        return text
    if case_sensitive:
        if marker not in text:
            return text
        cleaned = text.replace(marker, "")
    else:
        if marker.lower() not in text.lower():
            return text
        cleaned = re.sub(re.escape(marker), "", text, flags=re.IGNORECASE)
    return cleaned.rstrip()


def _make_condrouter_node(node: FlowNode, port_sources: dict[str, str] | None = None) -> Any:
    """The router's own node. Does everything that needs the running state,
    so the conditional edge below is a pure scratch read (mirrors Loop):

    - increments the per-turn iteration counter;
    - evaluates ``operator``/``match_text`` against the latest message and
      stores the boolean under ``_condrouter_matched_<id>``;
    - when ``strip_match`` is on, removes ``match_text`` from that message
      (same id → ``add_messages`` replaces it) so a completion marker never
      reaches the user or the next loop pass;
    - when the taken branch has a case message configured, replaces that
      message's text with it (Langflow's ``true_case_message`` /
      ``false_case_message``); a blank one forwards the input unchanged.

    The branch is chosen from ``matched``; on the turn the ``max_iterations``
    bound forces ``default_route`` the case message still follows ``matched``,
    which is a corner acceptable for an exit turn.
    """
    counter_key = _condrouter_counter_key(node.id)
    result_key = _condrouter_result_key(node.id)
    operator = str(node.values.get("operator") or "contains")
    match_text = str(node.values.get("match_text", "") or "")
    case_sensitive = bool(node.values.get("case_sensitive", True))
    strip_match = bool(node.values.get("strip_match", False))
    # Langflow's ``input_text`` port: a Set Variable name whose value is
    # compared instead of the latest message. Blank keeps the original
    # "test what the flow just produced" behaviour, so this is additive.
    input_source = str(node.values.get("input_source", "") or "")
    true_case_message = str(node.values.get("true_case_message", "") or "")
    false_case_message = str(node.values.get("false_case_message", "") or "")
    input_src = (port_sources or {}).get("input_text")
    true_src = (port_sources or {}).get("true_case_message")
    false_src = (port_sources or {}).get("false_case_message")

    async def _run(state: FlowState, config: RunnableConfig) -> dict[str, Any]:
        current = state.get("scratch", {}).get(counter_key, 0)
        # Wired port > input_source field > the latest message. Langflow's
        # port is required, so its "no input" case cannot arise; ours can, and
        # testing what the flow just produced beats failing.
        wired_input = _resolve_port_value(state, input_src)
        if wired_input is not None:
            compared = str(wired_input)
        elif input_source:
            compared = str(state.get("scratch", {}).get(input_source, ""))
        else:
            compared = _extract_last_message_text(state)
        matched = evaluate_comparison(operator, compared, match_text, case_sensitive=case_sensitive)
        update: dict[str, Any] = {"scratch": {counter_key: current + 1, result_key: matched}}

        messages = state.get("messages", [])
        last = messages[-1] if messages else None
        content = getattr(last, "content", None)
        if isinstance(content, str) and hasattr(last, "model_copy"):
            wired_case = _resolve_port_value(state, true_src if matched else false_src)
            override = (
                str(wired_case)
                if wired_case not in (None, "")
                else (true_case_message if matched else false_case_message)
            )
            if override:
                update["messages"] = [last.model_copy(update={"content": override})]
            elif strip_match and match_text:
                cleaned = _strip_marker(content, match_text, case_sensitive=case_sensitive)
                if cleaned != content:
                    update["messages"] = [last.model_copy(update={"content": cleaned})]

        return update

    return _run


def _make_set_variable_node(node: FlowNode) -> Any:
    """Stores a value in ``scratch`` under a user-chosen name.

    Node ids also live in ``scratch``, but they contain a dash, and internal
    counters start with an underscore; the validator's name rule keeps the
    three families from ever colliding. A blank name stores nothing rather
    than writing under "" — the validator rejects it, but an unvalidated spec
    must not corrupt scratch.
    """
    name = str(node.values.get("name", "") or "")
    configured = node.values.get("value")
    append = bool(node.values.get("append", False))

    async def _run(state: FlowState, config: RunnableConfig) -> dict[str, Any]:
        if not name:
            return {}
        value: Any = (
            configured if configured not in (None, "") else _extract_last_message_text(state)
        )
        if append:
            current = state.get("scratch", {}).get(name)
            if current is None:
                value = [value]
            elif isinstance(current, list):
                value = [*current, value]
            else:
                value = [current, value]
        return {"scratch": {name: value}}

    return _run


def _make_condrouter_route_fn(node: FlowNode, edges: list[FlowEdge]):
    """Pure state read: route on the boolean the node stored, unless the
    per-turn iteration count reached ``max_iterations`` — then the
    ``default_route`` branch is taken unconditionally (the R2
    no-infinite-loop guarantee, identical to Loop's bound)."""
    max_iterations = node.values.get("max_iterations")
    default_route = str(node.values.get("default_route") or "false_result")
    counter_key = _condrouter_counter_key(node.id)
    result_key = _condrouter_result_key(node.id)

    branch_target = {
        handle: next(
            (e.target for e in edges if e.source == node.id and e.source_handle == handle),
            None,
        )
        for handle in _CONDROUTER_BRANCHES
    }

    def _target(handle: str) -> str:
        target = branch_target.get(handle)
        if target is None:
            raise FlowBuildError(f"ConditionalRouter '{node.id}' has no '{handle}' edge")
        return target

    def _route(state: FlowState) -> str:
        scratch = state.get("scratch", {})
        iterations = scratch.get(counter_key, 0)
        if max_iterations is not None and iterations >= max_iterations:
            return _target(default_route)
        return _target("true_result" if scratch.get(result_key) else "false_result")

    return _route


_SMART_ROUTER_ELSE = "__else__"


def _smart_router_result_key(node_id: str) -> str:
    return f"_smart_router_choice_{node_id}"


def _make_smart_router_node(
    node: FlowNode,
    model: BaseChatModel | None,
    port_sources: dict[str, str] | None = None,
) -> Any:
    """Categorises the latest message with a single LLM call and records the
    chosen category in ``scratch``; the conditional edge below is a pure read
    (mirrors ConditionalRouter). A faithful port of Langflow's Smart Router.

    No wired Model resource falls back to the default model, exactly like a
    classic agent with no LLM override.
    """
    if model is None:
        from core import get_model, settings

        model = get_model(settings.DEFAULT_MODEL)

    rows = [r for r in node.values.get("routes", []) if isinstance(r, dict)]
    categories = [str(r.get("route_category", "")).strip() for r in rows]
    categories = [c for c in categories if c]
    enable_else = bool(node.values.get("enable_else_output", False))
    custom_prompt = str(node.values.get("custom_prompt", "") or "")
    override_field = str(node.values.get("message", "") or "")
    override_src = (port_sources or {}).get("message")
    result_key = _smart_router_result_key(node.id)
    value_by_category = {
        str(r.get("route_category", "")).strip(): r.get("output_value")
        for r in rows
        if str(r.get("route_category", "")).strip()
    }

    def _pick(reply_text: str) -> str | None:
        low = reply_text.strip().lower()
        for category in categories:
            if category.lower() == low:
                return category
        for category in categories:  # the LLM added surrounding words
            if category.lower() in low:
                return category
        return None

    async def _run(state: FlowState, config: RunnableConfig) -> dict[str, Any]:
        if not categories:
            return {"scratch": {result_key: _SMART_ROUTER_ELSE}}

        message = _extract_last_message_text(state)
        listing = "\n".join(
            f"- {r.get('route_category', '')}: {r.get('route_description', '')}" for r in rows
        )
        base = (
            f"Categories:\n{listing}\n\nMessage: {message}\n\n"
            "Reply with exactly one category name from the list and nothing else."
        )
        if custom_prompt:
            # Langflow calls this "Additional Instructions" and *appends* it.
            # Replacing the base prompt would delete the one instruction that
            # makes the reply a bare category name, which the router then has
            # to guess at.
            simple_routes = ", ".join(f'"{c}"' for c in categories)
            extra = custom_prompt.replace("{input_text}", message).replace(
                "{routes}", simple_routes
            )
            human = f"{base}\n\nAdditional Instructions:\n{extra}"
        else:
            human = base

        # `skip_stream`: this is an internal classification call, not part of
        # the answer. Without the tag its category reply ("yeterli", "iptal",
        # …) streams to the client as visible assistant text, landing as a
        # stray bubble next to the branch it was only meant to choose.
        reply = await model.ainvoke(
            [
                SystemMessage(content="You are a precise text classifier."),
                HumanMessage(content=human),
            ],
            config={"tags": ["skip_stream"]},
        )
        chosen = _pick(str(getattr(reply, "content", "")))

        if chosen is None:
            if not enable_else:
                raise FlowBuildError(
                    f"SmartRouter '{node.id}' matched no category and 'Enable Else output' is off"
                )
            return {"scratch": {result_key: _SMART_ROUTER_ELSE}}

        out: dict[str, Any] = {result_key: chosen}
        # Override Output beats everything, for every route (Langflow's rule).
        wired = _resolve_port_value(state, override_src)
        override = str(wired) if wired not in (None, "") else override_field
        if override.strip():
            out[node.id] = override
            return {"scratch": out, "messages": [HumanMessage(content=override)]}
        # Langflow sends the row's value *down the branch* as the message; a
        # blank one (or the literal "none") passes the input through instead.
        configured = value_by_category.get(chosen)
        if (
            configured is not None
            and str(configured).strip()
            and str(configured).strip().lower() != "none"
        ):
            text = str(configured)
            out[node.id] = text
            return {"scratch": out, "messages": [HumanMessage(content=text)]}
        return {"scratch": out}

    return _run


def _make_smart_router_route_fn(node: FlowNode, edges: list[FlowEdge]):
    """Pure state read: route on the category the node stored."""
    result_key = _smart_router_result_key(node.id)
    label_to_target = {e.source_handle: e.target for e in edges if e.source == node.id}

    def _route(state: FlowState) -> str:
        choice = state.get("scratch", {}).get(result_key)
        handle = "else" if choice == _SMART_ROUTER_ELSE else choice
        target = label_to_target.get(handle) or label_to_target.get("else")
        if target is None:
            raise FlowBuildError(f"SmartRouter '{node.id}' has no edge for category {choice!r}")
        return target

    return _route


def _guardrails_result_key(node_id: str) -> str:
    return f"_guardrails_passed_{node_id}"


def _make_guardrails_node(
    node: FlowNode,
    model: BaseChatModel | None,
    port_sources: dict[str, str] | None = None,
) -> Any:
    """A faithful port of Langflow's Guardrails: validate a piece of text
    against a set of LLM-backed checks and record the verdict in ``scratch``;
    the conditional edge below is a pure read (mirrors SmartRouter).

    Checks run in the order they were enabled and stop at the first failure —
    Langflow's fail-fast, which is observable, because a blocked input costs
    one model call rather than all of them. Jailbreak and Prompt Injection are
    screened by a regex score first and may be blocked without any call at all.

    ``scratch[node.id]`` holds Langflow's *Result Data* payload (the text, the
    verdict, and the justification on a failure) rather than the branch text,
    because that is the value the third output publishes and the richer of the
    two; the branch text travels as a message, which is how ``pass_result`` and
    ``fail_result`` reach whatever they are wired to.

    No wired Model resource falls back to the default model, exactly like
    SmartRouter and a classic agent with no LLM override.
    """
    if model is None:
        from core import get_model, settings

        model = get_model(settings.DEFAULT_MODEL)

    enabled = [str(v) for v in (node.values.get("enabled_guardrails") or []) if v]
    custom = (
        str(node.values.get("custom_guardrail_explanation", "") or "")
        if node.values.get("enable_custom_guardrail", False)
        else ""
    )
    checks = checks_to_run(enabled, custom)
    threshold = float(node.values.get("heuristic_threshold") or DEFAULT_HEURISTIC_THRESHOLD)
    # Langflow's ``input_text`` port; blank falls back to the latest message,
    # the same precedence ConditionalRouter uses.
    input_source = str(node.values.get("input_source", "") or "")
    input_src = (port_sources or {}).get("input_text")
    result_key = _guardrails_result_key(node.id)

    async def _check(name: str, description: str, text: str) -> bool:
        if name in HEURISTIC_CHECKS:
            score = heuristic_jailbreak_score(text)
            if score is not None and score >= threshold:
                return False
        prompt = build_check_prompt(name, description, sanitize_input(text))
        # `skip_stream`: an internal verdict call, never answer text — see the
        # same tag on SmartRouter's classifier for why it matters.
        reply = await model.ainvoke(prompt, config={"tags": ["skip_stream"]})
        try:
            return parse_guardrail_decision(str(getattr(reply, "content", reply)), check_type=name)
        except RuntimeError as exc:
            # An empty or error-shaped reply is not a verdict. Langflow raises
            # here too; naming the node turns it into something the flow author
            # can act on rather than a bare provider error.
            raise FlowBuildError(f"Guardrails '{node.id}': {exc}") from exc

    async def _run(state: FlowState, config: RunnableConfig) -> dict[str, Any]:
        if not checks:
            raise FlowBuildError(
                f"Guardrails '{node.id}' has no guardrail enabled; select at least one"
            )

        latest = _extract_last_message_text(state)
        wired = _resolve_port_value(state, input_src)
        if wired is not None:
            text = str(wired)
        elif input_source:
            text = str(state.get("scratch", {}).get(input_source, ""))
        else:
            text = latest
        if not text.strip():
            raise FlowBuildError(f"Guardrails '{node.id}' received empty text to validate")

        failed: list[str] = []
        for name, description in checks:
            if not await _check(name, description, text):
                # Langflow reports its own fixed sentence, never the model's
                # explanation — so a blocked input is not echoed back through
                # the justification the user reads.
                failed.append(f"{name}: {justification_for(name)}")
                break  # fail fast

        passed = not failed
        payload: dict[str, Any] = {"text": text, "result": "pass" if passed else "fail"}
        if not passed:
            payload["justification"] = "\n".join(failed)

        update: dict[str, Any] = {"scratch": {result_key: passed, node.id: payload}}
        if not passed:
            update["messages"] = [HumanMessage(content=payload["justification"])]
        elif text != latest:
            # Langflow's pass output is the validated text itself, which only
            # differs from the conversation when the text came from the port
            # or the named variable.
            update["messages"] = [HumanMessage(content=text)]
        return update

    return _run


_GUARDRAILS_BRANCHES = ("pass_result", "fail_result")


def _make_guardrails_route_fn(node: FlowNode, edges: list[FlowEdge]):
    """Pure state read: the verdict picks one branch, and ``data_result`` — if
    wired — runs alongside it.

    Langflow stops whichever of Pass/Fail did not fire but never stops Result
    Data, so an audit or logging path sees every verdict. Returning a list is
    how LangGraph expresses that same fan-out.
    """
    result_key = _guardrails_result_key(node.id)
    target_by_handle = {e.source_handle: e.target for e in edges if e.source == node.id}

    def _route(state: FlowState) -> list[str]:
        passed = bool(state.get("scratch", {}).get(result_key))
        handle = "pass_result" if passed else "fail_result"
        target = target_by_handle.get(handle)
        if target is None:
            raise FlowBuildError(f"Guardrails '{node.id}' has no '{handle}' edge")
        data_target = target_by_handle.get("data_result")
        return [target, data_target] if data_target else [target]

    return _route


_DEFAULT_FORMAT_INSTRUCTIONS = (
    "You are an AI that extracts structured JSON objects from unstructured text. "
    "Use a predefined schema with expected types (str, int, float, bool, dict). "
    "Extract ALL relevant instances that match the schema - if multiple patterns "
    "exist, capture them all. Fill missing or ambiguous values with defaults: "
    "null for missing values. Remove exact duplicates but keep variations that "
    "have different field values. Always return valid JSON in the expected "
    "format, never throw errors. If multiple objects can be extracted, return "
    "them all in the structured format."
)


def _make_structured_output_node(
    node: FlowNode,
    model: BaseChatModel | None,
    port_sources: dict[str, str] | None = None,
) -> Any:
    """Force an LLM to answer in a declared schema (Langflow's Structured Output).

    The schema table becomes a Pydantic model, wrapped in ``objects:
    list[Model]`` exactly as Langflow does — its own format instructions say
    "Extract ALL relevant instances", so the result is always a list even when
    the text yields one object. A caller can rely on that shape.

    The extracted objects land in ``scratch[node.id]``; the same value also
    leaves as JSON text, which is what lets the result reach an agent or Chat
    Output (we have no DataFrame port type, so one output carries both).
    """
    from pydantic import Field as _PydanticField
    from pydantic import create_model as _create_model

    from domain.flows.output_schema import build_output_model

    rows = node.values.get("output_schema")
    schema_name = str(node.values.get("schema_name", "") or "OutputModel").strip()
    try:
        item_model = build_output_model(schema_name, rows)
    except ValueError as exc:
        raise FlowBuildError(
            f"StructuredOutput '{node.id}' has an unusable output schema: {exc}"
        ) from exc

    wrapper = _create_model(
        f"{schema_name}List",
        objects=(
            list[item_model],  # type: ignore[valid-type]
            _PydanticField(description=f"Every {schema_name} found in the text."),
        ),
    )

    instructions = str(node.values.get("system_prompt", "") or _DEFAULT_FORMAT_INSTRUCTIONS)
    input_source = str(node.values.get("input_source", "") or "")
    input_src = (port_sources or {}).get("input_text")

    if model is None:
        from core import get_model, settings

        model = get_model(settings.DEFAULT_MODEL)

    async def _run(state: FlowState, config: RunnableConfig) -> dict[str, Any]:
        if not hasattr(model, "with_structured_output"):
            raise FlowBuildError(
                f"StructuredOutput '{node.id}' is wired to a model that does not "
                "support structured output"
            )

        wired = _resolve_port_value(state, input_src)
        if wired is not None:
            text = str(wired)
        elif input_source:
            text = str(state.get("scratch", {}).get(input_source, ""))
        else:
            text = _extract_last_message_text(state)

        bound = model.with_structured_output(wrapper)
        reply = await bound.ainvoke(
            [SystemMessage(content=instructions), HumanMessage(content=text)]
        )
        objects = [
            o.model_dump() if hasattr(o, "model_dump") else o
            for o in getattr(reply, "objects", []) or []
        ]
        return {
            "scratch": {node.id: objects},
            "messages": [
                HumanMessage(content=json.dumps(objects, ensure_ascii=False, default=str))
            ],
        }

    return _run


# One bound, two counters. `FlowGraphBuilder.build_depth` stops a reference
# cycle from hanging the *compiler* (a child is compiled inside build(), so
# A -> B -> A would recurse before a single message arrived); the
# `flow_depth` key in RunnableConfig stops one from hanging a *run*. Neither
# is a user field — a bound the user can edit is a guard the user can switch
# off. Publish-time cycle detection is the third, and the only one that gives
# the author an error before anything runs.
_MAX_FLOW_DEPTH = 5


_HUMAN_INPUT_UNMATCHED = "__unmatched__"


def _human_input_result_key(node_id: str) -> str:
    return f"_human_input_choice_{node_id}"


def _match_decision(answer: Any, labels: Sequence[str]) -> str | None:
    """The decision label the human's answer selects, or None.

    Accepts the answer as a bare string (the plain resume path) or a
    ``{"decision": ...}`` dict (the structured resume Phase 4b adds)."""
    if isinstance(answer, dict):
        answer = answer.get("decision", "")
    text = str(answer or "").strip().lower()
    for label in labels:
        if label.lower() == text:
            return label
    return None


def _make_human_input_node(node: FlowNode) -> Any:
    """Pauses the flow with ``interrupt()``, then routes on the action the
    person picked. A faithful port of Langflow's Human Input, on the
    platform's existing interrupt/resume pipeline. No timeout — the run waits
    in the thread until a reply arrives."""
    prompt = str(node.values.get("prompt", "") or "")
    labels = [
        str(r.get("label", "")).strip()
        for r in node.values.get("decisions", [])
        if isinstance(r, dict)
    ]
    labels = [label for label in labels if label]
    enable_unmatched = bool(node.values.get("enable_unmatched", False))
    result_key = _human_input_result_key(node.id)

    async def _run(state: FlowState, config: RunnableConfig) -> dict[str, Any]:
        answer = interrupt(
            {
                "type": "human_input",
                "node_id": node.id,
                "prompt": prompt,
                "decisions": labels,
            }
        )
        chosen = _match_decision(answer, labels)
        if chosen is None:
            if not enable_unmatched:
                raise FlowBuildError(
                    f"HumanInput '{node.id}' got an answer matching no action "
                    f"({answer!r}) and no unmatched branch is enabled"
                )
            chosen = _HUMAN_INPUT_UNMATCHED
        return {"scratch": {result_key: chosen, node.id: answer}}

    return _run


def _make_human_input_route_fn(node: FlowNode, edges: list[FlowEdge]):
    """Pure state read: route on the decision the node stored."""
    result_key = _human_input_result_key(node.id)
    label_to_target = {e.source_handle: e.target for e in edges if e.source == node.id}

    def _route(state: FlowState) -> str:
        choice = state.get("scratch", {}).get(result_key)
        handle = "unmatched" if choice == _HUMAN_INPUT_UNMATCHED else choice
        target = label_to_target.get(handle) or label_to_target.get("unmatched")
        if target is None:
            raise FlowBuildError(f"HumanInput '{node.id}' has no edge for action {choice!r}")
        return target

    return _route


_ROUTER_NODE_TYPES = (
    "Router",
    "Loop",
    "While",
    "ConditionalRouter",
    "SmartRouter",
    "HumanInput",
    "Guardrails",
)
# Boundary no-ops (_noop_node) — never a "stage" that produces answer text.
_BOUNDARY_NODE_TYPES = ("ChatInput", "ChatOutput")
# Nodes that forward state without producing an AI message. Walk past them
# when resolving which stage's output is the answer.
# One entry per node type whose runnable is a pure function of the node
# itself. A node type of that shape is a line in this table rather than
# another branch, and because ``build()`` routes every node through
# ``make_node`` the table cannot drift into a second dispatch that disagrees.
_SIMPLE_NODE_FACTORIES: dict[str, Callable[[FlowNode], Any]] = {
    "TextInput": _make_text_input_node,
    "FileInput": _make_file_input_node,
    "PromptTemplate": _make_prompt_template_node,
    "Merge": _make_merge_node,
    "SetVariable": _make_set_variable_node,
    "HumanInput": _make_human_input_node,
    "While": _make_loop_node,
    "DocumentSearch": _make_document_search_node,
    "KnowledgeBase": _make_document_search_node,
    "DocumentContext": _make_document_context_node,
    "GraphSearch": _make_graph_search_node,
    "GraphEntitySearch": _make_graph_entity_search_node,
    "GraphNeighborhood": _make_graph_neighborhood_node,
    "GraphStats": _make_graph_stats_node,
    "SyncTrigger": _make_sync_trigger_node,
}

# Addressable but inert: an edge endpoint (ChatOutput), or a branch point
# whose whole behaviour lives in its routing function (Router).
_NOOP_NODE_TYPES = frozenset({"ChatOutput", "Router"})


# Public: the stage timeline (AgentsRoute) needs the same answer the compiler
# uses, and a second hand-written copy went stale every time a node type was
# added. Exported through `agents.graphs` so consumers depend on the package's
# API rather than reaching into this module.
PASSTHROUGH_NODE_TYPES = (
    *_ROUTER_NODE_TYPES,
    *_BOUNDARY_NODE_TYPES,
    "Merge",
    "PromptTemplate",
    "TextInput",
    "FileInput",
    "SetVariable",
    # Processing nodes transform and forward; the answer comes from whatever
    # consumes them, so a stage walk must not stop here.
    "Operations",
    "SplitText",
    "TypeConverter",
    "Parser",
    "BatchRun",
)


def _resolve_final_stage_nodes(spec: FlowSpec, resource_ids: set[str]) -> set[str]:
    """Execution nodes whose output is the flow's answer: the direct
    predecessors of any ``ChatOutput`` node, walking back through nodes that
    only forward state (routers, ``Merge``, ``PromptTemplate``, boundary
    no-ops) to the nearest AI-message-producing node.

    Structure only — never touches graph execution. Used to tell the live
    SSE layer and read-time reconstruction which stage produces the single
    final answer bubble; every earlier stage folds into the timeline.
    """
    node_type = {n.id: n.type for n in spec.nodes}
    exit_ids = {n.id for n in spec.nodes if n.type == "ChatOutput"}

    preds: dict[str, list[str]] = {}
    for edge in spec.edges:
        if edge.source in resource_ids or edge.target in resource_ids:
            continue
        preds.setdefault(edge.target, []).append(edge.source)

    final: set[str] = set()
    seen: set[str] = set()
    stack = [src for xid in exit_ids for src in preds.get(xid, [])]
    while stack:
        nid = stack.pop()
        if nid in seen:
            continue
        seen.add(nid)
        if node_type.get(nid) in PASSTHROUGH_NODE_TYPES:
            # Forwards, does not produce — keep walking back.
            stack.extend(preds.get(nid, []))
        else:
            final.add(nid)
    return final


def _final_stage_in_cycle(spec: FlowSpec, resource_ids: set[str], final_ids: set[str]) -> bool:
    """True when a final-answer node sits on a Loop / ConditionalRouter cycle
    and so can run several times. The live SSE layer then folds every
    iteration and promotes only the last one to the answer bubble."""
    if not final_ids:
        return False
    adj: dict[str, list[str]] = {}
    for edge in spec.edges:
        if edge.source in resource_ids or edge.target in resource_ids:
            continue
        adj.setdefault(edge.source, []).append(edge.target)
    for start in final_ids:
        stack = list(adj.get(start, []))
        walked: set[str] = set()
        while stack:
            nid = stack.pop()
            if nid == start:
                return True
            if nid in walked:
                continue
            walked.add(nid)
            stack.extend(adj.get(nid, []))
    return False


# ---------------------------------------------------------------------------
# FlowGraphBuilder — assembles a validated FlowSpec into a StateGraph
# ---------------------------------------------------------------------------


class FlowGraphBuilder:
    """Compiles a FlowSpec into a runnable LangGraph graph.

    Assumes `spec` already passed FlowService.validate_flow (P1 Task 6) — this
    class does not re-validate. A spec that reaches here in a state validation
    should have caught still fails clearly (FlowBuildError), never silently.
    """

    def __init__(
        self,
        *,
        user_id: str | None = None,
        checkpointer: Any | None = None,
        repository: Any | None = None,
        registry: ComponentRegistry | None = None,
        mcp_tools_map: dict[str, Any] | None = None,
        build_depth: int = 0,
    ) -> None:
        self.user_id = user_id
        self.checkpointer = checkpointer
        self.repository = repository
        self.registry = registry
        self.mcp_tools_map = mcp_tools_map or {}
        # How many RunFlow hops deep this compile already is. A child
        # builder is constructed with build_depth + 1, so a reference cycle
        # hits the bound instead of recursing forever (see _MAX_FLOW_DEPTH).
        self.build_depth = build_depth
        # Populated by build(); the execution nodes whose output is the
        # flow's final answer. Stays empty if build() raises. See
        # _resolve_final_stage_nodes.
        self.final_stage_node_ids: set[str] = set()
        # Tools built from tool-mode components on this flow, by the name the
        # model sees. Merged into the map handed to every agent node.
        self.component_tools: dict[str, Any] = {}
        # True when a final node sits on a loop cycle (runs several times) —
        # the live layer then folds every iteration and promotes the last.
        self.final_stage_in_cycle: bool = False

    async def build(self, spec: FlowSpec) -> CompiledStateGraph:
        registry = self.registry or get_registry()

        # Migrate on read (design spec 4.6): a stored spec may predate a
        # template version bump (Router v1->v2 is the first). This is a pure,
        # in-memory rewrite; the next save persists it. Every routing/runtime
        # helper below can then assume current-version values.
        spec = migrate_spec(spec, registry=registry)

        try:
            resource_nodes, execution_nodes = partition_nodes(spec.nodes, registry)
        except UnknownComponentError as exc:
            raise FlowBuildError(str(exc)) from exc

        # A tool-mode node is a resource for this run, but it resolves to a
        # tool rather than to a model or a tool *name*. GraphBuilder resolves
        # tools by name from the map it is handed, so registering it there is
        # the whole integration — the agent side is untouched.
        tool_mode_nodes = {n.id: n for n in resource_nodes if is_tool_mode(n, registry.get(n.type))}
        resources = resolve_resources(resource_nodes, set(tool_mode_nodes))
        resource_ids = {n.id for n in resource_nodes}

        self.component_tools = {}
        for tool_node in tool_mode_nodes.values():
            tool = make_component_tool(
                tool_node,
                resources,
                user_id=self.user_id,
                mcp_tools_map=self.mcp_tools_map,
            )
            self.component_tools[tool.name] = tool

        # Which execution node each resource feeds — the resolver's per-node
        # model selection needs this; resources are never add_node'd.
        model_node_id_by_target: dict[str, str] = {}
        tool_node_ids_by_target: dict[str, list[str]] = defaultdict(list)
        mail_config_by_tool_node: dict[str, str] = {}
        memory_node_id_by_target: dict[str, str] = {}

        for edge in spec.edges:
            if edge.source in resource_ids:
                source_node = next((n for n in resource_nodes if n.id == edge.source), None)
                if source_node:
                    if source_node.type in _MODEL_RESOURCE_TYPES:
                        model_node_id_by_target[edge.target] = edge.source
                    elif source_node.id in tool_mode_nodes:
                        tool_node_ids_by_target[edge.target].append(edge.source)
                    elif source_node.type in _TOOL_RESOURCE_TYPES:
                        tool_node_ids_by_target[edge.target].append(edge.source)
                    elif source_node.type == "MailConfig":
                        mail_config_by_tool_node[edge.target] = edge.source
                    elif source_node.type == "LongTermMemory":
                        memory_node_id_by_target[edge.target] = edge.source

        entry_nodes = [n for n in execution_nodes if n.type == "ChatInput"]
        exit_nodes = [n for n in execution_nodes if n.type == "ChatOutput"]
        if not entry_nodes:
            raise FlowBuildError("Flow has no Chat Input node")
        if not exit_nodes:
            raise FlowBuildError("Flow has no Chat Output node")

        # Defense in depth for the validator/compiler reachability contract: a
        # spec whose only entry→exit path traverses a resource node compiles
        # into a dead-end graph that looks successful while silently doing
        # nothing. Validation rejects that shape; build() must not accept it
        # unvalidated either (e.g. a stale playground draft).
        execution_adjacency: dict[str, list[str]] = {n.id: [] for n in execution_nodes}
        for edge in spec.edges:
            if edge.source in resource_ids or edge.target in resource_ids:
                continue  # resource wiring — consumed above, not a graph edge
            execution_adjacency[edge.source].append(edge.target)
        reached: set[str] = set()
        pending = [n.id for n in entry_nodes]
        while pending:
            current = pending.pop()
            if current in reached:
                continue
            reached.add(current)
            pending.extend(execution_adjacency.get(current, []))
        if not any(n.id in reached for n in exit_nodes):
            raise FlowBuildError(
                "No Chat Output node is reachable from Chat Input through execution "
                "nodes; resource nodes are injected at build time and do not forward "
                "the flow"
            )

        self.final_stage_node_ids = _resolve_final_stage_nodes(spec, resource_ids)
        self.final_stage_in_cycle = _final_stage_in_cycle(
            spec, resource_ids, self.final_stage_node_ids
        )

        router_ids = {n.id for n in execution_nodes if n.type == "Router"}
        loop_ids = {n.id for n in execution_nodes if n.type == "Loop"}  # foreach
        while_ids = {n.id for n in execution_nodes if n.type == "While"}  # counter loop
        condrouter_ids = {n.id for n in execution_nodes if n.type == "ConditionalRouter"}
        smart_router_ids = {n.id for n in execution_nodes if n.type == "SmartRouter"}
        guardrails_ids = {n.id for n in execution_nodes if n.type == "Guardrails"}
        human_input_ids = {n.id for n in execution_nodes if n.type == "HumanInput"}
        # Merge nodes whose strategy needs branch arrival order: each incoming
        # edge is routed through an arrival-stamp node (added in the edge loop).
        stamped_merge_ids = {
            n.id
            for n in execution_nodes
            if n.type == "Merge" and n.values.get("strategy", "concat") in ("first", "last")
        }

        # Which node feeds each input handle of each node. This is how a
        # declared port carries a value: the consumer reads the producer's
        # scratch slot at runtime (see `_resolve_port_value`). Resource wiring
        # is excluded — it is consumed above and is not a graph edge.
        port_sources_by_node: dict[str, dict[str, str]] = defaultdict(dict)
        for edge in spec.edges:
            if edge.source in resource_ids or edge.target in resource_ids:
                continue
            port_sources_by_node[edge.target][edge.target_handle] = edge.source

        # Every table wired into a node's `df` handle, in edge order. Only
        # Concatenate reads past the first; port_sources_by_node keeps just one.
        frame_sources_by_node: dict[str, list[str]] = defaultdict(list)
        for edge in spec.edges:
            if edge.source in resource_ids or edge.target in resource_ids:
                continue
            if edge.target_handle == "df":
                frame_sources_by_node[edge.target].append(edge.source)

        # A foreach body's end is whatever wires back into the Loop's `input`
        # handle; its value is what each pass aggregates.
        def _body_end(loop_id: str) -> str | None:
            """The node that closes the foreach body.

            Two edges land on a Loop's `input`: Chat Input at the start of the
            turn, and the body's last node on every pass. Taking the first one
            found picks Chat Input in every normally-drawn flow, so the body
            has to be identified by reachability from the `item` branch —
            the same rule the validator uses.
            """
            item_target = next(
                (e.target for e in spec.edges if e.source == loop_id and e.source_handle == "item"),
                None,
            )
            if item_target is None:
                return None
            body = set()
            stack = [item_target]
            while stack:
                current = stack.pop()
                if current in body or current == loop_id:
                    continue
                body.add(current)
                stack.extend(execution_adjacency.get(current, []))
            return next(
                (
                    e.source
                    for e in spec.edges
                    if e.target == loop_id and e.target_handle == "input" and e.source in body
                ),
                None,
            )

        body_end_by_loop = {loop_id: _body_end(loop_id) for loop_id in loop_ids}

        graph = StateGraph(FlowState)

        # Every node type is built by `make_node`. The three cases below are
        # the only ones that need something `make_node` cannot see: the flow's
        # other nodes (ChatInput's per-turn reset list) or an awaited
        # sub-graph (AgentRef, Supervisor).
        for node in execution_nodes:
            if node.type == "ChatInput":
                graph.add_node(
                    node.id,
                    _make_chat_input_node(
                        sorted(while_ids), sorted(condrouter_ids), sorted(loop_ids)
                    ),
                )
                continue
            if node.type == "RunFlow":
                graph.add_node(node.id, await self._resolve_run_flow(node))
                continue
            if node.type == "AgentRef":
                subgraph = await self._resolve_agent_ref(node)
                graph.add_node(node.id, subgraph)
                continue
            if node.type == "Supervisor":
                subgraph = await self._resolve_supervisor(node)
                graph.add_node(node.id, subgraph)
                continue
            model_node_id = model_node_id_by_target.get(node.id)
            connected_tool_nodes = tool_node_ids_by_target.get(node.id, [])
            node_tool_names: list[str] = []
            node_tool_configs: dict[str, Any] = {}
            for t_id in connected_tool_nodes:
                if t_id in tool_mode_nodes:
                    component_tool_name = derive_tool_name(tool_mode_nodes[t_id])
                    if component_tool_name not in node_tool_names:
                        node_tool_names.append(component_tool_name)
                    continue
                for tool_name in resources.tool_names.get(t_id, []):
                    if tool_name not in node_tool_names:
                        node_tool_names.append(tool_name)
                if t_id in mail_config_by_tool_node:
                    mail_cfg_id = mail_config_by_tool_node[t_id]
                    config_val = resources.mail_config_ids.get(mail_cfg_id)
                    if config_val:
                        node_tool_configs["send_email"] = {"mail_config_id": config_val}

            graph.add_node(
                node.id,
                await make_node(
                    node,
                    resources,
                    user_id=self.user_id,
                    mcp_tools_map={**self.mcp_tools_map, **self.component_tools},
                    model_node_id=model_node_id,
                    mcp_tools=node_tool_names,
                    mcp_tool_configs=node_tool_configs,
                    memory_enabled=(node.id in memory_node_id_by_target),
                    port_sources=port_sources_by_node.get(node.id, {}),
                    body_end_id=body_end_by_loop.get(node.id),
                    extra_frame_sources=frame_sources_by_node.get(node.id, [])[1:],
                ),
            )

        stamped: set[str] = set()
        for edge in spec.edges:
            if edge.source in resource_ids or edge.target in resource_ids:
                continue  # resource wiring — consumed above, not a graph edge
            if (
                edge.source in router_ids
                or edge.source in loop_ids
                or edge.source in while_ids
                or edge.source in condrouter_ids
                or edge.source in smart_router_ids
                or edge.source in guardrails_ids
                or edge.source in human_input_ids
            ):
                continue  # handled by add_conditional_edges below
            if edge.target in stamped_merge_ids and edge.source not in stamped_merge_ids:
                stamp_id = f"__arrival__{edge.target}__{edge.source}"
                if stamp_id not in stamped:
                    graph.add_node(stamp_id, _make_arrival_stamp(edge.target, edge.source))
                    stamped.add(stamp_id)
                graph.add_edge(edge.source, stamp_id)
                graph.add_edge(stamp_id, edge.target)
                continue
            graph.add_edge(edge.source, edge.target)

        for router_id in router_ids:
            router_node = next(n for n in execution_nodes if n.id == router_id)
            graph.add_conditional_edges(router_id, self._make_router_fn(router_node, spec.edges))

        for loop_id in loop_ids:
            loop_node = next(n for n in execution_nodes if n.id == loop_id)
            graph.add_conditional_edges(loop_id, _make_foreach_route_fn(loop_node, spec.edges))

        for while_id in while_ids:
            while_node = next(n for n in execution_nodes if n.id == while_id)
            graph.add_conditional_edges(while_id, _make_loop_route_fn(while_node, spec.edges))

        for cr_id in condrouter_ids:
            cr_node = next(n for n in execution_nodes if n.id == cr_id)
            graph.add_conditional_edges(cr_id, _make_condrouter_route_fn(cr_node, spec.edges))

        for sr_id in smart_router_ids:
            sr_node = next(n for n in execution_nodes if n.id == sr_id)
            graph.add_conditional_edges(sr_id, _make_smart_router_route_fn(sr_node, spec.edges))

        for gr_id in guardrails_ids:
            gr_node = next(n for n in execution_nodes if n.id == gr_id)
            graph.add_conditional_edges(gr_id, _make_guardrails_route_fn(gr_node, spec.edges))

        for hi_id in human_input_ids:
            hi_node = next(n for n in execution_nodes if n.id == hi_id)
            graph.add_conditional_edges(hi_id, _make_human_input_route_fn(hi_node, spec.edges))

        for node in entry_nodes:
            graph.add_edge(START, node.id)
        for node in exit_nodes:
            graph.add_edge(node.id, END)

        compiled = graph.compile(checkpointer=self.checkpointer)

        # LangGraph's default recursion_limit (25 super-steps) is fine for an
        # acyclic flow but a loop can legitimately need more: every While /
        # ConditionalRouter / Loop pass is at least two super-steps (the node
        # plus its body). Raise the ceiling to the worst case the bounds
        # allow, so a valid flow never dies with GraphRecursionError; keep it
        # capped so a runaway still stops. A foreach Loop has no static bound,
        # so it gets a fixed allowance (very long collections may still hit
        # the cap).
        iteration_budget = sum(
            int(n.values.get("max_iterations") or 0)
            for n in execution_nodes
            if n.type in ("While", "ConditionalRouter")
        )
        iteration_budget += 50 * sum(1 for n in execution_nodes if n.type == "Loop")
        if iteration_budget:
            recursion_limit = max(25, min(500, 25 + 3 * iteration_budget))
            compiled = compiled.with_config({"recursion_limit": recursion_limit})

        return compiled

    async def _resolve_run_flow(self, node: FlowNode) -> Any:
        """Compile another published flow as this node (Langflow's Run Flow).

        Mirrors `_resolve_agent_ref`: the child compiles with
        `checkpointer=None`, so the parent owns persistence. It runs
        **isolated** — invoked with only the latest message, and only its
        answer comes back — so the two flows' `scratch` namespaces cannot
        collide. Two authors can each use a variable called `result` without
        knowing about each other.

        Returns a node callable rather than the raw subgraph, because the
        isolation and the depth check both happen *around* the child call.
        Nothing here reads the parent's edges, which is also the shape a
        tool-mode wrapper will need later.
        """
        flow_id = str(node.values.get("flow_id", "") or "").strip()
        if not flow_id:
            raise FlowBuildError(f"RunFlow '{node.id}' has no target flow selected")

        if self.build_depth >= _MAX_FLOW_DEPTH:
            raise FlowBuildError(
                f"RunFlow '{node.id}' exceeds the maximum flow nesting depth "
                f"({_MAX_FLOW_DEPTH}); check for a reference cycle"
            )

        try:
            definition_id = UUID(flow_id)
        except (ValueError, TypeError, AttributeError) as exc:
            raise FlowBuildError(
                f"RunFlow '{node.id}' has an invalid flow_id: {flow_id!r}"
            ) from exc

        definition = await self.repository.get_by_id(definition_id)
        if definition is None:
            raise FlowBuildError(f"RunFlow '{node.id}' references unknown flow '{flow_id}'")
        child_spec = getattr(definition, "flow_spec", None)
        if not child_spec:
            raise FlowBuildError(
                f"RunFlow '{node.id}' targets flow '{flow_id}', which has no published version"
            )

        child = await FlowGraphBuilder(
            user_id=self.user_id,
            checkpointer=None,
            repository=self.repository,
            registry=self.registry,
            mcp_tools_map=self.mcp_tools_map,
            build_depth=self.build_depth + 1,
        ).build(FlowSpec.model_validate(child_spec))

        async def _run(state: FlowState, config: RunnableConfig) -> dict[str, Any]:
            configurable = dict((config or {}).get("configurable", {}))
            depth = int(configurable.get("flow_depth", 0) or 0)
            if depth >= _MAX_FLOW_DEPTH:
                raise FlowBuildError(
                    f"RunFlow '{node.id}' exceeded the maximum flow nesting depth "
                    f"({_MAX_FLOW_DEPTH}) at run time"
                )
            configurable["flow_depth"] = depth + 1
            child_config = {**(config or {}), "configurable": configurable}

            # Isolation: seed only the latest message, keep only the answer.
            seed = list(state.get("messages", []))[-1:]
            result = await child.ainvoke(
                {"messages": seed, "scratch": {}, "arrivals": []}, child_config
            )

            produced = list(result.get("messages", []))[len(seed) :]
            answer = _extract_last_message_text(result)
            update: dict[str, Any] = {"scratch": {node.id: answer}}
            if produced:
                # Forward the child's own messages rather than re-wrapping the
                # text: a child ending in an agent produced an AIMessage, and
                # flattening that to some other type would lose what it is.
                update["messages"] = produced
            return update

        return _run

    async def _resolve_agent_ref(self, node: FlowNode) -> CompiledStateGraph:
        """Embed an existing classic agent as a subgraph — constraint #1's
        concrete proof. Mirrors Task 0's spike almost verbatim:
        `agents/graphs/builder.py` is called through its public API,
        unmodified, and compiled with `checkpointer=None` so the parent flow
        owns persistence (Task 0 finding A).
        """
        from agents.graphs.builder import GraphBuilder  # UNMODIFIED — do not edit

        agent_id = node.values.get("agent_id")
        if not agent_id:
            raise FlowBuildError(f"AgentRef '{node.id}' has no agent_id configured")

        try:
            definition_id = UUID(str(agent_id))
        except (ValueError, TypeError, AttributeError) as exc:
            raise FlowBuildError(
                f"AgentRef '{node.id}' has an invalid agent_id: {agent_id!r}"
            ) from exc

        definition = await self.repository.get_by_id(definition_id)
        if definition is None:
            raise FlowBuildError(f"AgentRef '{node.id}' references unknown agent '{agent_id}'")

        if definition.graph_schema == GraphSchemaType.FLOW:
            raise FlowBuildError(
                f"AgentRef '{node.id}' targets '{agent_id}', which is itself "
                "flow-backed; a flow cannot reference another flow (design spec 5.4)"
            )

        builder = GraphBuilder(checkpointer=None, repository=self.repository)
        return await builder.build_async(definition.graph_schema, definition.to_config())

    async def _resolve_supervisor(self, node: FlowNode) -> CompiledStateGraph:
        """Compile a Supervisor node by delegating to GraphBuilder.build_async('supervisor', ...).

        Sub-agents are resolved from sub_agents (list of agent IDs) through
        GraphBuilder's existing sub_agent_ids mechanism. Flow-backed agents
        are rejected explicitly to satisfy section 5.4.
        """
        from agents.graphs.builder import GraphBuilder
        from domain.flows.resolvers import is_flow_backed

        sub_agents = node.values.get("sub_agents")
        if not sub_agents:
            raise FlowBuildError(f"Supervisor node '{node.id}' must declare at least one sub_agent")

        if isinstance(sub_agents, str):
            sub_agent_ids = [sub_agents]
        elif isinstance(sub_agents, list):
            sub_agent_ids = [str(s) for s in sub_agents if s]
        else:
            sub_agent_ids = []

        if not sub_agent_ids:
            raise FlowBuildError(f"Supervisor node '{node.id}' must declare at least one sub_agent")

        for sub_id in sub_agent_ids:
            is_flow = await is_flow_backed(sub_id, repo=self.repository)
            if is_flow:
                raise FlowBuildError(
                    f"Supervisor node '{node.id}' references '{sub_id}', which is flow-backed; "
                    "a flow cannot embed another flow (design spec 5.4)"
                )

        supervisor_prompt = str(
            node.values.get("supervisor_prompt") or "You are a team supervisor."
        )
        config = {
            "supervisor_prompt": supervisor_prompt,
            "sub_agent_ids": sub_agent_ids,
        }

        builder = GraphBuilder(
            checkpointer=None,
            repository=self.repository,
            mcp_tools_map=self.mcp_tools_map,
        )
        return await builder.build_async("supervisor", config)

    @staticmethod
    def _make_router_fn(router_node: FlowNode, edges: list[FlowEdge]):
        routes_table = router_node.values.get("routes", [])
        label_to_target = {
            edge.source_handle: edge.target for edge in edges if edge.source == router_node.id
        }

        def _route(state: FlowState) -> str:
            # v2 rows: {source, operator, match_text, route}. ``source`` is a
            # Set Variable name, or blank for the latest message's text. v1
            # rows ({condition, route}) are rewritten to an ``is_truthy``
            # comparison by migrate_spec before build(), so this only ever
            # sees the v2 shape.
            scratch = state.get("scratch", {})
            for row in routes_table:
                if not isinstance(row, dict):
                    continue
                source = row.get("source", "")
                operator = row.get("operator") or "is_truthy"
                left = scratch.get(source) if source else _extract_last_message_text(state)
                if evaluate_comparison(operator, left, row.get("match_text", "")):
                    target = label_to_target.get(row.get("route"))
                    if target is not None:
                        return target
            default_target = label_to_target.get("default")
            if default_target is None:
                raise FlowBuildError(
                    f"Router '{router_node.id}' has no matching route and no 'default' fallback"
                )
            return default_target

        return _route


# ---------------------------------------------------------------------------
# Processing nodes — Langflow's data family
#
# The operation semantics live in `domain/flows/data_ops.py`, which is pure and
# tested against Langflow's own bodies. What happens here is plumbing: pick the
# right input for the family, run the operation, store the result and render a
# readable message alongside it.
# ---------------------------------------------------------------------------


def _render_processing_result(result: Any) -> str:
    """A readable message for any of the three result shapes."""
    import pandas as pd

    from domain.flows.data_ops import format_result_as_text

    if isinstance(result, pd.DataFrame):
        return result.to_string(index=False)
    if isinstance(result, dict):
        return json.dumps(result, ensure_ascii=False, default=str)
    return format_result_as_text(result)


def _make_operations_node(
    node: FlowNode,
    port_sources: dict[str, str] | None = None,
    extra_frame_sources: Sequence[str] | None = None,
) -> Any:
    """Langflow's Data Operations: thirty operations over Text, JSON and Table.

    Langflow picks the family with an ``input_type`` tab; its dispatch is by
    operation name alone and the three families share no name, so the operation
    is the only thing needed here too.

    ``extra_frame_sources`` carries the additional tables wired into ``df`` —
    Concatenate is the one operation that reads more than the first.
    """
    from domain.flows.data_ops import (
        JSON_OPERATIONS,
        TABLE_OPERATIONS,
        TEXT_OPERATIONS,
        run_json_operation,
        run_table_operation,
        run_text_operation,
    )

    operation = str(node.values.get("operation", "") or "").strip()
    if not operation:
        raise FlowBuildError(f"Operations '{node.id}' has no operation selected")
    if operation not in (TEXT_OPERATIONS | JSON_OPERATIONS | TABLE_OPERATIONS):
        raise FlowBuildError(f"Operations '{node.id}' has an unknown operation: {operation!r}")

    values = dict(node.values)
    sources = dict(port_sources or {})
    frame_sources = [sources["df"]] if "df" in sources else []
    frame_sources.extend(extra_frame_sources or [])

    async def _run(state: FlowState, config: RunnableConfig) -> dict[str, Any]:
        if operation in TEXT_OPERATIONS:
            # Wired Text port, then the field, then what the flow just
            # produced. Langflow's text_input is a required wired input; ours
            # sits in a conversation, so the latest message is the sensible
            # last resort — the same chain every other node here uses.
            wired = _resolve_port_value(state, sources.get("text_input"))
            if wired is not None:
                text = str(wired)
            else:
                text = str(values.get("text_input", "") or "") or _extract_last_message_text(state)
            result = run_text_operation(operation, text, values)
            # Langflow's empty-text guard returns None; store the empty string
            # so a downstream reader gets a value of the right shape.
            if result is None:
                result = ""
        elif operation in JSON_OPERATIONS:
            data = _resolve_port_value(state, sources.get("data"))
            if data is None:
                data = {}
            result = run_json_operation(operation, data, values)
        else:
            frames = []
            for source in frame_sources:
                frame = _resolve_port_value(state, source)
                if frame is not None:
                    frames.append(frame)
            merge_values = dict(values)
            for side in ("left_dataframe", "right_dataframe"):
                if side in sources:
                    merge_values[side] = _resolve_port_value(state, sources[side])
            result = run_table_operation(operation, frames, merge_values)

        return {
            "scratch": {node.id: result},
            "messages": [HumanMessage(content=_render_processing_result(result))],
        }

    return _run


def _make_split_text_node(node: FlowNode, port_sources: dict[str, str] | None = None) -> Any:
    """Langflow's Split Text: chunk text into one row per chunk."""
    from domain.flows.data_ops import split_text

    values = dict(node.values)
    source = (port_sources or {}).get("data_inputs")

    async def _run(state: FlowState, config: RunnableConfig) -> dict[str, Any]:
        wired = _resolve_port_value(state, source)
        payload = wired if wired is not None else _extract_last_message_text(state)
        try:
            frame = split_text(payload, values)
        except TypeError as exc:
            raise FlowBuildError(f"Split Text '{node.id}': {exc}") from exc
        return {
            "scratch": {node.id: frame},
            "messages": [HumanMessage(content=_render_processing_result(frame))],
        }

    return _run


def _make_type_converter_node(node: FlowNode, port_sources: dict[str, str] | None = None) -> Any:
    """Langflow's Type Convert: Message <-> JSON <-> Table."""
    from domain.flows.data_ops import convert_value

    output_type = str(node.values.get("output_type", "") or "Message")
    auto_parse = bool(node.values.get("auto_parse", False))
    source = (port_sources or {}).get("input_data")

    async def _run(state: FlowState, config: RunnableConfig) -> dict[str, Any]:
        wired = _resolve_port_value(state, source)
        payload = wired if wired is not None else _extract_last_message_text(state)
        try:
            result = convert_value(payload, output_type, auto_parse=auto_parse)
        except ValueError as exc:
            raise FlowBuildError(f"TypeConverter '{node.id}': {exc}") from exc
        return {
            "scratch": {node.id: result},
            "messages": [HumanMessage(content=_render_processing_result(result))],
        }

    return _run


# ---------------------------------------------------------------------------
# tool_mode — a flow component handed to an agent as a tool
#
# `GraphBuilder` needs no change: it resolves tools by name from the map the
# compiler hands it, and `maybe_wrap_mcp_tool` passes anything that is not
# `send_email` straight through. Registering the tool in that map is the whole
# integration.
# ---------------------------------------------------------------------------


def derive_tool_name(node: FlowNode) -> str:
    """The name the model sees.

    A configured ``tool_name`` wins; otherwise the node id, which already has
    the ``<type>-<short id>`` shape the canvas generates. Formatted to
    ``^[a-zA-Z0-9_-]+$`` the way Langflow's ``_format_tool_name`` does — the
    model picks a tool by its name, so a readable one is a real difference.
    """
    configured = str(node.values.get("tool_name", "") or "").strip()
    return re.sub(r"[^a-zA-Z0-9_-]", "-", configured or node.id)


def make_component_tool(
    node: FlowNode,
    resources: ResolvedResources,
    *,
    user_id: str | None = None,
    mcp_tools_map: dict[str, Any] | None = None,
) -> Any:
    """Wrap one flow component as a LangChain tool.

    Each call copies the node with the model's arguments written over
    ``values``, rebuilds the node function from the same factory the flow
    would use, and runs it against a fresh ``FlowState``.

    Running the component's own function is what keeps a tool call and a flow
    step from ever drifting apart; the fresh state is what keeps a tool call
    from touching the flow's.
    """
    from langchain_core.tools import StructuredTool

    from domain.flows.registry import get_registry
    from domain.flows.tool_schema import build_args_schema

    template = get_registry().get(node.type)
    args_schema = build_args_schema(template, node.values)

    async def _call(**kwargs: Any) -> Any:
        call_node = node.model_copy(update={"values": {**node.values, **kwargs}})
        fn = await make_node(
            call_node,
            resources,
            user_id=user_id,
            mcp_tools_map=mcp_tools_map,
        )
        result = await fn({"messages": [], "scratch": {}, "arrivals": []}, None)
        return result.get("scratch", {}).get(node.id)

    return StructuredTool(
        name=derive_tool_name(node),
        description=template.description or template.display_name,
        args_schema=args_schema,
        coroutine=_call,
    )


def _make_parser_node(node: FlowNode, port_sources: dict[str, str] | None = None) -> Any:
    """Langflow's Parser: render structured data through a template.

    Two modes. ``Parser`` formats each row or item with the template;
    ``Stringify`` renders the whole value readably (a table as markdown, JSON
    as a fenced block) and ignores the template.
    """
    from domain.flows.data_ops import parse_with_template, stringify_value

    mode = str(node.values.get("mode", "") or "Parser")
    pattern = str(node.values.get("pattern", "") or "")
    separator = str(node.values.get("sep", "\n") or "\n")
    clean_data = bool(node.values.get("clean_data", False))
    source = (port_sources or {}).get("input_data")

    async def _run(state: FlowState, config: RunnableConfig) -> dict[str, Any]:
        wired = _resolve_port_value(state, source)
        payload = wired if wired is not None else _extract_last_message_text(state)
        try:
            if mode == "Stringify":
                text = stringify_value(payload, clean_data=clean_data)
            else:
                text = parse_with_template(payload, pattern, separator)
        except (KeyError, ValueError) as exc:
            raise FlowBuildError(f"Parser '{node.id}': {exc!r}") from exc
        return {
            "scratch": {node.id: text},
            "messages": [HumanMessage(content=text)],
        }

    return _run


def _make_batch_run_node(
    node: FlowNode,
    model: BaseChatModel | None,
    port_sources: dict[str, str] | None = None,
) -> Any:
    """Langflow's Batch Run: one model call per row of a table.

    The whole table goes to the model in a single ``abatch``, and the answers
    come back as a new column beside the original rows. A blank column name
    sends the entire row, formatted the way Langflow does.
    """
    import pandas as pd

    column_name = str(node.values.get("column_name", "") or "")
    output_column = str(node.values.get("output_column_name", "") or "model_response")
    system_message = str(node.values.get("system_message", "") or "")
    source = (port_sources or {}).get("df")

    if model is None:
        from core import get_model, settings

        model = get_model(settings.DEFAULT_MODEL)

    def _row_as_text(row: dict[str, Any]) -> str:
        """Langflow renders a whole row as TOML-ish `col.value` lines."""
        return "\n".join(f'[{col}]\nvalue = "{val}"' for col, val in row.items())

    async def _run(state: FlowState, config: RunnableConfig) -> dict[str, Any]:
        frame = _resolve_port_value(state, source)
        if not isinstance(frame, pd.DataFrame):
            raise FlowBuildError(
                f"BatchRun '{node.id}' expects a table on its Table port, got "
                f"{type(frame).__name__}"
            )
        if column_name and column_name not in frame.columns:
            raise FlowBuildError(
                f"BatchRun '{node.id}': column '{column_name}' not found in the "
                f"table. Available columns: {', '.join(map(str, frame.columns))}"
            )

        records = frame.to_dict(orient="records")
        if column_name:
            texts = [str(row[column_name]) for row in records]
        else:
            texts = [_row_as_text(row) for row in records]

        conversations = [
            (
                [{"role": "system", "content": system_message}, {"role": "user", "content": text}]
                if system_message
                else [{"role": "user", "content": text}]
            )
            for text in texts
        ]

        replies = await model.abatch(conversations)
        rows: list[dict[str, Any]] = []
        for index, (row, reply) in enumerate(zip(records, replies, strict=False)):
            out = dict(row)
            out[output_column] = getattr(reply, "content", str(reply))
            out["batch_index"] = index
            rows.append(out)

        result = pd.DataFrame(rows)
        return {
            "scratch": {node.id: result},
            "messages": [HumanMessage(content=_render_processing_result(result))],
        }

    return _run
