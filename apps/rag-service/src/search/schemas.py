"""HTTP bodies of the search routes and their mapping from domain values."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from src.retrieval.contract import RetrievalKind
from src.retrieval.schemas import (
    RetrievalGraphEdgeBody,
    RetrievalGraphNodeBody,
)
from src.search.models import (
    DEFAULT_LIMIT,
    DEFAULT_NEIGHBORHOOD_DEPTH,
    DEFAULT_NEIGHBORHOOD_LIMIT,
    MAX_LIMIT,
    CollectionOutcome,
    FacetValue,
    KnowledgeSearchResult,
    SearchableCollection,
    SearchGraph,
    SearchHit,
)

MAX_COLLECTION_FILTERS = 50
MAX_VALUE_FILTERS = 20
MAX_QUERY_LENGTH = 1000
MAX_NEIGHBORHOOD_NODES = 20
MAX_NEIGHBORHOOD_DEPTH = 3
MAX_NEIGHBORHOOD_LIMIT = 300

FilterValue = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class KnowledgeSearchRequestBody(BaseModel):
    """Search request; filters refine hits after facets are counted."""

    model_config = ConfigDict(extra="forbid")

    query: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_QUERY_LENGTH),
    ]
    kind: Literal["hybrid", "vector", "graph"] = RetrievalKind.HYBRID.value
    limit: int = Field(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT)
    collection_ids: list[FilterValue] | None = Field(default=None, max_length=MAX_COLLECTION_FILTERS)
    file_types: list[FilterValue] | None = Field(default=None, max_length=MAX_VALUE_FILTERS)
    entity_labels: list[FilterValue] | None = Field(default=None, max_length=MAX_VALUE_FILTERS)


class DocumentHitBody(BaseModel):
    """The passage and document descriptors of a document hit."""

    content: str
    file_id: str | None
    source: str | None
    title: str | None
    page: int | None
    section: str | None
    file_type: str | None
    metadata: dict[str, object]


class EntityRelationBody(BaseModel):
    """One relationship of an entity hit."""

    type: str
    direction: Literal["out", "in"]
    node_id: str
    node_name: str
    node_label: str


class EntityHitBody(BaseModel):
    """A matched graph entity."""

    node_id: str
    name: str
    label: str
    matched: bool
    properties: dict[str, object]
    relations: list[EntityRelationBody]
    neighbor_count: int


class SearchHitBody(BaseModel):
    """One ranked hit; ``relevance`` is relative to the best hit (0-1)."""

    id: str
    kind: Literal["document", "entity"]
    relevance: float
    score: float
    collection_id: str
    collection_name: str
    document: DocumentHitBody | None
    entity: EntityHitBody | None

    @classmethod
    def from_hit(cls, hit: SearchHit) -> SearchHitBody:
        """Map a domain hit."""
        document = hit.document
        entity = hit.entity
        return cls(
            id=hit.identifier,
            kind=hit.kind.value,
            relevance=hit.relevance,
            score=hit.score,
            collection_id=hit.collection_id,
            collection_name=hit.collection_name,
            document=DocumentHitBody(
                content=document.content,
                file_id=document.file_id,
                source=document.source,
                title=document.title,
                page=document.page,
                section=document.section,
                file_type=document.file_type,
                metadata=dict(document.metadata),
            )
            if document is not None
            else None,
            entity=EntityHitBody(
                node_id=entity.node_id,
                name=entity.name,
                label=entity.label,
                matched=entity.matched,
                properties=dict(entity.properties),
                relations=[
                    EntityRelationBody(
                        type=relation.type,
                        direction=relation.direction.value,
                        node_id=relation.node_id,
                        node_name=relation.node_name,
                        node_label=relation.node_label,
                    )
                    for relation in entity.relations
                ],
                neighbor_count=entity.neighbor_count,
            )
            if entity is not None
            else None,
        )


class SearchGraphNodeBody(RetrievalGraphNodeBody):
    """A graph node with its collection."""

    collection_id: str


class SearchGraphEdgeBody(RetrievalGraphEdgeBody):
    """A graph edge with its collection."""

    collection_id: str


class SearchGraphBody(BaseModel):
    """A closed subgraph."""

    nodes: list[SearchGraphNodeBody]
    edges: list[SearchGraphEdgeBody]

    @classmethod
    def from_graph(cls, graph: SearchGraph) -> SearchGraphBody:
        """Map a domain graph."""
        return cls(
            nodes=[
                SearchGraphNodeBody(
                    id=node.identifier,
                    name=node.name,
                    label=node.label,
                    matched=node.matched,
                    score=node.score,
                    collection_id=node.collection_id,
                    properties=dict(node.properties),
                )
                for node in graph.nodes
            ],
            edges=[
                SearchGraphEdgeBody(
                    id=edge.identifier,
                    source=edge.source,
                    target=edge.target,
                    type=edge.type,
                    collection_id=edge.collection_id,
                    properties=dict(edge.properties),
                )
                for edge in graph.edges
            ],
        )


class CollectionOutcomeBody(BaseModel):
    """Per-collection unfiltered hit counts and status."""

    id: str
    name: str
    document_hits: int
    entity_hits: int
    status: Literal["ok", "failed"]

    @classmethod
    def from_outcome(cls, outcome: CollectionOutcome) -> CollectionOutcomeBody:
        """Map a domain outcome."""
        return cls(
            id=outcome.identifier,
            name=outcome.name,
            document_hits=outcome.document_hits,
            entity_hits=outcome.entity_hits,
            status=outcome.status.value,
        )


class FacetValueBody(BaseModel):
    """One facet bucket."""

    value: str
    count: int


class SearchFacetsBody(BaseModel):
    """Facets over the unfiltered hits."""

    file_types: list[FacetValueBody]
    entity_labels: list[FacetValueBody]


def _facet_bodies(values: tuple[FacetValue, ...]) -> list[FacetValueBody]:
    return [FacetValueBody(value=value.value, count=value.count) for value in values]


class KnowledgeSearchResponseBody(BaseModel):
    """Everything the knowledge search page renders for one query."""

    query: str
    kind: Literal["hybrid", "vector", "graph"]
    elapsed_ms: int
    total: int
    graph_available: bool
    graph_unavailable: bool = False
    hits: list[SearchHitBody]
    graph: SearchGraphBody
    collections: list[CollectionOutcomeBody]
    facets: SearchFacetsBody

    @classmethod
    def from_result(cls, result: KnowledgeSearchResult) -> KnowledgeSearchResponseBody:
        """Map a domain result."""
        return cls(
            query=result.query,
            kind=result.kind.value,
            elapsed_ms=result.elapsed_ms,
            total=result.total,
            graph_available=result.graph_available,
            graph_unavailable=result.graph_unavailable,
            hits=[SearchHitBody.from_hit(hit) for hit in result.hits],
            graph=SearchGraphBody.from_graph(result.graph),
            collections=[CollectionOutcomeBody.from_outcome(outcome) for outcome in result.collections],
            facets=SearchFacetsBody(
                file_types=_facet_bodies(result.facets.file_types),
                entity_labels=_facet_bodies(result.facets.entity_labels),
            ),
        )


class SearchSourceBody(BaseModel):
    """A collection the caller can search."""

    id: str
    name: str
    source_type: Literal["document", "connector"]
    connector_type: str
    sync_status: str
    has_graph: bool


class SearchSourcesResponseBody(BaseModel):
    """Searchable collections in display order."""

    sources: list[SearchSourceBody]

    @classmethod
    def from_sources(cls, sources: tuple[SearchableCollection, ...]) -> SearchSourcesResponseBody:
        """Map domain collections."""
        return cls(
            sources=[
                SearchSourceBody(
                    id=source.identifier,
                    name=source.name,
                    source_type=source.source_type.value,
                    connector_type=source.connector_type,
                    sync_status=source.sync_status,
                    has_graph=source.has_graph,
                )
                for source in sources
            ]
        )


class NeighborhoodRequestBody(BaseModel):
    """Expand the graph around up to 20 nodes of one collection."""

    model_config = ConfigDict(extra="forbid")

    collection_id: FilterValue
    node_ids: list[FilterValue] = Field(min_length=1, max_length=MAX_NEIGHBORHOOD_NODES)
    depth: int = Field(default=DEFAULT_NEIGHBORHOOD_DEPTH, ge=1, le=MAX_NEIGHBORHOOD_DEPTH)
    limit: int = Field(default=DEFAULT_NEIGHBORHOOD_LIMIT, ge=1, le=MAX_NEIGHBORHOOD_LIMIT)
