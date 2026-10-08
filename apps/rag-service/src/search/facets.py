"""Facet counting and post-fusion refinement of search hits."""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING

from src.search.models import (
    FacetValue,
    HitKind,
    SearchFacets,
    SearchFilters,
    SearchGraph,
    SearchHit,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence


def _buckets(values: Iterable[str]) -> tuple[FacetValue, ...]:
    counts = Counter(values)
    return tuple(
        FacetValue(value=value, count=count)
        for value, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    )


def count_facets(hits: Sequence[SearchHit]) -> SearchFacets:
    """File types of document hits and labels of entity hits, most frequent first."""
    return SearchFacets(
        file_types=_buckets(
            hit.document.file_type for hit in hits if hit.document is not None and hit.document.file_type
        ),
        entity_labels=_buckets(hit.entity.label for hit in hits if hit.entity is not None),
    )


def _folded(values: frozenset[str] | None) -> frozenset[str] | None:
    return None if values is None else frozenset(value.casefold() for value in values)


def apply_filters(hits: Sequence[SearchHit], filters: SearchFilters) -> list[SearchHit]:
    """Keep hits matching every refinement.

    File types and entity labels each describe one kind of hit, so choosing one
    asks for that kind only: a file type keeps matching documents and drops
    entities, an entity label the reverse. With both, each kind keeps its matches.
    """
    file_types = _folded(filters.file_types)
    entity_labels = _folded(filters.entity_labels)

    def keep(hit: SearchHit) -> bool:
        if filters.collection_ids is not None and hit.collection_id not in filters.collection_ids:
            return False
        if hit.kind is HitKind.DOCUMENT:
            if file_types is None:
                return entity_labels is None
            file_type = hit.document.file_type if hit.document else None
            return file_type is not None and file_type.casefold() in file_types
        if hit.kind is HitKind.ENTITY:
            if entity_labels is None:
                return file_types is None
            label = hit.entity.label if hit.entity else ""
            return label.casefold() in entity_labels
        return True

    return [hit for hit in hits if keep(hit)]


def filter_graph(
    graph: SearchGraph,
    collection_ids: frozenset[str] | None,
    entity_labels: frozenset[str] | None,
) -> SearchGraph:
    """Restrict the subgraph to selected collections and labels, keeping it closed."""
    if collection_ids is None and entity_labels is None:
        return graph
    labels = _folded(entity_labels)
    nodes = tuple(
        node
        for node in graph.nodes
        if (collection_ids is None or node.collection_id in collection_ids)
        and (labels is None or node.label.casefold() in labels)
    )
    kept = {node.identifier for node in nodes}
    edges = tuple(
        edge
        for edge in graph.edges
        if (collection_ids is None or edge.collection_id in collection_ids)
        and edge.source in kept
        and edge.target in kept
    )
    return SearchGraph(nodes=nodes, edges=edges)
