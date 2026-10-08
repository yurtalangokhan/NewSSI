"""KnowledgeEvidence for flow retrieval nodes.

Flow nodes call rag-service directly (not through tools-service), so they
build the same evidence contract here from what they retrieved.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from integrations.rag_client import RagChunk
from schemas.knowledge_evidence import (
    EvidenceChunk,
    EvidenceCollection,
    EvidenceGraph,
    EvidenceKind,
    KnowledgeEvidence,
)

_TOOL_BY_NODE_TYPE = {
    "DocumentSearch": "document_search",
    "KnowledgeBase": "document_search",
    "GraphSearch": "graph_search",
    "GraphEntitySearch": "graph_entity_search",
    "GraphNeighborhood": "graph_neighborhood",
}


def tool_name_for_node(node_type: str) -> str:
    """The search a retrieval node performs, named like a tool for the timeline."""
    return _TOOL_BY_NODE_TYPE.get(node_type, "knowledge_search")


def document_evidence(
    *,
    tool: str,
    query: str,
    collection_id: str,
    chunks: Sequence[RagChunk],
    model_context: str,
    elapsed_ms: int | None,
) -> KnowledgeEvidence:
    """Evidence for a vector search: the non-empty chunks, numbered from 1."""
    retrieved = [chunk for chunk in chunks if chunk.text]
    return KnowledgeEvidence(
        kind=EvidenceKind.DOCUMENT,
        tool=tool,
        query=query,
        collections=(EvidenceCollection(id=collection_id),),
        chunks=tuple(
            EvidenceChunk.from_hit(
                ref=ref,
                collection_id=collection_id,
                content=chunk.text,
                hit_id=chunk.id,
                score=chunk.score,
                metadata=chunk.metadata,
            )
            for ref, chunk in enumerate(retrieved, start=1)
        ),
        model_context=model_context,
        elapsed_ms=elapsed_ms,
    )


def graph_evidence(
    *,
    tool: str,
    query: str,
    collection_id: str,
    payload: Any,
    elapsed_ms: int | None,
) -> KnowledgeEvidence:
    """Evidence for a graph node: a search result, a neighbourhood, or an entity list."""
    nodes, edges, seeds, context = _graph_parts(payload)
    return KnowledgeEvidence(
        kind=EvidenceKind.GRAPH,
        tool=tool,
        query=query,
        collections=(EvidenceCollection(id=collection_id),),
        graph=EvidenceGraph(
            nodes=tuple(_node(node, matched=_is_seed(node, seeds, query)) for node in nodes),
            edges=tuple(edge for raw in edges if (edge := _edge(raw)) is not None),
        ),
        model_context=context,
        elapsed_ms=elapsed_ms,
    )


def _graph_parts(payload: Any) -> tuple[list[Mapping[str, Any]], list[Mapping[str, Any]], set[str] | None, str]:
    """``(nodes, edges, seed ids or None when every node is a hit, context)``."""
    if isinstance(payload, list):
        return [node for node in payload if isinstance(node, Mapping)], [], None, ""
    if not isinstance(payload, Mapping):
        return [], [], set(), ""
    nodes = [node for node in payload.get("nodes") or [] if isinstance(node, Mapping)]
    edges = [edge for edge in payload.get("edges") or [] if isinstance(edge, Mapping)]
    seed_ids = payload.get("seed_node_ids")
    seeds = {str(seed) for seed in seed_ids} if isinstance(seed_ids, list) else set()
    context = payload.get("context")
    return nodes, edges, seeds, context if isinstance(context, str) else ""


def _is_seed(node: Mapping[str, Any], seeds: set[str] | None, query: str) -> bool:
    if seeds is None:
        return True
    node_id = str(node.get("id"))
    # A neighbourhood has no seed list; the entity it was expanded from is the hit.
    return node_id in seeds if seeds else node_id == query


def _node(node: Mapping[str, Any], *, matched: bool) -> dict[str, Any]:
    properties = node.get("properties") if isinstance(node.get("properties"), Mapping) else {}
    return {
        "id": str(node.get("id")),
        "name": str(node.get("name") or node.get("id")),
        "label": str(node.get("label") or "Entity"),
        "matched": matched,
        "score": properties.get("rrf_score"),
        "properties": properties,
    }


def _edge(edge: Mapping[str, Any]) -> dict[str, Any] | None:
    source, target = edge.get("source"), edge.get("target")
    if source is None or target is None:
        return None
    properties = edge.get("properties") if isinstance(edge.get("properties"), Mapping) else {}
    return {
        "id": str(edge["id"]) if edge.get("id") is not None else None,
        "source": str(source),
        "target": str(target),
        "type": str(edge.get("type") or "RELATED_TO"),
        "properties": properties,
    }
