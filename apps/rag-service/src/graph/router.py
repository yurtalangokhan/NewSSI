# Copyright (c) 2026 Agentic AI Platform
"""Graph JSON transport and permission boundaries."""

from typing import Annotated

from error_contract import ApplicationError, render_error_message
from fastapi import APIRouter, Depends, Query, Request, Response

from src.graph import controller
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
from src.shared.auth import AuthenticatedUser, require_permission
from src.shared.response_errors import request_locale, set_error_response
from src.shared.response_models import ErrorModel, ResponseModel

router = APIRouter(prefix="/graph", tags=["graph-rag"])


def _error_response(error: ApplicationError, response: Response, request: Request) -> ResponseModel:
    set_error_response(response, error, request)
    message = render_error_message(error, locale=request_locale(request))
    return ResponseModel(
        statusCode=error.status_code,
        message=message,
        error=ErrorModel.from_error(error, message),
    )


@router.post("/build", response_model=ResponseModel[GraphBuildResponse])
async def build_graph(
    *,
    response: Response,
    body: GraphBuildRequest,
    request: Request,
    user: Annotated[AuthenticatedUser, Depends(require_permission("graph:build"))],
):
    """Trigger knowledge graph construction from a vector collection.

    This runs in the background and returns immediately.
    Poll /graph/build/{collection_id}/status to track progress.
    """
    try:
        return await controller.build_graph(request=body, user_id=user.identity)
    except ApplicationError as error:
        return _error_response(error, response, request)


@router.get("/build/{collection_id}/status", response_model=ResponseModel[BuildProgress | None])
async def get_build_status(
    *,
    response: Response,
    request: Request,
    collection_id: str,
    user: Annotated[AuthenticatedUser, Depends(require_permission("graph:read"))],
):
    """Get the current build progress for a collection.

    Returns ``data=null`` when no build has ever been started for this
    collection, so the frontend can distinguish "never built" from
    "pending".
    """
    try:
        return await controller.get_build_status(collection_id=collection_id, user_id=user.identity)
    except ApplicationError as error:
        return _error_response(error, response, request)


@router.post("/build/{collection_id}/pause", response_model=ResponseModel[GraphBuildResponse])
async def pause_build(
    *,
    response: Response,
    request: Request,
    collection_id: str,
    user: Annotated[AuthenticatedUser, Depends(require_permission("graph:build"))],
):
    """Pause a currently running graph build."""
    try:
        return await controller.pause_build(collection_id=collection_id, user_id=user.identity)
    except ApplicationError as error:
        return _error_response(error, response, request)


@router.post("/build/{collection_id}/resume", response_model=ResponseModel[GraphBuildResponse])
async def resume_build(
    *,
    response: Response,
    request: Request,
    collection_id: str,
    user: Annotated[AuthenticatedUser, Depends(require_permission("graph:build"))],
):
    """Resume a paused graph build."""
    try:
        return await controller.resume_build(collection_id=collection_id, user_id=user.identity)
    except ApplicationError as error:
        return _error_response(error, response, request)


@router.post("/build/{collection_id}/stop", response_model=ResponseModel[GraphBuildResponse])
async def stop_build(
    *,
    response: Response,
    request: Request,
    collection_id: str,
    user: Annotated[AuthenticatedUser, Depends(require_permission("graph:build"))],
):
    """Request cancellation for a currently running graph build."""
    try:
        return await controller.stop_build(collection_id=collection_id, user_id=user.identity)
    except ApplicationError as error:
        return _error_response(error, response, request)


@router.get("/collections", response_model=ResponseModel[list[str]])
async def list_graph_collections(
    *,
    response: Response,
    request: Request,
    user: Annotated[AuthenticatedUser, Depends(require_permission("graph:read"))],
):
    """Return the list of collection IDs that have a knowledge graph built."""
    try:
        return await controller.list_graph_collections(user_id=user.identity)
    except ApplicationError as error:
        return _error_response(error, response, request)


@router.get("/collections/{collection_id}/nodes", response_model=ResponseModel[list[GraphNode]])
async def list_nodes(
    *,
    response: Response,
    request: Request,
    collection_id: str,
    user: Annotated[AuthenticatedUser, Depends(require_permission("graph:read"))],
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
    label: Annotated[str | None, Query()] = None,
):
    """List nodes in the knowledge graph for a collection."""
    try:
        return await controller.list_nodes(
            collection_id=collection_id,
            user_id=user.identity,
            limit=limit,
            offset=offset,
            label=label,
        )
    except ApplicationError as error:
        return _error_response(error, response, request)


@router.get("/collections/{collection_id}/edges", response_model=ResponseModel[list[GraphEdge]])
async def list_edges(
    *,
    response: Response,
    request: Request,
    collection_id: str,
    user: Annotated[AuthenticatedUser, Depends(require_permission("graph:read"))],
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    """List edges (relationships) in the knowledge graph for a collection."""
    try:
        return await controller.list_edges(
            collection_id=collection_id,
            user_id=user.identity,
            limit=limit,
            offset=offset,
        )
    except ApplicationError as error:
        return _error_response(error, response, request)


@router.get("/collections/{collection_id}/data", response_model=ResponseModel[GraphData])
async def get_graph_data(
    *,
    response: Response,
    request: Request,
    collection_id: str,
    user: Annotated[AuthenticatedUser, Depends(require_permission("graph:read"))],
    node_limit: Annotated[int, Query(ge=1, le=1000)] = 200,
    edge_limit: Annotated[int, Query(ge=1, le=2000)] = 500,
):
    """Get full graph data (nodes + edges) for visualization."""
    try:
        return await controller.get_graph_data(
            collection_id=collection_id,
            user_id=user.identity,
            node_limit=node_limit,
            edge_limit=edge_limit,
        )
    except ApplicationError as error:
        return _error_response(error, response, request)


@router.get(
    "/collections/{collection_id}/data/scalable",
    response_model=ResponseModel[ClusteredGraphData],
)
async def get_scalable_graph_data(
    *,
    response: Response,
    request: Request,
    collection_id: str,
    user: Annotated[AuthenticatedUser, Depends(require_permission("graph:read"))],
    mode: Annotated[str, Query(regex="^(auto|overview|expand|neighborhood|full)$")] = "auto",
    node_limit: Annotated[int, Query(ge=1, le=5000)] = 500,
    edge_limit: Annotated[int, Query(ge=1, le=10000)] = 1000,
    cluster_label: Annotated[str | None, Query()] = None,
    node_id: Annotated[str | None, Query()] = None,
    depth: Annotated[int, Query(ge=1, le=3)] = 1,
):
    """Scalable graph visualization endpoint.

    Modes:
        - auto: Automatically choose best mode based on graph size
        - overview: Clustered supernodes for large graphs
        - expand: Drill into a cluster (requires cluster_label)
        - neighborhood: Ego graph around a node (requires node_id)
        - full: All nodes sorted by importance
    """
    try:
        return await controller.get_scalable_graph_data(
            collection_id=collection_id,
            user_id=user.identity,
            mode=mode,
            node_limit=node_limit,
            edge_limit=edge_limit,
            cluster_label=cluster_label,
            node_id=node_id,
            depth=depth,
        )
    except ApplicationError as error:
        return _error_response(error, response, request)


@router.get("/collections/{collection_id}/neighborhood", response_model=ResponseModel[GraphData])
async def get_neighborhood(
    *,
    response: Response,
    request: Request,
    collection_id: str,
    user: Annotated[AuthenticatedUser, Depends(require_permission("graph:read"))],
    node_id: Annotated[str, Query()] = ...,
    depth: Annotated[int, Query(ge=1, le=3)] = 1,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
):
    """Get ego-graph (neighborhood) around a specific node."""
    try:
        return await controller.get_neighborhood(
            collection_id=collection_id,
            user_id=user.identity,
            node_id=node_id,
            depth=depth,
            limit=limit,
        )
    except ApplicationError as error:
        return _error_response(error, response, request)


@router.get("/collections/{collection_id}/expand", response_model=ResponseModel[GraphData])
async def expand_cluster(
    *,
    response: Response,
    request: Request,
    collection_id: str,
    user: Annotated[AuthenticatedUser, Depends(require_permission("graph:read"))],
    label: Annotated[str, Query()] = ...,
    node_limit: Annotated[int, Query(ge=1, le=1000)] = 200,
    edge_limit: Annotated[int, Query(ge=1, le=2000)] = 500,
):
    """Expand a cluster to see individual nodes with the given label."""
    try:
        return await controller.expand_cluster(
            collection_id=collection_id,
            user_id=user.identity,
            label=label,
            node_limit=node_limit,
            edge_limit=edge_limit,
        )
    except ApplicationError as error:
        return _error_response(error, response, request)


@router.get("/collections/{collection_id}/stats", response_model=ResponseModel[GraphStats])
async def get_graph_stats(
    *,
    response: Response,
    request: Request,
    collection_id: str,
    user: Annotated[AuthenticatedUser, Depends(require_permission("graph:read"))],
    scope_label: Annotated[str | None, Query(description="Scope stats to this label group")] = None,
):
    """Get statistics about the knowledge graph for a collection."""
    try:
        return await controller.get_graph_stats(
            collection_id=collection_id, user_id=user.identity, scope_label=scope_label
        )
    except ApplicationError as error:
        return _error_response(error, response, request)


@router.get(
    "/collections/{collection_id}/stats/labels",
    response_model=ResponseModel[PaginatedCounts],
)
async def get_labels_paginated(
    *,
    response: Response,
    request: Request,
    collection_id: str,
    user: Annotated[AuthenticatedUser, Depends(require_permission("graph:read"))],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
    search: Annotated[str | None, Query()] = None,
    scope_label: Annotated[str | None, Query(description="Scope to neighbour labels of this label group")] = None,
    rel_type_filter: Annotated[
        str | None, Query(description="Comma-separated relationship types to cross-filter labels by")
    ] = None,
):
    """Return entity labels with counts (paginated, searchable)."""
    try:
        return await controller.get_labels_paginated(
            collection_id=collection_id,
            user_id=user.identity,
            page=page,
            page_size=page_size,
            search=search,
            scope_label=scope_label,
            rel_type_filter=rel_type_filter,
        )
    except ApplicationError as error:
        return _error_response(error, response, request)


@router.get(
    "/collections/{collection_id}/stats/relationship-types",
    response_model=ResponseModel[PaginatedCounts],
)
async def get_relationship_types_paginated(
    *,
    response: Response,
    request: Request,
    collection_id: str,
    user: Annotated[AuthenticatedUser, Depends(require_permission("graph:read"))],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
    search: Annotated[str | None, Query()] = None,
    scope_label: Annotated[str | None, Query(description="Scope to relationships involving this label group")] = None,
    scope_skip: Annotated[
        int | None, Query(ge=0, description="Chunk offset — scopes counts to a node slice within the label")
    ] = None,
    scope_limit: Annotated[
        int | None, Query(ge=1, le=10_000, description="Chunk size — scopes counts to a node slice within the label")
    ] = None,
    label_filter: Annotated[
        str | None, Query(description="Comma-separated entity labels to cross-filter relationship types by")
    ] = None,
):
    """Return relationship types with counts (paginated, searchable)."""
    try:
        return await controller.get_relationship_types_paginated(
            collection_id=collection_id,
            user_id=user.identity,
            page=page,
            page_size=page_size,
            search=search,
            scope_label=scope_label,
            scope_skip=scope_skip,
            scope_limit=scope_limit,
            label_filter=label_filter,
        )
    except ApplicationError as error:
        return _error_response(error, response, request)


@router.post("/search", response_model=ResponseModel[GraphSearchResult])
async def search_graph(
    *,
    response: Response,
    request: Request,
    query: GraphSearchQuery,
    user: Annotated[AuthenticatedUser, Depends(require_permission("graph:search"))],
):
    """Hybrid search: combines vector similarity + graph traversal with RRF scoring."""
    try:
        return await controller.search_graph(query=query, user_id=user.identity)
    except ApplicationError as error:
        return _error_response(error, response, request)


@router.get(
    "/collections/{collection_id}/search/entities",
    response_model=ResponseModel[GraphData],
)
async def search_entities(
    *,
    response: Response,
    request: Request,
    collection_id: str,
    q: Annotated[str, Query(min_length=1)] = ...,
    user: Annotated[AuthenticatedUser, Depends(require_permission("graph:search"))] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
):
    """Search entities by name (full-text) in the knowledge graph."""
    try:
        return await controller.search_entities(collection_id=collection_id, q=q, user_id=user.identity, limit=limit)
    except ApplicationError as error:
        return _error_response(error, response, request)


@router.get(
    "/collections/{collection_id}/search/entity-clusters",
    response_model=ResponseModel[dict[str, int]],
)
async def search_entity_clusters(
    *,
    response: Response,
    request: Request,
    collection_id: str,
    q: Annotated[str, Query(min_length=1)] = ...,
    scope_label: Annotated[
        str | None, Query(description="If provided, returns counts for offset-based subclusters")
    ] = None,
    chunk_size: Annotated[
        int, Query(ge=1, le=10_000, description="Chunk size for subclusters (should match node_limit of expand)")
    ] = 200,
    user: Annotated[AuthenticatedUser, Depends(require_permission("graph:search"))] = None,
):
    """Return ``{label: count}`` or ``{chunk_id: count}`` for clusters that contain entities matching *q*.

    This is a lightweight endpoint used by the clustered graph explorer to
    highlight matching clusters without breaking them apart.
    """
    try:
        return await controller.search_entity_clusters(
            collection_id=collection_id,
            q=q,
            scope_label=scope_label,
            chunk_size=chunk_size,
            user_id=user.identity,
        )
    except ApplicationError as error:
        return _error_response(error, response, request)


@router.post("/cypher", response_model=ResponseModel[CypherQueryResponse])
async def execute_cypher(
    *,
    response: Response,
    body: CypherQueryRequest,
    request: Request,
    user: Annotated[AuthenticatedUser, Depends(require_permission("graph:search"))],
):
    """Execute raw Cypher for system or enterprise administrators only."""
    try:
        return await controller.execute_cypher(request=body, user_id=user.identity, access_token=user.access_token)
    except ApplicationError as error:
        return _error_response(error, response, request)


@router.delete("/collections/{collection_id}", response_model=ResponseModel[None])
async def delete_graph(
    *,
    response: Response,
    request: Request,
    collection_id: str,
    user: Annotated[AuthenticatedUser, Depends(require_permission("graph:delete"))],
):
    """Delete the entire knowledge graph for a collection."""
    try:
        return await controller.delete_graph(collection_id=collection_id, user_id=user.identity)
    except ApplicationError as error:
        return _error_response(error, response, request)


@router.get("/health", response_model=GraphHealthResponse)
async def graph_health():
    """Check Neo4j connectivity using the existing health payload."""
    return await controller.graph_health()
