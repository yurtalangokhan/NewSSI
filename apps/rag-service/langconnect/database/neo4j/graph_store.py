"""GraphStore — high-level facade delegating to domain repositories.

Consumers (``api/graph.py``, ``services/graph_rag_service.py``, etc.)
use this single entry-point while the actual work is handled by the
underlying domain-specific repositories.  For fine-grained access,
import the repositories directly from ``langconnect.database.neo4j.repositories``.
"""

from __future__ import annotations

import logging
from typing import Any

from langconnect.database.neo4j.repositories.entity_repository import EntityRepository
from langconnect.database.neo4j.repositories.search_repository import SearchRepository
from langconnect.database.neo4j.repositories.stats_repository import StatsRepository
from langconnect.database.neo4j.repositories.visualization_repository import (
    VisualizationRepository,
)
from langconnect.models.graph import (
    ClusteredGraphData,
    GraphData,
    GraphEdge,
    GraphNode,
    GraphStats,
    PaginatedCounts,
)

logger = logging.getLogger(__name__)


class GraphStore:
    """High-level facade for knowledge-graph operations.

    Instantiated per-collection; delegates to ``EntityRepository``,
    ``SearchRepository``, ``StatsRepository`` and
    ``VisualizationRepository`` internally.
    """

    def __init__(self, collection_id: str) -> None:
        self.collection_id = collection_id
        self._entity = EntityRepository(collection_id)
        self._search = SearchRepository(collection_id)
        self._stats = StatsRepository(collection_id)
        self._viz = VisualizationRepository(collection_id)

    # ------------------------------------------------------------------
    # Index management
    # ------------------------------------------------------------------

    async def ensure_indexes(self) -> None:
        await self._entity.ensure_indexes()

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    async def upsert_node(
        self,
        name: str,
        label: str,
        properties: dict[str, Any] | None = None,
    ) -> str:
        return await self._entity.upsert_node(name, label, properties)

    async def upsert_edge(
        self,
        source_name: str,
        target_name: str,
        rel_type: str,
        properties: dict[str, Any] | None = None,
    ) -> str:
        return await self._entity.upsert_edge(
            source_name, target_name, rel_type, properties
        )

    async def bulk_upsert(
        self,
        entities: list[dict[str, Any]],
        relations: list[dict[str, Any]],
    ) -> dict[str, int]:
        return await self._entity.bulk_upsert(entities, relations)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def get_nodes(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        label_filter: str | None = None,
    ) -> list[GraphNode]:
        return await self._entity.get_nodes(
            limit=limit, offset=offset, label_filter=label_filter
        )

    async def get_edges(
        self,
        *,
        limit: int = 200,
        offset: int = 0,
    ) -> list[GraphEdge]:
        return await self._entity.get_edges(limit=limit, offset=offset)

    async def get_graph_data(
        self,
        *,
        node_limit: int = 200,
        edge_limit: int = 500,
    ) -> GraphData:
        return await self._entity.get_graph_data(
            node_limit=node_limit, edge_limit=edge_limit
        )

    # ------------------------------------------------------------------
    # Scalable Visualization
    # ------------------------------------------------------------------

    async def get_graph_overview(
        self,
        *,
        max_clusters: int = 200,
        top_entities_per_cluster: int = 5,
    ) -> ClusteredGraphData:
        return await self._viz.get_graph_overview(
            max_clusters=max_clusters,
            top_entities_per_cluster=top_entities_per_cluster,
        )

    async def get_graph_overview_with_edges(
        self,
        *,
        max_clusters: int = 200,
        top_entities_per_cluster: int = 5,
    ) -> ClusteredGraphData:
        return await self._viz.get_graph_overview_with_edges(
            max_clusters=max_clusters,
            top_entities_per_cluster=top_entities_per_cluster,
        )

    async def expand_cluster(
        self,
        cluster_label: str,
        *,
        node_limit: int = 200,
        edge_limit: int = 500,
    ) -> GraphData:
        return await self._viz.expand_cluster(
            cluster_label, node_limit=node_limit, edge_limit=edge_limit
        )

    async def get_neighborhood(
        self,
        node_id: str,
        *,
        depth: int = 1,
        limit: int = 50,
    ) -> GraphData:
        return await self._viz.get_neighborhood(
            node_id, depth=depth, limit=limit
        )

    async def get_important_nodes(self, *, limit: int = 200) -> list[GraphNode]:
        return await self._viz.get_important_nodes(limit=limit)

    async def get_scalable_graph_data(
        self,
        *,
        mode: str = "auto",
        node_limit: int = 500,
        edge_limit: int = 1000,
        cluster_label: str | None = None,
        node_id: str | None = None,
        depth: int = 1,
    ) -> ClusteredGraphData:
        return await self._viz.get_scalable_graph_data(
            mode=mode,
            node_limit=node_limit,
            edge_limit=edge_limit,
            cluster_label=cluster_label,
            node_id=node_id,
            depth=depth,
        )

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    @staticmethod
    async def list_graph_collection_ids() -> list[str]:
        return await StatsRepository.list_graph_collection_ids()

    async def get_stats(self, *, scope_label: str | None = None) -> GraphStats:
        return await self._stats.get_stats(scope_label=scope_label)

    async def get_labels_paginated(
        self,
        *,
        page: int = 1,
        page_size: int = 25,
        search: str | None = None,
        scope_label: str | None = None,
        rel_type_filter: list[str] | None = None,
    ) -> PaginatedCounts:
        return await self._stats.get_labels_paginated(
            page=page,
            page_size=page_size,
            search=search,
            scope_label=scope_label,
            rel_type_filter=rel_type_filter,
        )

    async def get_relationship_types_paginated(
        self,
        *,
        page: int = 1,
        page_size: int = 25,
        search: str | None = None,
        scope_label: str | None = None,
        scope_skip: int | None = None,
        scope_limit: int | None = None,
        label_filter: list[str] | None = None,
    ) -> PaginatedCounts:
        return await self._stats.get_relationship_types_paginated(
            page=page,
            page_size=page_size,
            search=search,
            scope_label=scope_label,
            scope_skip=scope_skip,
            scope_limit=scope_limit,
            label_filter=label_filter,
        )

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    async def search_entities_bm25(
        self,
        query: str,
        *,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        return await self._search.search_entities_bm25(query, limit=limit)

    async def fetch_edges_for_nodes(
        self,
        node_names: list[str],
        *,
        limit: int = 100,
    ) -> list[GraphEdge]:
        return await self._search.fetch_edges_for_nodes(node_names, limit=limit)

    async def search_entities(
        self,
        query: str,
        *,
        limit: int = 10,
    ) -> GraphData:
        return await self._search.search_entities(query, limit=limit)

    async def search_entity_clusters(
        self, query: str, scope_label: str | None = None, chunk_size: int = 200
    ) -> dict[str, int]:
        return await self._search.search_entity_clusters(query, scope_label, chunk_size)

    async def get_entity_context(
        self,
        entity_names: list[str],
        *,
        depth: int = 1,
    ) -> str:
        return await self._search.get_entity_context(entity_names, depth=depth)

    async def get_entity_context_focused(
        self,
        entity_names: list[str],
        *,
        max_direct: int = 30,
        max_indirect: int = 20,
    ) -> str:
        return await self._search.get_entity_context_focused(
            entity_names, max_direct=max_direct, max_indirect=max_indirect
        )

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    async def delete_collection_graph(self) -> int:
        return await self._entity.delete_collection_graph()

    # ------------------------------------------------------------------
    # Arbitrary Cypher
    # ------------------------------------------------------------------

    async def execute_cypher(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        return await self._entity.execute_cypher(query, parameters)
