"""Flow retrieval node factories (document search, context, knowledge graph)."""

from __future__ import annotations

from collections.abc import Callable
import time
from typing import Any

from langchain_core.runnables import RunnableConfig

from agents.graphs.flow.state import FlowState
from agents.graphs.stage_report import (
    report_stage_evidence,
    report_stage_output,
    summarise_chunks,
    summarise_graph_result,
)
from core.observability.logger import get_logger
from schemas.flows import FlowNode
from schemas.knowledge_evidence import KnowledgeEvidence
from service.flow_retrieval import default_retrieval_gateway
from service.knowledge_evidence.flow_evidence import document_evidence, graph_evidence, tool_name_for_node

from .retrieval_ports import RetrievalGateway, RetrievedChunk

logger = get_logger(__name__)

_gateway: RetrievalGateway = default_retrieval_gateway()


async def _execute_document_search(
    collection_id: str,
    query: str,
    *,
    top_k: int = 4,
    threshold: float | None = None,
    access_token: str | None = None,
) -> list[RetrievedChunk]:
    """Vector RAG over rag-service.

    The wire contract (request shape, ``page_content`` normalisation,
    threshold filtering) lives in ``integrations.rag_client``, behind the gateway.
    """
    if not query or not collection_id:
        return []
    try:
        return await _gateway.search_documents(
            collection_id,
            query,
            top_k=top_k,
            threshold=threshold,
            access_token=access_token,
        )
    except Exception as exc:
        # A local vector-store fallback used to live here, bypassing
        # rag-service's own authorization checks entirely. It also called
        # agents.tools.get_collection_name_from_uuid, which does not exist,
        # so it always raised and silently returned []  — removed rather
        # than fixed, since fixing it would restore the authz bypass.
        logger.warning("RAG search endpoint failed (%s)", exc)
        return []


def _elapsed_ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)


async def _report_evidence(
    node: FlowNode,
    build_evidence: Callable[[], KnowledgeEvidence],
    summarise: Callable[[], str],
) -> None:
    """Show the evidence as the stage's card, or the summary as text when it cannot be."""
    try:
        reported = await report_stage_evidence(node.id, build_evidence())
    except Exception:
        # The card is a display concern: it must never fail the flow.
        logger.warning("Could not report evidence for node %s", node.id, exc_info=True)
        reported = False
    if not reported:
        report_stage_output(node.id, summarise())


async def _report_documents(
    node: FlowNode,
    *,
    query: str,
    collection_id: str,
    chunks: list[RetrievedChunk],
    context: str,
    started: float,
    top_k: int,
    threshold: float | None,
) -> None:
    await _report_evidence(
        node,
        lambda: document_evidence(
            tool=tool_name_for_node(node.type),
            query=query,
            collection_id=collection_id,
            chunks=chunks,
            model_context=context,
            elapsed_ms=_elapsed_ms(started),
        ),
        lambda: summarise_chunks(chunks, top_k=top_k, threshold=threshold),
    )


async def _report_graph(
    node: FlowNode,
    *,
    query: str,
    collection_id: str,
    payload: Any,
    started: float,
    label: str,
) -> None:
    await _report_evidence(
        node,
        lambda: graph_evidence(
            tool=tool_name_for_node(node.type),
            query=query,
            collection_id=collection_id,
            payload=payload,
            elapsed_ms=_elapsed_ms(started),
        ),
        lambda: summarise_graph_result(payload, label=label),
    )


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
    threshold = float(node.values.get("threshold", 0.7)) if node.values.get("threshold") is not None else None

    async def _run(state: FlowState, config: RunnableConfig) -> dict[str, Any]:
        query = static_query or _extract_query(state)
        # access_token is no longer read from configurable: it was persisted
        # verbatim into checkpoint metadata there. The gateway token
        # is the same ContextVar AgentHelpers/run_route used to populate it.
        token = _gateway.access_token()
        started = time.perf_counter()
        chunks = await _execute_document_search(
            collection_id, query, top_k=top_k, threshold=threshold, access_token=token
        )
        context_str = "\n\n".join(c.text for c in chunks if c.text)
        await _report_documents(
            node,
            query=query,
            collection_id=collection_id,
            chunks=chunks,
            context=context_str,
            started=started,
            top_k=top_k,
            threshold=threshold,
        )
        return {
            "scratch": {
                # normalised dicts: DocumentContext and any other consumer
                # read a guaranteed `content` key, never a wire alias.
                node.id: [c.as_dict() for c in chunks],
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
            if isinstance(v, list) and v and isinstance(v[0], dict) and "content" in v[0]:
                docs_list.extend(v)

        formatted_chunks = []
        for d in docs_list:
            content = d.get("content") or ""
            source = d.get("metadata", {}).get("source") if isinstance(d.get("metadata"), dict) else None
            if source:
                formatted_chunks.append(f"[{source}]: {content}")
            else:
                formatted_chunks.append(content)

        context_str = "\n\n".join(formatted_chunks) if formatted_chunks else ""
        rendered = template.replace("{context}", context_str).replace("{query}", query)
        report_stage_output(
            node.id,
            f"{len(docs_list)} parça biçimlendirildi, {len(context_str)} karakter bağlam",
        )
        return {"scratch": {node.id: rendered}}

    return _run


async def _execute_graph_search(
    collection_id: str,
    query: str,
    *,
    limit: int = 10,
    access_token: str | None = None,
) -> Any:
    return await _gateway.search_graph(collection_id, query, limit=limit, access_token=access_token)


async def _execute_graph_entity_search(
    collection_id: str,
    query: str,
    *,
    entity_type: str | None = None,
    limit: int = 10,
    access_token: str | None = None,
) -> Any:
    return await _gateway.search_graph_entities(
        collection_id,
        query,
        entity_type=entity_type,
        limit=limit,
        access_token=access_token,
    )


async def _execute_graph_neighborhood(
    collection_id: str,
    entity_id: str,
    *,
    depth: int = 1,
    limit: int = 20,
    access_token: str | None = None,
) -> Any:
    return await _gateway.graph_neighborhood(
        collection_id, entity_id, depth=depth, limit=limit, access_token=access_token
    )


async def _execute_graph_stats(
    collection_id: str,
    *,
    access_token: str | None = None,
) -> Any:
    return await _gateway.graph_stats(collection_id, access_token=access_token)


def _make_graph_search_node(node: FlowNode) -> Any:
    collection_id = str(node.values.get("collection") or "")
    limit = int(node.values.get("limit", 10))

    async def _run(state: FlowState, config: RunnableConfig) -> dict[str, Any]:
        query = _extract_query(state)
        # access_token is no longer read from configurable: it was persisted
        # verbatim into checkpoint metadata there. The gateway token
        # is the same ContextVar AgentHelpers/run_route used to populate it.
        token = _gateway.access_token()
        started = time.perf_counter()
        results = await _execute_graph_search(collection_id, query, limit=limit, access_token=token)
        await _report_graph(
            node, query=query, collection_id=collection_id, payload=results, started=started, label="Graf arama"
        )
        return {"scratch": {node.id: results}}

    return _run


def _make_graph_entity_search_node(node: FlowNode) -> Any:
    collection_id = str(node.values.get("collection") or "")
    entity_type = node.values.get("entity_type")
    limit = int(node.values.get("limit", 10))

    async def _run(state: FlowState, config: RunnableConfig) -> dict[str, Any]:
        query = _extract_query(state)
        # access_token is no longer read from configurable: it was persisted
        # verbatim into checkpoint metadata there. The gateway token
        # is the same ContextVar AgentHelpers/run_route used to populate it.
        token = _gateway.access_token()
        started = time.perf_counter()
        results = await _execute_graph_entity_search(
            collection_id, query, entity_type=entity_type, limit=limit, access_token=token
        )
        await _report_graph(
            node, query=query, collection_id=collection_id, payload=results, started=started, label="Varlık arama"
        )
        return {"scratch": {node.id: results}}

    return _run


def _make_graph_neighborhood_node(node: FlowNode) -> Any:
    collection_id = str(node.values.get("collection") or "")
    depth = int(node.values.get("depth", 1))
    limit = int(node.values.get("limit", 20))

    async def _run(state: FlowState, config: RunnableConfig) -> dict[str, Any]:
        entity_id = _extract_query(state)
        # access_token is no longer read from configurable: it was persisted
        # verbatim into checkpoint metadata there. The gateway token
        # is the same ContextVar AgentHelpers/run_route used to populate it.
        token = _gateway.access_token()
        started = time.perf_counter()
        results = await _execute_graph_neighborhood(
            collection_id, entity_id, depth=depth, limit=limit, access_token=token
        )
        await _report_graph(
            node, query=entity_id, collection_id=collection_id, payload=results, started=started, label="Komşuluk"
        )
        return {"scratch": {node.id: results}}

    return _run


def _make_graph_stats_node(node: FlowNode) -> Any:
    collection_id = str(node.values.get("collection") or "")

    async def _run(state: FlowState, config: RunnableConfig) -> dict[str, Any]:
        # access_token is no longer read from configurable: it was persisted
        # verbatim into checkpoint metadata there. The gateway token
        # is the same ContextVar AgentHelpers/run_route used to populate it.
        token = _gateway.access_token()
        results = await _execute_graph_stats(collection_id, access_token=token)
        report_stage_output(node.id, summarise_graph_result(results, label="Graf istatistiği"))
        return {"scratch": {node.id: results}}

    return _run
