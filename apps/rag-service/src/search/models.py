"""Framework-free value types of the knowledge search domain."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

from src.retrieval.contract import RetrievalKind

if TYPE_CHECKING:
    from collections.abc import Mapping

MAX_LIMIT = 100
DEFAULT_LIMIT = 50
DEFAULT_NEIGHBORHOOD_DEPTH = 1
DEFAULT_NEIGHBORHOOD_LIMIT = 100


class HitKind(StrEnum):
    """What a search hit points at."""

    DOCUMENT = "document"
    ENTITY = "entity"


class SourceType(StrEnum):
    """How a collection's content arrived."""

    DOCUMENT = "document"
    CONNECTOR = "connector"


class CollectionStatus(StrEnum):
    """Outcome of searching one collection."""

    OK = "ok"
    FAILED = "failed"


class RelationDirection(StrEnum):
    """Direction of a relationship relative to the entity it is listed on."""

    OUT = "out"
    IN = "in"


@dataclass(frozen=True)
class SearchableCollection:
    """A collection the caller may read, with what can be searched in it."""

    identifier: str
    name: str
    source_type: SourceType
    connector_type: str
    sync_status: str
    has_graph: bool
    # The graph store could not be asked, so ``has_graph`` is unknown, not false.
    graph_unreachable: bool = False


@dataclass(frozen=True)
class DocumentHit:
    """A vector-search passage and the document it came from."""

    content: str
    file_id: str | None
    source: str | None
    title: str | None
    page: int | None
    section: str | None
    file_type: str | None
    metadata: Mapping[str, object]


@dataclass(frozen=True)
class EntityRelation:
    """One relationship of an entity hit, seen from that entity."""

    type: str
    direction: RelationDirection
    node_id: str
    node_name: str
    node_label: str


@dataclass(frozen=True)
class EntityHit:
    """A graph entity that matched the query directly."""

    node_id: str
    name: str
    label: str
    matched: bool
    properties: Mapping[str, object]
    relations: tuple[EntityRelation, ...]
    neighbor_count: int


@dataclass(frozen=True)
class SearchHit:
    """One ranked search result; exactly one of document or entity is set."""

    identifier: str
    kind: HitKind
    relevance: float
    score: float
    collection_id: str
    collection_name: str
    document: DocumentHit | None = None
    entity: EntityHit | None = None


@dataclass(frozen=True)
class SearchGraphNode:
    """A graph node tagged with the collection it belongs to."""

    identifier: str
    name: str
    label: str
    matched: bool
    score: float | None
    collection_id: str
    properties: Mapping[str, object]


@dataclass(frozen=True)
class SearchGraphEdge:
    """A graph edge tagged with the collection it belongs to."""

    identifier: str | None
    source: str
    target: str
    type: str
    collection_id: str
    properties: Mapping[str, object]


@dataclass(frozen=True)
class SearchGraph:
    """A closed subgraph: every edge's endpoints are among the nodes."""

    nodes: tuple[SearchGraphNode, ...] = ()
    edges: tuple[SearchGraphEdge, ...] = ()


@dataclass(frozen=True)
class CollectionOutcome:
    """Per-collection hit counts before filters, and whether it answered."""

    identifier: str
    name: str
    document_hits: int
    entity_hits: int
    status: CollectionStatus


@dataclass(frozen=True)
class FacetValue:
    """One facet bucket."""

    value: str
    count: int


@dataclass(frozen=True)
class SearchFacets:
    """Facets computed over the unfiltered fused hits."""

    file_types: tuple[FacetValue, ...] = ()
    entity_labels: tuple[FacetValue, ...] = ()


@dataclass(frozen=True)
class SearchFilters:
    """Refinements applied after fusion; ``None`` means no refinement."""

    collection_ids: frozenset[str] | None = None
    file_types: frozenset[str] | None = None
    entity_labels: frozenset[str] | None = None


@dataclass(frozen=True)
class KnowledgeSearchRequest:
    """A validated search request with the trusted caller identity."""

    query: str
    user_id: str
    graph_allowed: bool
    kind: RetrievalKind = RetrievalKind.HYBRID
    limit: int = DEFAULT_LIMIT
    filters: SearchFilters = field(default_factory=SearchFilters)


@dataclass(frozen=True)
class KnowledgeSearchResult:
    """Everything the search page renders for one query."""

    query: str
    kind: RetrievalKind
    elapsed_ms: int
    total: int
    graph_available: bool
    hits: tuple[SearchHit, ...]
    graph: SearchGraph
    collections: tuple[CollectionOutcome, ...]
    facets: SearchFacets
    graph_unavailable: bool = False


@dataclass(frozen=True)
class NeighborhoodRequest:
    """Expand the graph around nodes of one collection."""

    user_id: str
    collection_id: str
    node_ids: tuple[str, ...]
    depth: int = DEFAULT_NEIGHBORHOOD_DEPTH
    limit: int = DEFAULT_NEIGHBORHOOD_LIMIT
