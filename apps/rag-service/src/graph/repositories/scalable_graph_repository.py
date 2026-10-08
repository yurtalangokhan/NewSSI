"""Repository — Unified scalable graph endpoint (mode dispatch).

``get_scalable_graph_data`` is the single entry point ``graph_store.py``'s
callers use for "give me a renderable slice of this graph, at whatever
size" — it decides, from the graph's size and the caller's requested mode,
whether that means a clustered overview (``ClusterRepository``), a drill
into one cluster or a node's neighbourhood (``ExpansionRepository``), or a
flat importance-sorted view of everything. This class owns that decision
and the combining logic around it; the two repositories it composes each
own a single raw Neo4j query concern and know nothing about the others.
"""

from __future__ import annotations

from src.graph.queries.visualization import EDGES_BETWEEN_IDS_FULL
from src.graph.repositories.base import Neo4jRepository
from src.graph.repositories.cluster_repository import (
    ClusterRepository,
)
from src.graph.repositories.expansion_repository import (
    ExpansionRepository,
)
from src.graph.repositories.stats_repository import StatsRepository
from src.graph.schemas import ClusteredGraphData, GraphEdge, GraphStats
from src.shared.observability import get_logger

logger = get_logger(__name__)


class ScalableGraphRepository(Neo4jRepository):
    """Scalable graph visualisation: clustering, drill-down, neighbourhood."""

    def __init__(self, collection_id: str) -> None:
        super().__init__(collection_id)
        self._cluster = ClusterRepository(collection_id)
        self._expansion = ExpansionRepository(collection_id)
        self._stats_repo = StatsRepository(collection_id)

    # ------------------------------------------------------------------
    # Thin pass-throughs — graph_store.py's public contract
    # ------------------------------------------------------------------

    async def get_graph_overview(
        self,
        *,
        max_clusters: int = 200,
        top_entities_per_cluster: int = 5,
    ) -> ClusteredGraphData:
        return await self._cluster.get_graph_overview(
            max_clusters=max_clusters,
            top_entities_per_cluster=top_entities_per_cluster,
        )

    async def get_graph_overview_with_edges(
        self,
        *,
        max_clusters: int = 200,
        top_entities_per_cluster: int = 5,
    ) -> ClusteredGraphData:
        return await self._cluster.get_graph_overview_with_edges(
            max_clusters=max_clusters,
            top_entities_per_cluster=top_entities_per_cluster,
        )

    async def expand_cluster(
        self,
        cluster_label: str,
        *,
        node_limit: int = 200,
        edge_limit: int = 500,
    ):
        return await self._expansion.expand_cluster(cluster_label, node_limit=node_limit, edge_limit=edge_limit)

    async def get_neighborhood(
        self,
        node_id: str,
        *,
        depth: int = 1,
        limit: int = 50,
    ):
        return await self._expansion.get_neighborhood(node_id, depth=depth, limit=limit)

    async def get_important_nodes(self, *, limit: int = 200):
        return await self._expansion.get_important_nodes(limit=limit)

    # ------------------------------------------------------------------
    # Unified scalable endpoint (mode dispatch)
    # ------------------------------------------------------------------

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
        """Unified scalable graph endpoint (auto/overview/expand/neighborhood/full)."""
        stats = await self._stats_repo.get_stats()

        if mode == "auto":
            mode = "full" if stats.node_count <= node_limit else "overview"

        if mode == "overview":
            return await self._cluster.get_graph_overview_with_edges(max_clusters=node_limit)

        if mode == "expand" and cluster_label:
            return await self._handle_expand(
                cluster_label,
                node_limit=node_limit,
                edge_limit=edge_limit,
                stats=stats,
            )

        if mode == "neighborhood" and node_id:
            data = await self._expansion.get_neighborhood(node_id, depth=depth, limit=node_limit)
            return ClusteredGraphData(
                nodes=data.nodes,
                edges=data.edges,
                total_node_count=stats.node_count,
                total_edge_count=stats.edge_count,
                cluster_count=0,
                mode="neighborhood",
            )

        # "full" mode — importance-sorted
        return await self._handle_full_mode(
            node_limit=node_limit,
            edge_limit=edge_limit,
            stats=stats,
        )

    async def _handle_expand(
        self,
        cluster_label: str,
        *,
        node_limit: int,
        edge_limit: int,
        stats: GraphStats,
    ) -> ClusteredGraphData:
        """Handle expand mode including sub-cluster drill-down."""
        # Sub-cluster drill-down (offset-based)
        if cluster_label.startswith("subcluster__"):
            parts = cluster_label.split("__")
            if len(parts) == 4:
                real_label = parts[1]
                skip = int(parts[2])
                chunk = int(parts[3])
                data = await self._expansion.expand_cluster_slice(
                    real_label, skip=skip, limit=chunk, edge_limit=edge_limit
                )
                rel_type_counts, neighbor_label_counts = await self._expansion.get_label_metadata(real_label)
                return ClusteredGraphData(
                    nodes=data.nodes,
                    edges=data.edges,
                    total_node_count=stats.node_count,
                    total_edge_count=stats.edge_count,
                    cluster_count=0,
                    mode="expand",
                    scope_label=real_label,
                    metadata={
                        "neighbor_label_counts": neighbor_label_counts,
                        "rel_type_counts": rel_type_counts,
                        "scope_skip": skip,
                        "scope_limit": chunk,
                    },
                )

        # Regular label expand
        label_count = await self._expansion.count_label_nodes(cluster_label)

        if label_count > node_limit:
            return await self._expand_as_subclusters(
                cluster_label,
                label_count=label_count,
                node_limit=node_limit,
            )

        # Small enough — return flat
        data = await self._expansion.expand_cluster(cluster_label, node_limit=node_limit, edge_limit=edge_limit)
        rel_type_counts, neighbor_label_counts = await self._expansion.get_label_metadata(cluster_label)
        return ClusteredGraphData(
            nodes=data.nodes,
            edges=data.edges,
            total_node_count=stats.node_count,
            total_edge_count=stats.edge_count,
            cluster_count=0,
            mode="expand",
            scope_label=cluster_label,
            metadata={
                "neighbor_label_counts": neighbor_label_counts,
                "rel_type_counts": rel_type_counts,
            },
        )

    async def _expand_as_subclusters(
        self,
        cluster_label: str,
        *,
        label_count: int,
        node_limit: int,
    ) -> ClusteredGraphData:
        """Too many nodes for flat display — produce offset-based sub-clusters."""
        chunk_size = max(node_limit, 50)
        top_names = await self._expansion.top_entity_names(cluster_label, limit=label_count)
        sub_clusters = ExpansionRepository.build_sub_clusters(
            label=cluster_label,
            total_count=label_count,
            chunk_size=chunk_size,
            top_entities_per_chunk=5,
            entity_names=top_names,
        )
        label_edge_count = await self._expansion.count_label_edges(cluster_label)
        rel_type_counts, neighbor_label_counts = await self._expansion.get_label_metadata(cluster_label)
        chunked_rels = await self._expansion.get_chunked_internal_rel_types(cluster_label, chunk_size)

        for sc in sub_clusters:
            offset = sc.properties.get("_skip", 0)
            sc.properties["_rel_type_counts"] = chunked_rels.get(offset, {})
            sc.properties["_neighbor_label_counts"] = neighbor_label_counts

        return ClusteredGraphData(
            nodes=sub_clusters,
            edges=[],
            total_node_count=label_count,
            total_edge_count=label_edge_count,
            cluster_count=len(sub_clusters),
            mode="expand",
            scope_label=cluster_label,
            metadata={
                "neighbor_label_counts": neighbor_label_counts,
                "rel_type_counts": rel_type_counts,
            },
        )

    async def _handle_full_mode(
        self,
        *,
        node_limit: int,
        edge_limit: int,
        stats: GraphStats,
    ) -> ClusteredGraphData:
        """Full mode — importance-sorted nodes with edges."""
        important_nodes = await self._expansion.get_important_nodes(limit=node_limit)
        node_ids = [n.id for n in important_nodes]

        edges: list[GraphEdge] = []
        if node_ids:
            async with self._session() as session:
                edge_result = await session.run(
                    EDGES_BETWEEN_IDS_FULL,
                    cid=self.cid,
                    ids=node_ids,
                    limit=edge_limit,
                )
                edges.extend([self._map_edge(record) async for record in edge_result])

        return ClusteredGraphData(
            nodes=important_nodes,
            edges=edges,
            total_node_count=stats.node_count,
            total_edge_count=stats.edge_count,
            cluster_count=0,
            mode="full",
        )
