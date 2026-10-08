"""Pure mappers from retrieval results onto search-domain hits and graphs."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import PurePosixPath
import re
from typing import TYPE_CHECKING

from src.retrieval.contract import RetrievalKind
from src.search.models import (
    DocumentHit,
    EntityHit,
    EntityRelation,
    HitKind,
    RelationDirection,
    SearchableCollection,
    SearchGraph,
    SearchGraphEdge,
    SearchGraphNode,
    SearchHit,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from src.retrieval.contract import (
        GraphEdgeView,
        GraphNodeView,
        RetrievalGraph,
        RetrievalHit,
    )

MAX_RELATIONS = 3
MAX_GRAPH_NODES = 200
MAX_GRAPH_EDGES = 400

_FILE_TYPE = re.compile(r"^[a-z0-9]{1,10}$")


def file_type_of(name: str | None) -> str | None:
    """Lower-case file extension of a document name, when it looks like one."""
    if not name:
        return None
    suffix = PurePosixPath(name).suffix.lower().lstrip(".")
    return suffix if _FILE_TYPE.match(suffix) else None


def _text(metadata: Mapping[str, object], *keys: str) -> str | None:
    for key in keys:
        value = metadata.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _page(metadata: Mapping[str, object]) -> int | None:
    value = _text(metadata, "page", "page_number")
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def document_hit_from_retrieval(hit: RetrievalHit) -> DocumentHit:
    """Read the document descriptors the ingestion pipeline stores per chunk."""
    metadata = hit.metadata
    source = _text(metadata, "source", "filename")
    return DocumentHit(
        content=hit.content,
        file_id=_text(metadata, "file_id"),
        source=source,
        title=_text(metadata, "title"),
        page=_page(metadata),
        section=_text(metadata, "section"),
        file_type=file_type_of(source),
        metadata=metadata,
    )


def _relations(
    node: GraphNodeView,
    edges: Sequence[GraphEdgeView],
    nodes_by_id: Mapping[str, GraphNodeView],
) -> tuple[tuple[EntityRelation, ...], int]:
    outgoing: list[EntityRelation] = []
    incoming: list[EntityRelation] = []
    neighbors: set[str] = set()
    for edge in edges:
        if edge.source == node.identifier:
            other_id, direction, bucket = edge.target, RelationDirection.OUT, outgoing
        elif edge.target == node.identifier:
            other_id, direction, bucket = edge.source, RelationDirection.IN, incoming
        else:
            continue
        neighbors.add(other_id)
        other = nodes_by_id.get(other_id)
        if other is None:
            continue
        bucket.append(
            EntityRelation(
                type=edge.type,
                direction=direction,
                node_id=other.identifier,
                node_name=other.name,
                node_label=other.label,
            )
        )
    return tuple([*outgoing, *incoming][:MAX_RELATIONS]), len(neighbors)


def entity_hits_from_graph(graph: RetrievalGraph) -> list[EntityHit]:
    """Matched (seed) nodes, best score first, with their nearest relations."""
    nodes_by_id = {node.identifier: node for node in graph.nodes}
    matched = sorted(
        (node for node in graph.nodes if node.matched),
        key=lambda node: (node.score is None, -(node.score or 0.0)),
    )
    hits: list[EntityHit] = []
    for node in matched:
        relations, neighbor_count = _relations(node, graph.edges, nodes_by_id)
        hits.append(
            EntityHit(
                node_id=node.identifier,
                name=node.name,
                label=node.label,
                matched=True,
                properties=node.properties,
                relations=relations,
                neighbor_count=neighbor_count,
            )
        )
    return hits


def document_search_hits(collection: SearchableCollection, hits: Sequence[RetrievalHit]) -> list[SearchHit]:
    """Vector hits of one collection as ranked, not yet fused, search hits."""
    return [
        SearchHit(
            identifier=hit.identifier or f"{collection.identifier}:{position}",
            kind=HitKind.DOCUMENT,
            relevance=0.0,
            score=hit.score,
            collection_id=collection.identifier,
            collection_name=collection.name,
            document=document_hit_from_retrieval(hit),
        )
        for position, hit in enumerate(hits)
        if hit.source == RetrievalKind.VECTOR.value
    ]


def entity_search_hits(collection: SearchableCollection, graph: RetrievalGraph) -> list[SearchHit]:
    """Matched entities of one collection as ranked, not yet fused, hits."""
    scores = {node.identifier: node.score for node in graph.nodes}
    return [
        SearchHit(
            identifier=entity.node_id,
            kind=HitKind.ENTITY,
            relevance=0.0,
            score=scores.get(entity.node_id) or 0.0,
            collection_id=collection.identifier,
            collection_name=collection.name,
            entity=entity,
        )
        for entity in entity_hits_from_graph(graph)
    ]


@dataclass
class _NodeSlot:
    node: SearchGraphNode
    order: int


def _max_score(first: float | None, second: float | None) -> float | None:
    if first is None:
        return second
    if second is None:
        return first
    return max(first, second)


def merge_graphs(
    parts: Sequence[tuple[str, RetrievalGraph]],
    *,
    max_nodes: int = MAX_GRAPH_NODES,
    max_edges: int = MAX_GRAPH_EDGES,
) -> SearchGraph:
    """Union per-collection subgraphs, keep matched nodes first when capping."""
    slots: dict[str, _NodeSlot] = {}
    for collection_id, graph in parts:
        for node in graph.nodes:
            slot = slots.get(node.identifier)
            if slot is None:
                slots[node.identifier] = _NodeSlot(
                    node=SearchGraphNode(
                        identifier=node.identifier,
                        name=node.name,
                        label=node.label,
                        matched=node.matched,
                        score=node.score,
                        collection_id=collection_id,
                        properties=node.properties,
                    ),
                    order=len(slots),
                )
            else:
                slot.node = replace(
                    slot.node,
                    matched=slot.node.matched or node.matched,
                    score=_max_score(slot.node.score, node.score),
                )

    ranked = sorted(slots.values(), key=lambda slot: (not slot.node.matched, slot.order))
    kept = tuple(slot.node for slot in ranked[:max_nodes])
    kept_ids = {node.identifier for node in kept}

    edges: list[SearchGraphEdge] = []
    seen_edges: set[object] = set()
    for collection_id, graph in parts:
        for edge in graph.edges:
            if len(edges) >= max_edges:
                break
            identity = edge.identifier or (edge.source, edge.target, edge.type)
            if identity in seen_edges:
                continue
            if edge.source not in kept_ids or edge.target not in kept_ids:
                continue
            seen_edges.add(identity)
            edges.append(
                SearchGraphEdge(
                    identifier=edge.identifier,
                    source=edge.source,
                    target=edge.target,
                    type=edge.type,
                    collection_id=collection_id,
                    properties=edge.properties,
                )
            )
    return SearchGraph(nodes=kept, edges=tuple(edges))
