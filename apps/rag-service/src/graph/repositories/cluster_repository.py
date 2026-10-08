"""Repository — Server-side clustered graph overview (Louvain / label-based)."""

from __future__ import annotations

import uuid

from error_contract import DatabaseOperationError

from src.graph.queries.visualization import (
    ALL_COLLECTION_EDGES,
    ALL_LABEL_COUNTS,
    CLUSTER_BY_LABEL,
    GDS_GRAPH_DROP,
    GDS_GRAPH_PROJECT,
    GDS_LOUVAIN_STREAM,
)
from src.graph.repositories.base import Neo4jRepository
from src.graph.repositories.stats_repository import StatsRepository
from src.graph.schemas import (
    ClusterEdge,
    ClusteredGraphData,
    ClusterNode,
    GraphNode,
    GraphStats,
)
from src.shared.observability import get_logger

logger = get_logger(__name__)


class ClusterRepository(Neo4jRepository):
    """Clustered overview of a collection's whole graph.

    Groups nodes into cluster supernodes so a large graph renders as a
    handful of nodes instead of thousands: GDS Louvain community detection
    when available, falling back to grouping by entity label. Drilling into
    one cluster's real nodes is ``ExpansionRepository``'s job, not this
    class's.
    """

    def __init__(self, collection_id: str) -> None:
        super().__init__(collection_id)
        self._stats_repo = StatsRepository(collection_id)

    async def get_graph_overview(
        self,
        *,
        max_clusters: int = 200,
        top_entities_per_cluster: int = 5,
    ) -> ClusteredGraphData:
        """Server-side clustered overview of the full graph.

        Uses GDS Louvain with fallback to label-based grouping.
        """
        stats = await self._stats_repo.get_stats()

        if stats.node_count <= max_clusters:
            from src.graph.repositories.entity_repository import (
                EntityRepository,
            )

            entity_repo = EntityRepository(self.cid)
            data = await entity_repo.get_graph_data(
                node_limit=stats.node_count,
                edge_limit=stats.edge_count,
            )
            return ClusteredGraphData(
                nodes=data.nodes,
                edges=data.edges,
                total_node_count=stats.node_count,
                total_edge_count=stats.edge_count,
                cluster_count=0,
                mode="full",
            )

        try:
            return await self._cluster_louvain(
                max_clusters=max_clusters,
                top_entities_per_cluster=top_entities_per_cluster,
                stats=stats,
            )
        except DatabaseOperationError as exc:
            logger.warning("GDS Louvain not available (%s), using label-based grouping", exc)
            return await self._cluster_by_label(
                max_clusters=max_clusters,
                top_entities_per_cluster=top_entities_per_cluster,
                stats=stats,
            )

    async def _cluster_louvain(
        self,
        *,
        max_clusters: int,
        top_entities_per_cluster: int,
        stats: GraphStats,
    ) -> ClusteredGraphData:
        """Cluster via Neo4j GDS Louvain community detection."""
        # Unique per call: a name derived only from the collection id
        # collided between two concurrent visualization requests for the
        # same collection, each dropping/overwriting the other's projection.
        graph_name = f"viz_{self.cid[:12]}_{uuid.uuid4().hex[:8]}"
        async with self._session() as session:
            await session.run(
                GDS_GRAPH_PROJECT,
                graph_name=graph_name,
                cid=self.cid,
            )

            try:
                # Run Louvain
                louvain_result = await session.run(
                    GDS_LOUVAIN_STREAM,
                    graph_name=graph_name,
                    cid=self.cid,
                )

                communities: dict[int, list[dict]] = {}
                async for record in louvain_result:
                    comm_id = record["communityId"]
                    if comm_id not in communities:
                        communities[comm_id] = []
                    communities[comm_id].append(
                        {
                            "id": record["id"],
                            "name": record["name"],
                            "label": record["label"] or "Entity",
                        }
                    )
            finally:
                # Always drop the projection, even on failure — otherwise it
                # leaks in the GDS in-memory graph catalog until restart.
                try:
                    await session.run(GDS_GRAPH_DROP, graph_name=graph_name)
                except Exception:
                    logger.warning("Failed to drop GDS projection %s", graph_name)

        return self._build_clustered_response(
            communities=communities,
            max_clusters=max_clusters,
            top_entities_per_cluster=top_entities_per_cluster,
            stats=stats,
        )

    async def _cluster_by_label(
        self,
        *,
        max_clusters: int,
        top_entities_per_cluster: int,
        stats: GraphStats,
    ) -> ClusteredGraphData:
        """Fallback clustering by entity label + degree-based importance."""
        async with self._session() as session:
            result = await session.run(CLUSTER_BY_LABEL, cid=self.cid)

            label_groups: dict[str, list[dict]] = {}
            async for record in result:
                lbl = record["label"] or "Entity"
                if lbl not in label_groups:
                    label_groups[lbl] = []
                label_groups[lbl].append(
                    {
                        "id": record["id"],
                        "name": record["name"],
                        "label": lbl,
                        "degree": record["degree"],
                    }
                )

        communities: dict[int, list[dict]] = {}
        comm_idx = 0
        for nodes in label_groups.values():
            chunk_size = max(len(nodes) // max(1, max_clusters // len(label_groups)), 10)
            for i in range(0, len(nodes), chunk_size):
                communities[comm_idx] = nodes[i : i + chunk_size]
                comm_idx += 1

        return self._build_clustered_response(
            communities=communities,
            max_clusters=max_clusters,
            top_entities_per_cluster=top_entities_per_cluster,
            stats=stats,
        )

    async def get_graph_overview_with_edges(
        self,
        *,
        max_clusters: int = 200,
        top_entities_per_cluster: int = 5,
    ) -> ClusteredGraphData:
        """Full overview with aggregated inter-cluster edges."""
        overview = await self.get_graph_overview(
            max_clusters=max_clusters,
            top_entities_per_cluster=top_entities_per_cluster,
        )
        if overview.mode == "full":
            return overview

        async with self._session() as session:
            result = await session.run(ALL_COLLECTION_EDGES, cid=self.cid)

            node_to_cluster: dict[str, str] = {}
            cluster_rel_counts: dict[str, dict[str, int]] = {}

            for n in overview.nodes:
                cluster_rel_counts[n.id] = {}
                if isinstance(n, ClusterNode) and n.is_cluster:
                    for mid in n.properties.get("_member_ids", []):
                        node_to_cluster[mid] = n.id
                else:
                    node_to_cluster[n.id] = n.id

            edge_agg: dict[tuple[str, str], dict[str, int]] = {}
            async for record in result:
                src_cluster = node_to_cluster.get(record["src"])
                tgt_cluster = node_to_cluster.get(record["tgt"])

                rtype = record["rtype"]

                if src_cluster:
                    cluster_rel_counts[src_cluster][rtype] = cluster_rel_counts[src_cluster].get(rtype, 0) + 1
                if tgt_cluster and tgt_cluster != src_cluster:
                    cluster_rel_counts[tgt_cluster][rtype] = cluster_rel_counts[tgt_cluster].get(rtype, 0) + 1

                if not src_cluster or not tgt_cluster or src_cluster == tgt_cluster:
                    continue
                key = (min(src_cluster, tgt_cluster), max(src_cluster, tgt_cluster))
                if key not in edge_agg:
                    edge_agg[key] = {}
                rtype = record["rtype"]
                edge_agg[key][rtype] = edge_agg[key].get(rtype, 0) + 1

            cluster_edges: list[ClusterEdge] = []
            for (src, tgt), type_counts in edge_agg.items():
                dominant_type = max(type_counts, key=type_counts.get)  # type: ignore[arg-type]
                total_weight = sum(type_counts.values())
                cluster_edges.append(
                    ClusterEdge(
                        id=f"ce_{src}_{tgt}",
                        source=src,
                        target=tgt,
                        type=dominant_type,
                        weight=total_weight,
                        relationship_types=list(type_counts.keys()),
                        properties={"type_counts": type_counts},
                    )
                )

        for n in overview.nodes:
            if isinstance(n, ClusterNode) and n.is_cluster:
                n.properties["_rel_type_counts"] = cluster_rel_counts.get(n.id, {})

        # Patch node_count on each cluster with the real Neo4j label count so
        # the overview badge matches what the user sees after expanding.
        async with self._session() as session:
            lc_result = await session.run(ALL_LABEL_COUNTS, cid=self.cid)
            real_counts: dict[str, int] = {}
            async for record in lc_result:
                real_counts[record["label"]] = record["cnt"]

        for n in overview.nodes:
            if isinstance(n, ClusterNode) and n.is_cluster:
                real = real_counts.get(n.label)
                if real is not None and real != n.node_count:
                    n.node_count = real
                    n.name = f"{n.label} ({real})"

        # Do not return the inter-cluster edges in the UI, just the counts in node properties
        overview.edges = []
        return overview

    @staticmethod
    def _build_clustered_response(
        *,
        communities: dict[int, list[dict]],
        max_clusters: int,
        top_entities_per_cluster: int,
        stats: GraphStats,
    ) -> ClusteredGraphData:
        """Build ClusteredGraphData from community assignments."""
        # Merge ALL communities by dominant label first so every node is
        # counted before any truncation happens.  Truncating before the merge
        # caused the overview count to be lower than the true Neo4j count.
        label_merged: dict[str, list[dict]] = {}
        for members in communities.values():
            lfreq: dict[str, int] = {}
            for m in members:
                lfreq[m["label"]] = lfreq.get(m["label"], 0) + 1
            dom = max(lfreq, key=lfreq.get)  # type: ignore[arg-type]
            label_merged.setdefault(dom, []).extend(members)

        merged_comms = sorted(label_merged.items(), key=lambda x: len(x[1]), reverse=True)
        if len(merged_comms) > max_clusters:
            merged_comms = merged_comms[:max_clusters]

        cluster_nodes: list[ClusterNode | GraphNode] = []
        for idx, (dominant_label, members) in enumerate(merged_comms):
            cluster_id = f"cluster_{idx}"

            label_freq: dict[str, int] = {}
            for m in members:
                label_freq[m["label"]] = label_freq.get(m["label"], 0) + 1

            top_names = [m["name"] for m in members[:top_entities_per_cluster]]

            if len(members) == 1:
                m = members[0]
                cluster_nodes.append(
                    GraphNode(
                        id=m["id"],
                        label=m["label"],
                        name=m["name"],
                        properties={},
                    )
                )
            else:
                display_name = f"{dominant_label} ({len(members)})"
                cluster_nodes.append(
                    ClusterNode(
                        id=cluster_id,
                        label=dominant_label,
                        name=display_name,
                        node_count=len(members),
                        top_entities=top_names,
                        properties={
                            "community_id": idx,
                            "label_counts": label_freq,
                            "_member_ids": [m["id"] for m in members],
                        },
                        is_cluster=True,
                    )
                )

        return ClusteredGraphData(
            nodes=cluster_nodes,
            edges=[],
            total_node_count=stats.node_count,
            total_edge_count=stats.edge_count,
            cluster_count=len([n for n in cluster_nodes if isinstance(n, ClusterNode)]),
            mode="overview",
        )
