# Copyright (c) 2026 Agentic AI Platform
"""Graph response orchestration; domain DTOs remain nested in data."""

from src.graph import api_service
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
from src.shared.response_models import ResponseModel


async def build_graph(request: GraphBuildRequest, user_id: str) -> ResponseModel[GraphBuildResponse]:
    """Return the build graph result in the JSON response contract."""
    data = await api_service.build_graph(request=request, user_id=user_id)
    return ResponseModel[GraphBuildResponse](data=data)


async def get_build_status(collection_id: str, user_id: str) -> ResponseModel[BuildProgress | None]:
    """Return the get build status result in the JSON response contract."""
    data = await api_service.get_build_status(collection_id=collection_id, user_id=user_id)
    return ResponseModel[BuildProgress | None](data=data)


async def pause_build(collection_id: str, user_id: str) -> ResponseModel[GraphBuildResponse]:
    """Return the pause build result in the JSON response contract."""
    data = await api_service.pause_build(collection_id=collection_id, user_id=user_id)
    return ResponseModel[GraphBuildResponse](data=data)


async def resume_build(collection_id: str, user_id: str) -> ResponseModel[GraphBuildResponse]:
    """Return the resume build result in the JSON response contract."""
    data = await api_service.resume_build(collection_id=collection_id, user_id=user_id)
    return ResponseModel[GraphBuildResponse](data=data)


async def stop_build(collection_id: str, user_id: str) -> ResponseModel[GraphBuildResponse]:
    """Return the stop build result in the JSON response contract."""
    data = await api_service.stop_build(collection_id=collection_id, user_id=user_id)
    return ResponseModel[GraphBuildResponse](data=data)


async def list_graph_collections(user_id: str) -> ResponseModel[list[str]]:
    """Return the list graph collections result in the JSON response contract."""
    data = await api_service.list_graph_collections(user_id=user_id)
    return ResponseModel[list[str]](data=data)


async def list_nodes(
    collection_id: str, user_id: str, limit: int, offset: int, label: str | None
) -> ResponseModel[list[GraphNode]]:
    """Return the list nodes result in the JSON response contract."""
    data = await api_service.list_nodes(
        collection_id=collection_id,
        user_id=user_id,
        limit=limit,
        offset=offset,
        label=label,
    )
    return ResponseModel[list[GraphNode]](data=data)


async def list_edges(collection_id: str, user_id: str, limit: int, offset: int) -> ResponseModel[list[GraphEdge]]:
    """Return the list edges result in the JSON response contract."""
    data = await api_service.list_edges(collection_id=collection_id, user_id=user_id, limit=limit, offset=offset)
    return ResponseModel[list[GraphEdge]](data=data)


async def get_graph_data(
    collection_id: str, user_id: str, node_limit: int, edge_limit: int
) -> ResponseModel[GraphData]:
    """Return the get graph data result in the JSON response contract."""
    data = await api_service.get_graph_data(
        collection_id=collection_id,
        user_id=user_id,
        node_limit=node_limit,
        edge_limit=edge_limit,
    )
    return ResponseModel[GraphData](data=data)


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
) -> ResponseModel[ClusteredGraphData]:
    """Return the get scalable graph data result in the JSON response contract."""
    data = await api_service.get_scalable_graph_data(
        collection_id=collection_id,
        user_id=user_id,
        mode=mode,
        node_limit=node_limit,
        edge_limit=edge_limit,
        cluster_label=cluster_label,
        node_id=node_id,
        depth=depth,
    )
    return ResponseModel[ClusteredGraphData](data=data)


async def get_neighborhood(
    collection_id: str, user_id: str, node_id: str, depth: int, limit: int
) -> ResponseModel[GraphData]:
    """Return the get neighborhood result in the JSON response contract."""
    data = await api_service.get_neighborhood(
        collection_id=collection_id,
        user_id=user_id,
        node_id=node_id,
        depth=depth,
        limit=limit,
    )
    return ResponseModel[GraphData](data=data)


async def expand_cluster(
    collection_id: str, user_id: str, label: str, node_limit: int, edge_limit: int
) -> ResponseModel[GraphData]:
    """Return the expand cluster result in the JSON response contract."""
    data = await api_service.expand_cluster(
        collection_id=collection_id,
        user_id=user_id,
        label=label,
        node_limit=node_limit,
        edge_limit=edge_limit,
    )
    return ResponseModel[GraphData](data=data)


async def get_graph_stats(collection_id: str, user_id: str, scope_label: str | None) -> ResponseModel[GraphStats]:
    """Return the get graph stats result in the JSON response contract."""
    data = await api_service.get_graph_stats(collection_id=collection_id, user_id=user_id, scope_label=scope_label)
    return ResponseModel[GraphStats](data=data)


async def get_labels_paginated(
    *,
    collection_id: str,
    user_id: str,
    page: int,
    page_size: int,
    search: str | None,
    scope_label: str | None,
    rel_type_filter: str | None,
) -> ResponseModel[PaginatedCounts]:
    """Return the get labels paginated result in the JSON response contract."""
    data = await api_service.get_labels_paginated(
        collection_id=collection_id,
        user_id=user_id,
        page=page,
        page_size=page_size,
        search=search,
        scope_label=scope_label,
        rel_type_filter=rel_type_filter,
    )
    return ResponseModel[PaginatedCounts](data=data)


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
) -> ResponseModel[PaginatedCounts]:
    """Return the get relationship types paginated result in the JSON response contract."""
    data = await api_service.get_relationship_types_paginated(
        collection_id=collection_id,
        user_id=user_id,
        page=page,
        page_size=page_size,
        search=search,
        scope_label=scope_label,
        scope_skip=scope_skip,
        scope_limit=scope_limit,
        label_filter=label_filter,
    )
    return ResponseModel[PaginatedCounts](data=data)


async def search_graph(query: GraphSearchQuery, user_id: str) -> ResponseModel[GraphSearchResult]:
    """Return the search graph result in the JSON response contract."""
    data = await api_service.search_graph(query=query, user_id=user_id)
    return ResponseModel[GraphSearchResult](data=data)


async def search_entities(collection_id: str, q: str, user_id: str, limit: int) -> ResponseModel[GraphData]:
    """Return the search entities result in the JSON response contract."""
    data = await api_service.search_entities(collection_id=collection_id, q=q, user_id=user_id, limit=limit)
    return ResponseModel[GraphData](data=data)


async def search_entity_clusters(
    collection_id: str, q: str, scope_label: str | None, chunk_size: int, user_id: str
) -> ResponseModel[dict[str, int]]:
    """Return the search entity clusters result in the JSON response contract."""
    data = await api_service.search_entity_clusters(
        collection_id=collection_id,
        q=q,
        scope_label=scope_label,
        chunk_size=chunk_size,
        user_id=user_id,
    )
    return ResponseModel[dict[str, int]](data=data)


async def execute_cypher(
    request: CypherQueryRequest, user_id: str, access_token: str
) -> ResponseModel[CypherQueryResponse]:
    """Return the execute cypher result in the JSON response contract."""
    data = await api_service.execute_cypher(request=request, user_id=user_id, access_token=access_token)
    return ResponseModel[CypherQueryResponse](data=data)


async def delete_graph(collection_id: str, user_id: str) -> ResponseModel[None]:
    """Return the delete graph result in the JSON response contract."""
    await api_service.delete_graph(collection_id=collection_id, user_id=user_id)
    return ResponseModel[None](data=None)


async def graph_health() -> GraphHealthResponse:
    """Return the native graph health projection."""
    return await api_service.graph_health()
