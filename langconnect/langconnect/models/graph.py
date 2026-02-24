"""Pydantic models for Graph RAG entities, relations, and queries."""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


# =====================
# Graph Node / Edge
# =====================


class GraphNode(BaseModel):
    """A node in the knowledge graph."""

    id: str = Field(..., description="Neo4j internal element id or custom id.")
    label: str = Field(..., description="Primary label of the node (e.g. Person, Company).")
    name: str = Field(..., description="Human-readable name of the entity.")
    properties: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional properties stored on the node.",
    )


class GraphEdge(BaseModel):
    """An edge (relationship) in the knowledge graph."""

    id: str = Field(..., description="Neo4j internal element id or custom id.")
    source: str = Field(..., description="Element id of the source node.")
    target: str = Field(..., description="Element id of the target node.")
    type: str = Field(..., description="Relationship type (e.g. WORKS_AT, KNOWS).")
    properties: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional properties stored on the relationship.",
    )


class GraphData(BaseModel):
    """Combined graph data with nodes and edges."""

    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)


# =====================
# Clustered / Scalable Graph
# =====================


class ClusterNode(BaseModel):
    """A supernode representing a cluster of entities."""

    id: str = Field(..., description="Cluster identifier (e.g. 'cluster_0').")
    label: str = Field(..., description="Dominant label in this cluster.")
    name: str = Field(..., description="Display name for the cluster.")
    node_count: int = Field(0, description="Number of nodes in this cluster.")
    top_entities: list[str] = Field(
        default_factory=list,
        description="Names of the most important entities in the cluster.",
    )
    properties: dict[str, Any] = Field(default_factory=dict)
    is_cluster: bool = Field(True, description="Flag to identify supernode clusters.")


class ClusterEdge(BaseModel):
    """An aggregated edge between two clusters."""

    id: str = Field(..., description="Aggregated edge identifier.")
    source: str = Field(..., description="Source cluster id.")
    target: str = Field(..., description="Target cluster id.")
    type: str = Field("RELATED_TO", description="Dominant relationship type.")
    weight: int = Field(1, description="Number of original edges bundled.")
    relationship_types: list[str] = Field(
        default_factory=list,
        description="All relationship types in this bundle.",
    )
    properties: dict[str, Any] = Field(default_factory=dict)


class ClusteredGraphData(BaseModel):
    """Clustered graph data for scalable visualization."""

    nodes: list[GraphNode | ClusterNode] = Field(default_factory=list)
    edges: list[GraphEdge | ClusterEdge] = Field(default_factory=list)
    total_node_count: int = Field(0, description="Total nodes in DB.")
    total_edge_count: int = Field(0, description="Total edges in DB.")
    cluster_count: int = Field(0, description="Number of clusters generated.")
    mode: str = Field("overview", description="'overview' | 'expand' | 'neighborhood' | 'full'")
    scope_label: str | None = Field(
        None,
        description="The label currently being viewed (expand/sub-cluster). "
        "None for overview/full modes.",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional metadata: neighbor_label_counts, rel_type_counts for the current scope.",
    )


class NeighborhoodRequest(BaseModel):
    """Request for ego-graph around a specific node."""

    node_id: str = Field(..., description="Element ID of the center node.")
    depth: int = Field(1, ge=1, le=3, description="Hop depth.")
    limit: int = Field(50, ge=1, le=500, description="Max neighbors to return.")


# =====================
# Graph Stats
# =====================


class GraphStats(BaseModel):
    """Statistics about the knowledge graph for a collection."""

    collection_id: str
    node_count: int = 0
    edge_count: int = 0
    label_counts: dict[str, int] = Field(default_factory=dict)
    relationship_type_counts: dict[str, int] = Field(default_factory=dict)


class PaginatedCounts(BaseModel):
    """Paginated list of name:count pairs with search support."""

    items: list[dict[str, Any]] = Field(
        default_factory=list,
        description="List of {name, count} dicts.",
    )
    total: int = Field(0, description="Total number of items (before pagination).")
    page: int = Field(1, description="Current page number (1-based).")
    page_size: int = Field(25, description="Items per page.")
    has_next: bool = Field(False, description="Whether there is a next page.")


# =====================
# Build Pipeline
# =====================


class BuildStatus(StrEnum):
    """Status of a graph build pipeline."""

    PENDING = "pending"
    EXTRACTING = "extracting"
    BUILDING = "building"
    COMPLETED = "completed"
    FAILED = "failed"


class BuildProgress(BaseModel):
    """Progress information for a graph build pipeline."""

    collection_id: str
    status: BuildStatus = BuildStatus.PENDING
    total_chunks: int = 0
    processed_chunks: int = 0
    extracted_entities: int = 0
    extracted_relations: int = 0
    error: str | None = None

    @property
    def progress_percent(self) -> float:
        """Return progress as a percentage."""
        if self.total_chunks == 0:
            return 0.0
        return round((self.processed_chunks / self.total_chunks) * 100, 1)


# =====================
# Search / Query
# =====================


class GraphSearchQuery(BaseModel):
    """Query for searching the knowledge graph."""

    query: str = Field(..., description="Natural language query or entity name.")
    collection_id: str = Field(..., description="Collection to search within.")
    limit: int = Field(default=20, ge=1, le=100)
    search_type: str = Field(
        default="hybrid",
        description="Search type: 'entity', 'cypher', or 'hybrid'.",
    )
    vector_weight: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Weight for vector (cosine similarity) results in RRF fusion.",
    )
    graph_weight: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Weight for graph (entity traversal) results in RRF fusion.",
    )


class GraphSearchResult(BaseModel):
    """Result from a graph search."""

    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
    context: str = Field(
        default="",
        description="Formatted text context from the graph for RAG.",
    )
    score: float = Field(default=0.0, description="Relevance score.")


# =====================
# Entity Extraction
# =====================


class ExtractedEntity(BaseModel):
    """An entity extracted from text via LLM."""

    name: str
    label: str
    properties: dict[str, Any] = Field(default_factory=dict)


class ExtractedRelation(BaseModel):
    """A relation extracted from text via LLM."""

    source: str
    target: str
    type: str
    properties: dict[str, Any] = Field(default_factory=dict)


class ExtractionResult(BaseModel):
    """Result of entity/relation extraction from a document chunk."""

    chunk_id: str | None = None
    entities: list[ExtractedEntity] = Field(default_factory=list)
    relations: list[ExtractedRelation] = Field(default_factory=list)


# =====================
# API Request / Response
# =====================


class GraphBuildRequest(BaseModel):
    """Request to build a knowledge graph from a collection."""

    collection_id: str = Field(..., description="UUID of the source vector collection.")
    entity_types: list[str] | None = Field(
        default=None,
        description="Optional list of entity types to extract (e.g. ['Person', 'Organization']).",
    )
    relationship_types: list[str] | None = Field(
        default=None,
        description="Optional list of relationship types to extract.",
    )


class GraphBuildResponse(BaseModel):
    """Response for a graph build request."""

    collection_id: str
    status: BuildStatus
    message: str


class CypherQueryRequest(BaseModel):
    """Request to execute a raw Cypher query."""

    query: str = Field(..., description="Cypher query to execute.")
    collection_id: str = Field(..., description="Collection scope.")
    parameters: dict[str, Any] = Field(default_factory=dict)
