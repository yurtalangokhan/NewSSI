# Copyright (c) 2026 Agentic AI Platform
"""Framework-free graph API orchestration over graph and collection services."""

import time
from typing import Any

from error_contract import ConflictError, DependencyUnavailableError, ForbiddenError
from localization import t

from src.collections.service import CollectionsManager
from src.documents.service import Collection
from src.graph import GraphStore
from src.graph.connection import check_neo4j_health
from src.graph.repositories.base import sanitize_neo4j_value
from src.graph.schemas import (
    BuildProgress,
    ClusteredGraphData,
    CypherQueryRequest,
    CypherQueryResponse,
    GraphBuildRequest,
    GraphBuildResponse,
    GraphData,
    GraphEdge,
    GraphHealthResponse,
    GraphNode,
    GraphSearchQuery,
    GraphSearchResult,
    GraphStats,
    PaginatedCounts,
)
from src.graph.service import (
    GraphRAGService,
    get_build_progress,
    request_pause_build,
    request_resume_build,
    request_stop_build,
    spawn_tracked,
    start_build,
)
from src.shared.authorization import get_authorization_client


async def build_graph(request: GraphBuildRequest, user_id: str) -> GraphBuildResponse:
    """Trigger knowledge graph construction from a vector collection.

    This runs in the background and returns immediately.
    Poll /graph/build/{collection_id}/status to track progress.
    """
    await Collection(request.collection_id, user_id).ensure_exists("write")
    service = GraphRAGService(
        collection_id=request.collection_id,
        user_id=user_id,
    )

    # Service owns the build-start decision: empty-collection rejection,
    # active-build detection, and pending-record registration.
    progress, already_in_progress = await start_build(
        collection_id=request.collection_id,
        user_id=user_id,
    )

    if already_in_progress:
        return GraphBuildResponse(
            collection_id=request.collection_id,
            status=progress.status,
            message=t("graph.build_already_in_progress"),
        )

    # Launch a tracked background build: a bare create_task() reference can
    # be garbage-collected mid-flight, and FastAPI's BackgroundTasks give no
    # handle to cancel in-flight builds from the app's shutdown hook.
    spawn_tracked(
        service.build_graph(
            entity_types=request.entity_types,
            relationship_types=request.relationship_types,
        )
    )

    return GraphBuildResponse(
        collection_id=request.collection_id,
        status="pending",
        message=t("graph.build_started"),
    )


async def get_build_status(collection_id: str, user_id: str) -> BuildProgress | None:
    """Get the current build progress for a collection.

    Returns ``null`` when no build has ever been started for this
    collection, so the frontend can distinguish "never built" from
    "pending".
    """
    await Collection(collection_id, user_id).ensure_exists("read")
    progress = get_build_progress(collection_id)
    if progress is None:
        return None
    return progress


async def pause_build(collection_id: str, user_id: str) -> GraphBuildResponse:
    """Pause a currently running graph build."""
    await Collection(collection_id, user_id).ensure_exists("write")
    progress = request_pause_build(collection_id)
    if progress is None:
        raise ConflictError(
            code="graph.no_running_build_pause",
            message_key="errors.rag.graph.no_running_build_pause",
        )
    return GraphBuildResponse(
        collection_id=collection_id,
        status=progress.status,
        message=t("graph.build_paused"),
    )


async def resume_build(collection_id: str, user_id: str) -> GraphBuildResponse:
    """Resume a paused graph build."""
    await Collection(collection_id, user_id).ensure_exists("write")
    progress = request_resume_build(collection_id)
    if progress is None:
        raise ConflictError(
            code="graph.no_running_build_resume",
            message_key="errors.rag.graph.no_running_build_resume",
        )
    return GraphBuildResponse(
        collection_id=collection_id,
        status=progress.status,
        message=t("graph.build_resumed"),
    )


async def stop_build(collection_id: str, user_id: str) -> GraphBuildResponse:
    """Request cancellation for a currently running graph build."""
    await Collection(collection_id, user_id).ensure_exists("write")
    progress = request_stop_build(collection_id)
    if progress is None:
        raise ConflictError(
            code="graph.no_running_build_stop",
            message_key="errors.rag.graph.no_running_build_stop",
        )
    return GraphBuildResponse(
        collection_id=collection_id,
        status=progress.status,
        message=t("graph.build_stop_requested"),
    )


async def list_graph_collections(user_id: str) -> list[str]:
    """Return the list of collection IDs that have a knowledge graph built."""
    ids = await GraphStore.list_graph_collection_ids()
    visible = {row["uuid"] for row in await CollectionsManager(user_id).list()}
    return [collection_id for collection_id in ids if collection_id in visible]


async def list_nodes(collection_id: str, user_id: str, limit: int, offset: int, label: str | None) -> list[GraphNode]:
    """List nodes in the knowledge graph for a collection."""
    await Collection(collection_id, user_id).ensure_exists("read")
    store = GraphStore(collection_id)
    nodes = await store.get_nodes(limit=limit, offset=offset, label_filter=label)
    return nodes


async def list_edges(collection_id: str, user_id: str, limit: int, offset: int) -> list[GraphEdge]:
    """List edges (relationships) in the knowledge graph for a collection."""
    await Collection(collection_id, user_id).ensure_exists("read")
    store = GraphStore(collection_id)
    edges = await store.get_edges(limit=limit, offset=offset)
    return edges


async def get_graph_data(collection_id: str, user_id: str, node_limit: int, edge_limit: int) -> GraphData:
    """Get full graph data (nodes + edges) for visualization."""
    await Collection(collection_id, user_id).ensure_exists("read")
    store = GraphStore(collection_id)
    return await store.get_graph_data(node_limit=node_limit, edge_limit=edge_limit)


async def get_scalable_graph_data(
    *,
    collection_id: str,
    user_id: str,
    mode: str,
    node_limit: int,
    edge_limit: int,
    cluster_label: str | None,
    node_id: str | None,
    depth: int,
) -> ClusteredGraphData:
    """Scalable graph visualization endpoint.

    Modes:
        - auto: Automatically choose best mode based on graph size
        - overview: Clustered supernodes for large graphs
        - expand: Drill into a cluster (requires cluster_label)
        - neighborhood: Ego graph around a node (requires node_id)
        - full: All nodes sorted by importance
    """
    await Collection(collection_id, user_id).ensure_exists("read")
    store = GraphStore(collection_id)
    return await store.get_scalable_graph_data(
        mode=mode,
        node_limit=node_limit,
        edge_limit=edge_limit,
        cluster_label=cluster_label,
        node_id=node_id,
        depth=depth,
    )


async def get_neighborhood(collection_id: str, user_id: str, node_id: str, depth: int, limit: int) -> GraphData:
    """Get ego-graph (neighborhood) around a specific node."""
    await Collection(collection_id, user_id).ensure_exists("read")
    store = GraphStore(collection_id)
    return await store.get_neighborhood(node_id=node_id, depth=depth, limit=limit)


async def expand_cluster(collection_id: str, user_id: str, label: str, node_limit: int, edge_limit: int) -> GraphData:
    """Expand a cluster to see individual nodes with the given label."""
    await Collection(collection_id, user_id).ensure_exists("read")
    store = GraphStore(collection_id)
    return await store.expand_cluster(
        cluster_label=label,
        node_limit=node_limit,
        edge_limit=edge_limit,
    )


async def get_graph_stats(collection_id: str, user_id: str, scope_label: str | None) -> GraphStats:
    """Get statistics about the knowledge graph for a collection."""
    await Collection(collection_id, user_id).ensure_exists("read")
    store = GraphStore(collection_id)
    return await store.get_stats(scope_label=scope_label)


async def get_labels_paginated(
    *,
    collection_id: str,
    user_id: str,
    page: int,
    page_size: int,
    search: str | None,
    scope_label: str | None,
    rel_type_filter: str | None,
) -> PaginatedCounts:
    """Return entity labels with counts (paginated, searchable)."""
    await Collection(collection_id, user_id).ensure_exists("read")
    store = GraphStore(collection_id)
    rel_types = [t.strip() for t in rel_type_filter.split(",") if t.strip()] if rel_type_filter else None
    return await store.get_labels_paginated(
        page=page,
        page_size=page_size,
        search=search,
        scope_label=scope_label,
        rel_type_filter=rel_types,
    )


async def get_relationship_types_paginated(
    *,
    collection_id: str,
    user_id: str,
    page: int,
    page_size: int,
    search: str | None,
    scope_label: str | None,
    scope_skip: int | None,
    scope_limit: int | None,
    label_filter: str | None,
) -> PaginatedCounts:
    """Return relationship types with counts (paginated, searchable)."""
    await Collection(collection_id, user_id).ensure_exists("read")
    store = GraphStore(collection_id)
    labels = [label.strip() for label in label_filter.split(",") if label.strip()] if label_filter else None
    return await store.get_relationship_types_paginated(
        page=page,
        page_size=page_size,
        search=search,
        scope_label=scope_label,
        scope_skip=scope_skip,
        scope_limit=scope_limit,
        label_filter=labels,
    )


async def search_graph(query: GraphSearchQuery, user_id: str) -> GraphSearchResult:
    """Hybrid search: combines vector similarity + graph traversal with RRF scoring."""
    await Collection(query.collection_id, user_id).ensure_exists("read")
    service = GraphRAGService(
        collection_id=query.collection_id,
        user_id=user_id,
    )
    return await service.hybrid_search(
        query.query,
        limit=query.limit,
        vector_weight=query.vector_weight,
        graph_weight=query.graph_weight,
        include_vector_context=query.include_vector_context,
    )


async def search_entities(collection_id: str, q: str, user_id: str, limit: int) -> GraphData:
    """Search entities by name (full-text) in the knowledge graph."""
    await Collection(collection_id, user_id).ensure_exists("read")
    store = GraphStore(collection_id)
    return await store.search_entities(q, limit=limit)


async def search_entity_clusters(
    collection_id: str, q: str, scope_label: str | None, chunk_size: int, user_id: str
) -> dict[str, int]:
    """Return ``{label: count}`` or ``{chunk_id: count}`` for clusters that contain entities matching *q*.

    This is a lightweight endpoint used by the clustered graph explorer to
    highlight matching clusters without breaking them apart.
    """
    await Collection(collection_id, user_id).ensure_exists("read")
    store = GraphStore(collection_id)
    return await store.search_entity_clusters(q, scope_label, chunk_size)


async def execute_cypher(request: CypherQueryRequest, user_id: str, access_token: str) -> CypherQueryResponse:
    """Execute raw Cypher for system or enterprise administrators only."""
    if not await get_authorization_client().is_admin(user_id, access_token):
        raise ForbiddenError(
            code="graph.cypher_admin_required",
            message_key="errors.rag.graph.cypher_admin_required",
        )
    await Collection(request.collection_id, user_id).ensure_exists("admin")
    store = GraphStore(request.collection_id)
    # read_only=True (the default): even an administrator's raw Cypher
    # cannot write or call apoc.* here, and the server-side timeout
    # bounds how long a pathological query can hold a connection.
    results = await store.execute_cypher(request.query, request.parameters)
    serializable: list[dict[str, Any]] = []
    for record in results:
        row = {key: sanitize_neo4j_value(value) for key, value in record.items()}
        serializable.append(row)
    return CypherQueryResponse(results=serializable, count=len(serializable))


async def delete_graph(collection_id: str, user_id: str) -> None:
    """Delete the entire knowledge graph for a collection."""
    await Collection(collection_id, user_id).ensure_exists("admin")
    store = GraphStore(collection_id)
    await store.delete_collection_graph()


_HEALTH_CACHE_SECONDS = 10.0
_health_cache: tuple[float, bool] | None = None


async def _cached_neo4j_health() -> bool:
    global _health_cache

    now = time.monotonic()
    if _health_cache is not None and now - _health_cache[0] < _HEALTH_CACHE_SECONDS:
        return _health_cache[1]

    healthy = await check_neo4j_health()
    _health_cache = (now, healthy)
    return healthy


async def graph_health() -> GraphHealthResponse:
    """Check Neo4j connectivity."""
    healthy = await _cached_neo4j_health()
    if not healthy:
        raise DependencyUnavailableError(
            code="graph.neo4j_unreachable",
            message_key="errors.rag.graph.neo4j_unreachable",
        )
    return GraphHealthResponse(status="ok", service="neo4j")
