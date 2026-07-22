"""Repository — Scalable visualization (clustering, expansion, neighbourhood)."""

from __future__ import annotations

import logging

from langconnect.database.neo4j.queries.visualization import (
    ALL_COLLECTION_EDGES,
    ALL_LABEL_COUNTS,
    CHUNKED_INTERNAL_REL_TYPES,
    CLUSTER_BY_LABEL,
    COUNT_LABEL_EDGES,
    COUNT_LABEL_NODES,
    EDGES_BETWEEN_IDS,
    EDGES_BETWEEN_IDS_FULL,
    EXPAND_CLUSTER_NODES,
    EXPAND_CLUSTER_SLICE,
    GDS_GRAPH_DROP,
    GDS_GRAPH_PROJECT,
    GDS_LOUVAIN_STREAM,
    IMPORTANT_NODES,
    LABEL_NEIGHBOR_LABELS,
    LABEL_RELATIONSHIP_TYPES,
    NEIGHBORHOOD_TEMPLATE,
    TOP_ENTITY_NAMES_BY_DEGREE,
)
from langconnect.database.neo4j.repositories.base import Neo4jRepository
from langconnect.database.neo4j.repositories.stats_repository import StatsRepository
from langconnect.models.graph import (
    ClusterEdge,
    ClusteredGraphData,
    ClusterNode,
    GraphData,
    GraphEdge,
    GraphNode,
    GraphStats,
)

logger = logging.getLogger(__name__)


class VisualizationRepository(Neo4jRepository):
    """Scalable graph visualisation: clustering, drill-down, neighbourhood."""

    def __init__(self, collection_id: str) -> None:
        super().__init__(collection_id)
        self._stats_repo = StatsRepository(collection_id)

    # ------------------------------------------------------------------
    # Overview (clustered)
    # ------------------------------------------------------------------

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
            from langconnect.database.neo4j.repositories.entity_repository import (
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
        except Exception as exc:
            logger.warning(
                "GDS Louvain not available (%s), using label-based grouping", exc
            )
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
        graph_name = f"viz_{self.cid[:12]}"
        async with self._session() as session:
            # Drop existing projection
            try:
                await session.run(GDS_GRAPH_DROP, graph_name=graph_name)
            except Exception:
                pass

            # Create projection
            await session.run(
                GDS_GRAPH_PROJECT,
                graph_name=graph_name,
                cid=self.cid,
            )

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

            # Cleanup
            try:
                await session.run(GDS_GRAPH_DROP, graph_name=graph_name)
            except Exception:
                pass

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
        for _lbl, nodes in label_groups.items():
            chunk_size = max(
                len(nodes) // max(1, max_clusters // len(label_groups)), 10
            )
            for i in range(0, len(nodes), chunk_size):
                communities[comm_idx] = nodes[i : i + chunk_size]
                comm_idx += 1

        return self._build_clustered_response(
            communities=communities,
            max_clusters=max_clusters,
            top_entities_per_cluster=top_entities_per_cluster,
            stats=stats,
        )

    # ------------------------------------------------------------------
    # Overview with aggregated inter-cluster edges
    # ------------------------------------------------------------------

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
                    cluster_rel_counts[src_cluster][rtype] = (
                        cluster_rel_counts[src_cluster].get(rtype, 0) + 1
                    )
                if tgt_cluster and tgt_cluster != src_cluster:
                    cluster_rel_counts[tgt_cluster][rtype] = (
                        cluster_rel_counts[tgt_cluster].get(rtype, 0) + 1
                    )

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

    # ------------------------------------------------------------------
    # Expand cluster
    # ------------------------------------------------------------------

    async def expand_cluster(
        self,
        cluster_label: str,
        *,
        node_limit: int = 200,
        edge_limit: int = 500,
    ) -> GraphData:
        """Expand a cluster: return actual nodes with the given label."""
        async with self._session() as session:
            node_result = await session.run(
                EXPAND_CLUSTER_NODES,
                cid=self.cid,
                label=cluster_label,
                limit=node_limit,
            )
            nodes: list[GraphNode] = []
            node_ids: set[str] = set()
            async for record in node_result:
                nodes.append(self._map_node(record))
                node_ids.add(record["id"])

            if not node_ids:
                return GraphData(nodes=[], edges=[])

            edge_result = await session.run(
                EDGES_BETWEEN_IDS,
                cid=self.cid,
                ids=list(node_ids),
                elimit=edge_limit,
            )
            edges: list[GraphEdge] = []
            async for record in edge_result:
                edges.append(self._map_edge(record))

        return GraphData(nodes=nodes, edges=edges)

    async def expand_cluster_slice(
        self,
        label: str,
        *,
        skip: int = 0,
        limit: int = 200,
        edge_limit: int = 500,
    ) -> GraphData:
        """Return a specific offset-based slice of nodes for a label."""
        async with self._session() as session:
            node_result = await session.run(
                EXPAND_CLUSTER_SLICE,
                cid=self.cid,
                label=label,
                skip=skip,
                limit=limit,
            )
            nodes: list[GraphNode] = []
            node_ids: set[str] = set()
            async for record in node_result:
                nodes.append(self._map_node(record))
                node_ids.add(record["id"])

            if not node_ids:
                return GraphData(nodes=[], edges=[])

            edge_result = await session.run(
                EDGES_BETWEEN_IDS,
                cid=self.cid,
                ids=list(node_ids),
                elimit=edge_limit,
            )
            edges: list[GraphEdge] = []
            async for record in edge_result:
                edges.append(self._map_edge(record))

        return GraphData(nodes=nodes, edges=edges)

    # ------------------------------------------------------------------
    # Neighbourhood (ego-graph)
    # ------------------------------------------------------------------

    async def get_neighborhood(
        self,
        node_id: str,
        *,
        depth: int = 1,
        limit: int = 50,
    ) -> GraphData:
        """Get ego-graph (neighbourhood) around a specific node."""
        query = NEIGHBORHOOD_TEMPLATE.format(depth=depth)
        async with self._session() as session:
            result = await session.run(
                query,
                cid=self.cid,
                node_id=node_id,
                limit=limit,
            )
            nodes: list[GraphNode] = []
            node_ids: set[str] = set()
            async for record in result:
                nodes.append(self._map_node(record))
                node_ids.add(record["id"])

            if not node_ids:
                return GraphData(nodes=[], edges=[])

            edge_result = await session.run(
                EDGES_BETWEEN_IDS,
                cid=self.cid,
                ids=list(node_ids),
                elimit=10_000,
            )
            edges: list[GraphEdge] = []
            async for record in edge_result:
                edges.append(self._map_edge(record))

        return GraphData(nodes=nodes, edges=edges)

    # ------------------------------------------------------------------
    # Important nodes (degree centrality)
    # ------------------------------------------------------------------

    async def get_important_nodes(
        self,
        *,
        limit: int = 200,
    ) -> list[GraphNode]:
        """Get the most important nodes by degree centrality."""
        async with self._session() as session:
            result = await session.run(
                IMPORTANT_NODES,
                cid=self.cid,
                limit=limit,
            )
            nodes: list[GraphNode] = []
            async for record in result:
                props = self._clean_node_props(record["props"])
                props["degree"] = record["degree"]
                nodes.append(
                    GraphNode(
                        id=record["id"],
                        label=record["label"] or "Entity",
                        name=record["name"],
                        properties=props,
                    )
                )
            return nodes

    # ------------------------------------------------------------------
    # Label metadata helpers
    # ------------------------------------------------------------------

    async def count_label_nodes(self, label: str) -> int:
        async with self._session() as session:
            result = await session.run(COUNT_LABEL_NODES, cid=self.cid, label=label)
            record = await result.single()
            return record["cnt"] if record else 0

    async def count_label_edges(self, label: str) -> int:
        async with self._session() as session:
            result = await session.run(COUNT_LABEL_EDGES, cid=self.cid, label=label)
            record = await result.single()
            return record["cnt"] if record else 0

    async def get_label_metadata(
        self, label: str
    ) -> tuple[dict[str, int], dict[str, int]]:
        """Return (rel_type_counts, neighbor_label_counts) for a label group."""
        async with self._session() as session:
            rel_result = await session.run(
                LABEL_RELATIONSHIP_TYPES, cid=self.cid, label=label
            )
            rel_type_counts: dict[str, int] = {}
            async for record in rel_result:
                rel_type_counts[record["rtype"]] = record["cnt"]

            label_result = await session.run(
                LABEL_NEIGHBOR_LABELS, cid=self.cid, label=label
            )
            neighbor_label_counts: dict[str, int] = {}
            async for record in label_result:
                neighbor_label_counts[record["blabel"] or "Entity"] = record["cnt"]

        return rel_type_counts, neighbor_label_counts

    async def top_entity_names(self, label: str, limit: int = 100) -> list[str]:
        async with self._session() as session:
            result = await session.run(
                TOP_ENTITY_NAMES_BY_DEGREE,
                cid=self.cid,
                label=label,
                limit=limit,
            )
            return [record["name"] async for record in result]

    async def get_chunked_internal_rel_types(
        self, label: str, chunk_size: int
    ) -> dict[int, dict[str, int]]:
        async with self._session() as session:
            result = await session.run(
                CHUNKED_INTERNAL_REL_TYPES,
                cid=self.cid,
                label=label,
                chunk_size=chunk_size,
            )
            data: dict[int, dict[str, int]] = {}
            async for record in result:
                offset = record["offset"]
                rtype = record["rtype"]
                cnt = record["cnt"]
                if offset not in data:
                    data[offset] = {}
                data[offset][rtype] = cnt
            return data

    # ------------------------------------------------------------------
    # Unified scalable endpoint
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
            return await self.get_graph_overview_with_edges(max_clusters=node_limit)

        if mode == "expand" and cluster_label:
            return await self._handle_expand(
                cluster_label,
                node_limit=node_limit,
                edge_limit=edge_limit,
                stats=stats,
            )

        if mode == "neighborhood" and node_id:
            data = await self.get_neighborhood(node_id, depth=depth, limit=node_limit)
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

    # ------------------------------------------------------------------
    # Private: scalable expand logic
    # ------------------------------------------------------------------

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
                data = await self.expand_cluster_slice(
                    real_label, skip=skip, limit=chunk, edge_limit=edge_limit
                )
                rel_type_counts, neighbor_label_counts = await self.get_label_metadata(
                    real_label
                )
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
        label_count = await self.count_label_nodes(cluster_label)

        if label_count > node_limit:
            return await self._expand_as_subclusters(
                cluster_label,
                label_count=label_count,
                node_limit=node_limit,
                stats=stats,
            )

        # Small enough — return flat
        data = await self.expand_cluster(
            cluster_label, node_limit=node_limit, edge_limit=edge_limit
        )
        rel_type_counts, neighbor_label_counts = await self.get_label_metadata(
            cluster_label
        )
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
        stats: GraphStats,
    ) -> ClusteredGraphData:
        """Too many nodes for flat display — produce offset-based sub-clusters."""
        chunk_size = max(node_limit, 50)
        top_names = await self.top_entity_names(cluster_label, limit=label_count)
        sub_clusters = self._build_sub_clusters(
            label=cluster_label,
            total_count=label_count,
            chunk_size=chunk_size,
            top_entities_per_chunk=5,
            entity_names=top_names,
        )
        label_edge_count = await self.count_label_edges(cluster_label)
        rel_type_counts, neighbor_label_counts = await self.get_label_metadata(
            cluster_label
        )
        chunked_rels = await self.get_chunked_internal_rel_types(
            cluster_label, chunk_size
        )

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
        important_nodes = await self.get_important_nodes(limit=node_limit)
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
                async for record in edge_result:
                    edges.append(self._map_edge(record))

        return ClusteredGraphData(
            nodes=important_nodes,
            edges=edges,
            total_node_count=stats.node_count,
            total_edge_count=stats.edge_count,
            cluster_count=0,
            mode="full",
        )

    # ------------------------------------------------------------------
    # Clustered response builder (shared by Louvain + label-based)
    # ------------------------------------------------------------------

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
        for _comm_id, members in communities.items():
            lfreq: dict[str, int] = {}
            for m in members:
                lfreq[m["label"]] = lfreq.get(m["label"], 0) + 1
            dom = max(lfreq, key=lfreq.get)  # type: ignore[arg-type]
            label_merged.setdefault(dom, []).extend(members)

        merged_comms = sorted(
            label_merged.items(), key=lambda x: len(x[1]), reverse=True
        )
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

    @staticmethod
    def _build_sub_clusters(
        label: str,
        total_count: int,
        chunk_size: int,
        top_entities_per_chunk: int = 5,
        entity_names: list[str] | None = None,
    ) -> list[ClusterNode]:
        """Build offset-based sub-cluster supernodes for a label."""
        clusters: list[ClusterNode] = []
        for offset in range(0, total_count, chunk_size):
            actual_size = min(chunk_size, total_count - offset)
            chunk_id = f"subcluster__{label}__{offset}__{chunk_size}"

            top: list[str] = []
            if entity_names:
                top = entity_names[offset : offset + top_entities_per_chunk]

            clusters.append(
                ClusterNode(
                    id=chunk_id,
                    label=label,
                    name=f"{label} #{offset // chunk_size + 1} ({actual_size})",
                    node_count=actual_size,
                    top_entities=top,
                    properties={"_skip": offset, "_limit": chunk_size},
                    is_cluster=True,
                )
            )
        return clusters
