"""Graph RAG API endpoints.

Provides REST API for:
  - Building knowledge graphs from vector collections.
  - Querying build progress.
  - Browsing nodes, edges, and stats.
  - Hybrid search (vector + graph).
  - Executing Cypher queries.
"""

import logging
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from i18n import t

from langconnect.auth import AuthenticatedUser, require_permission
from langconnect.database.neo4j import GraphStore
from langconnect.models.graph import (
    BuildProgress,
    ClusteredGraphData,
    CypherQueryRequest,
    GraphBuildRequest,
    GraphBuildResponse,
    GraphData,
    GraphSearchQuery,
    GraphSearchResult,
    GraphStats,
    PaginatedCounts,
)
from langconnect.services.graph_rag_service import (
    GraphRAGService,
    get_build_progress,
    request_pause_build,
    request_resume_build,
    request_stop_build,
    start_build,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/graph", tags=["graph-rag"])


# ------------------------------------------------------------------
# Build Pipeline
# ------------------------------------------------------------------


@router.post("/build", response_model=GraphBuildResponse)
async def build_graph(
    request: GraphBuildRequest,
    background_tasks: BackgroundTasks,
    user: Annotated[AuthenticatedUser, Depends(require_permission("graph:build"))],
):
    """Trigger knowledge graph construction from a vector collection.

    This runs in the background and returns immediately.
    Poll /graph/build/{collection_id}/status to track progress.
    """
    service = GraphRAGService(
        collection_id=request.collection_id,
        user_id=user.identity,
    )

    # Service owns the build-start decision: empty-collection rejection,
    # active-build detection, and pending-record registration.
    progress = await start_build(
        collection_id=request.collection_id,
        user_id=user.identity,
        entity_types=request.entity_types,
        relationship_types=request.relationship_types,
    )

    # If a build is already active, return its current status.
    if progress.status in ("pending", "extracting", "building"):
        return GraphBuildResponse(
            collection_id=request.collection_id,
            status=progress.status,
            message=t("graph.build_already_in_progress"),
        )

    # Launch background build
    background_tasks.add_task(
        service.build_graph,
        entity_types=request.entity_types,
        relationship_types=request.relationship_types,
    )

    return GraphBuildResponse(
        collection_id=request.collection_id,
        status="pending",
        message=t("graph.build_started"),
    )


@router.get("/build/{collection_id}/status", response_model=BuildProgress | None)
async def get_build_status(
    collection_id: str,
    user: Annotated[AuthenticatedUser, Depends(require_permission("graph:read"))],
):
    """Get the current build progress for a collection.

    Returns ``null`` when no build has ever been started for this
    collection, so the frontend can distinguish "never built" from
    "pending".
    """
    progress = get_build_progress(collection_id)
    if progress is None:
        return None
    return progress


@router.post("/build/{collection_id}/pause", response_model=GraphBuildResponse)
async def pause_build(
    collection_id: str,
    user: Annotated[AuthenticatedUser, Depends(require_permission("graph:build"))],
):
    """Pause a currently running graph build."""
    progress = request_pause_build(collection_id)
    if progress is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=t("graph.no_running_build_pause"),
        )
    return GraphBuildResponse(
        collection_id=collection_id,
        status=progress.status,
        message=t("graph.build_paused"),
    )


@router.post("/build/{collection_id}/resume", response_model=GraphBuildResponse)
async def resume_build(
    collection_id: str,
    user: Annotated[AuthenticatedUser, Depends(require_permission("graph:build"))],
):
    """Resume a paused graph build."""
    progress = request_resume_build(collection_id)
    if progress is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=t("graph.no_running_build_resume"),
        )
    return GraphBuildResponse(
        collection_id=collection_id,
        status=progress.status,
        message=t("graph.build_resumed"),
    )


@router.post("/build/{collection_id}/stop", response_model=GraphBuildResponse)
async def stop_build(
    collection_id: str,
    user: Annotated[AuthenticatedUser, Depends(require_permission("graph:build"))],
):
    """Request cancellation for a currently running graph build."""
    progress = request_stop_build(collection_id)
    if progress is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=t("graph.no_running_build_stop"),
        )
    return GraphBuildResponse(
        collection_id=collection_id,
        status=progress.status,
        message=t("graph.build_stop_requested"),
    )


# ------------------------------------------------------------------
# Graph Data
# ------------------------------------------------------------------


@router.get("/collections")
async def list_graph_collections(
    user: Annotated[AuthenticatedUser, Depends(require_permission("graph:read"))],
):
    """Return the list of collection IDs that have a knowledge graph built."""
    ids = await GraphStore.list_graph_collection_ids()
    return ids


@router.get("/collections/{collection_id}/nodes")
async def list_nodes(
    collection_id: str,
    user: Annotated[AuthenticatedUser, Depends(require_permission("graph:read"))],
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    label: str | None = Query(None),
):
    """List nodes in the knowledge graph for a collection."""
    store = GraphStore(collection_id)
    nodes = await store.get_nodes(limit=limit, offset=offset, label_filter=label)
    return nodes


@router.get("/collections/{collection_id}/edges")
async def list_edges(
    collection_id: str,
    user: Annotated[AuthenticatedUser, Depends(require_permission("graph:read"))],
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    """List edges (relationships) in the knowledge graph for a collection."""
    store = GraphStore(collection_id)
    edges = await store.get_edges(limit=limit, offset=offset)
    return edges


@router.get("/collections/{collection_id}/data", response_model=GraphData)
async def get_graph_data(
    collection_id: str,
    user: Annotated[AuthenticatedUser, Depends(require_permission("graph:read"))],
    node_limit: int = Query(200, ge=1, le=1000),
    edge_limit: int = Query(500, ge=1, le=2000),
):
    """Get full graph data (nodes + edges) for visualization."""
    store = GraphStore(collection_id)
    return await store.get_graph_data(node_limit=node_limit, edge_limit=edge_limit)


# ------------------------------------------------------------------
# Scalable Visualization Endpoints
# ------------------------------------------------------------------


@router.get(
    "/collections/{collection_id}/data/scalable",
    response_model=ClusteredGraphData,
)
async def get_scalable_graph_data(
    collection_id: str,
    user: Annotated[AuthenticatedUser, Depends(require_permission("graph:read"))],
    mode: str = Query("auto", regex="^(auto|overview|expand|neighborhood|full)$"),
    node_limit: int = Query(500, ge=1, le=5000),
    edge_limit: int = Query(1000, ge=1, le=10000),
    cluster_label: str | None = Query(None),
    node_id: str | None = Query(None),
    depth: int = Query(1, ge=1, le=3),
):
    """Scalable graph visualization endpoint.

    Modes:
        - auto: Automatically choose best mode based on graph size
        - overview: Clustered supernodes for large graphs
        - expand: Drill into a cluster (requires cluster_label)
        - neighborhood: Ego graph around a node (requires node_id)
        - full: All nodes sorted by importance
    """
    store = GraphStore(collection_id)
    return await store.get_scalable_graph_data(
        mode=mode,
        node_limit=node_limit,
        edge_limit=edge_limit,
        cluster_label=cluster_label,
        node_id=node_id,
        depth=depth,
    )


@router.get(
    "/collections/{collection_id}/neighborhood",
    response_model=GraphData,
)
async def get_neighborhood(
    collection_id: str,
    user: Annotated[AuthenticatedUser, Depends(require_permission("graph:read"))],
    node_id: str = Query(...),
    depth: int = Query(1, ge=1, le=3),
    limit: int = Query(50, ge=1, le=500),
):
    """Get ego-graph (neighborhood) around a specific node."""
    store = GraphStore(collection_id)
    return await store.get_neighborhood(node_id=node_id, depth=depth, limit=limit)


@router.get(
    "/collections/{collection_id}/expand",
    response_model=GraphData,
)
async def expand_cluster(
    collection_id: str,
    user: Annotated[AuthenticatedUser, Depends(require_permission("graph:read"))],
    label: str = Query(...),
    node_limit: int = Query(200, ge=1, le=1000),
    edge_limit: int = Query(500, ge=1, le=2000),
):
    """Expand a cluster to see individual nodes with the given label."""
    store = GraphStore(collection_id)
    return await store.expand_cluster(
        cluster_label=label,
        node_limit=node_limit,
        edge_limit=edge_limit,
    )


@router.get("/collections/{collection_id}/stats", response_model=GraphStats)
async def get_graph_stats(
    collection_id: str,
    user: Annotated[AuthenticatedUser, Depends(require_permission("graph:read"))],
    scope_label: str | None = Query(
        None,
        description="Scope stats to this label group",
    ),
):
    """Get statistics about the knowledge graph for a collection."""
    store = GraphStore(collection_id)
    return await store.get_stats(scope_label=scope_label)


@router.get(
    "/collections/{collection_id}/stats/labels",
    response_model=PaginatedCounts,
)
async def get_labels_paginated(
    collection_id: str,
    user: Annotated[AuthenticatedUser, Depends(require_permission("graph:read"))],
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    search: str | None = Query(None),
    scope_label: str | None = Query(
        None, description="Scope to neighbour labels of this label group"
    ),
    rel_type_filter: str | None = Query(
        None,
        description="Comma-separated relationship types to cross-filter labels by",
    ),
):
    """Return entity labels with counts (paginated, searchable)."""
    store = GraphStore(collection_id)
    rel_types = (
        [t.strip() for t in rel_type_filter.split(",") if t.strip()]
        if rel_type_filter
        else None
    )
    return await store.get_labels_paginated(
        page=page,
        page_size=page_size,
        search=search,
        scope_label=scope_label,
        rel_type_filter=rel_types,
    )


@router.get(
    "/collections/{collection_id}/stats/relationship-types",
    response_model=PaginatedCounts,
)
async def get_relationship_types_paginated(
    collection_id: str,
    user: Annotated[AuthenticatedUser, Depends(require_permission("graph:read"))],
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    search: str | None = Query(None),
    scope_label: str | None = Query(
        None,
        description="Scope to relationships involving this label group",
    ),
    scope_skip: int | None = Query(
        None,
        description="Chunk offset — scopes counts to a node slice within the label",
    ),
    scope_limit: int | None = Query(
        None,
        description="Chunk size — scopes counts to a node slice within the label",
    ),
    label_filter: str | None = Query(
        None,
        description="Comma-separated entity labels to cross-filter relationship types by",
    ),
):
    """Return relationship types with counts (paginated, searchable)."""
    store = GraphStore(collection_id)
    labels = (
        [label.strip() for label in label_filter.split(",") if label.strip()]
        if label_filter
        else None
    )
    return await store.get_relationship_types_paginated(
        page=page,
        page_size=page_size,
        search=search,
        scope_label=scope_label,
        scope_skip=scope_skip,
        scope_limit=scope_limit,
        label_filter=labels,
    )


# ------------------------------------------------------------------
# Search
# ------------------------------------------------------------------


@router.post("/search", response_model=GraphSearchResult)
async def search_graph(
    query: GraphSearchQuery,
    user: Annotated[AuthenticatedUser, Depends(require_permission("graph:search"))],
):
    """Hybrid search: combines vector similarity + graph traversal with RRF scoring."""
    service = GraphRAGService(
        collection_id=query.collection_id,
        user_id=user.identity,
    )
    return await service.hybrid_search(
        query.query,
        limit=query.limit,
        vector_weight=query.vector_weight,
        graph_weight=query.graph_weight,
        include_vector_context=query.include_vector_context,
    )


@router.get("/collections/{collection_id}/search/entities")
async def search_entities(
    collection_id: str,
    q: str = Query(..., min_length=1),
    user: Annotated[
        AuthenticatedUser, Depends(require_permission("graph:search"))
    ] = None,
    limit: int = Query(10, ge=1, le=100),
):
    """Search entities by name (full-text) in the knowledge graph."""
    store = GraphStore(collection_id)
    return await store.search_entities(q, limit=limit)


@router.get("/collections/{collection_id}/search/entity-clusters")
async def search_entity_clusters(
    collection_id: str,
    q: str = Query(..., min_length=1),
    scope_label: str | None = Query(
        None, description="If provided, returns counts for offset-based subclusters"
    ),
    chunk_size: int = Query(
        200,
        description="Chunk size for subclusters (should match node_limit of expand)",
    ),
    user: Annotated[
        AuthenticatedUser, Depends(require_permission("graph:search"))
    ] = None,
):
    """Return ``{label: count}`` or ``{chunk_id: count}`` for clusters that contain entities matching *q*.

    This is a lightweight endpoint used by the clustered graph explorer to
    highlight matching clusters without breaking them apart.
    """
    store = GraphStore(collection_id)
    return await store.search_entity_clusters(q, scope_label, chunk_size)


# ------------------------------------------------------------------
# Cypher
# ------------------------------------------------------------------


@router.post("/cypher")
async def execute_cypher(
    request: CypherQueryRequest,
    user: Annotated[AuthenticatedUser, Depends(require_permission("graph:search"))],
):
    """Execute a Cypher query scoped to a collection (read-only recommended)."""
    store = GraphStore(request.collection_id)
    try:
        results = await store.execute_cypher(request.query, request.parameters)
        # Convert Neo4j types to JSON-serializable format
        serializable: list[dict[str, Any]] = []
        for record in results:
            row: dict[str, Any] = {}
            for key, value in record.items():
                row[key] = _serialize_neo4j_value(value)
            serializable.append(row)
        return {"results": serializable, "count": len(serializable)}
    except Exception as exc:
        logger.exception("Cypher query failed")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=t("graph.cypher_query_error", error=str(exc)),
        )


# ------------------------------------------------------------------
# Delete
# ------------------------------------------------------------------


@router.delete("/collections/{collection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_graph(
    collection_id: str,
    user: Annotated[AuthenticatedUser, Depends(require_permission("graph:delete"))],
):
    """Delete the entire knowledge graph for a collection."""
    store = GraphStore(collection_id)
    await store.delete_collection_graph()


# ------------------------------------------------------------------
# Health
# ------------------------------------------------------------------


@router.get("/health")
async def graph_health():
    """Check Neo4j connectivity."""
    from langconnect.database.neo4j.connection import check_neo4j_health

    healthy = await check_neo4j_health()
    if not healthy:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=t("graph.neo4j_unreachable"),
        )
    return {"status": "ok", "service": "neo4j"}


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _serialize_neo4j_value(value: Any) -> Any:
    """Convert Neo4j-specific types to JSON-serializable Python types."""
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [_serialize_neo4j_value(v) for v in value]
    if isinstance(value, dict):
        return {k: _serialize_neo4j_value(v) for k, v in value.items()}
    # Fallback
    return str(value)
