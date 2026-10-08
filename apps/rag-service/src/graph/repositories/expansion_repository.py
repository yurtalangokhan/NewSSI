"""Repository — Drilling into one label/cluster: real nodes, neighbourhood, metadata.

Where ``ClusterRepository`` answers "what does the whole graph look like at
a glance", this answers "give me the actual nodes behind one cluster, one
node's neighbourhood, or the metadata (counts, relationship types) that
describes a label group."
"""

from __future__ import annotations

from src.graph.queries.visualization import (
    CHUNKED_INTERNAL_REL_TYPES,
    COUNT_LABEL_EDGES,
    COUNT_LABEL_NODES,
    EDGES_BETWEEN_IDS,
    EXPAND_CLUSTER_NODES,
    EXPAND_CLUSTER_SLICE,
    IMPORTANT_NODES,
    LABEL_NEIGHBOR_LABELS,
    LABEL_RELATIONSHIP_TYPES,
    NEIGHBORHOOD_TEMPLATE,
    TOP_ENTITY_NAMES_BY_DEGREE,
)
from src.graph.repositories.base import Neo4jRepository
from src.graph.schemas import ClusterNode, GraphData, GraphNode
from src.shared.observability import get_logger

logger = get_logger(__name__)


class ExpansionRepository(Neo4jRepository):
    """Real nodes/edges behind a cluster, a node's neighbourhood, and label metadata."""

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
            edges = [self._map_edge(record) async for record in edge_result]

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
            edges = [self._map_edge(record) async for record in edge_result]

        return GraphData(nodes=nodes, edges=edges)

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
            edges = [self._map_edge(record) async for record in edge_result]

        return GraphData(nodes=nodes, edges=edges)

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

    async def get_label_metadata(self, label: str) -> tuple[dict[str, int], dict[str, int]]:
        """Return (rel_type_counts, neighbor_label_counts) for a label group."""
        async with self._session() as session:
            rel_result = await session.run(LABEL_RELATIONSHIP_TYPES, cid=self.cid, label=label)
            rel_type_counts: dict[str, int] = {}
            async for record in rel_result:
                rel_type_counts[record["rtype"]] = record["cnt"]

            label_result = await session.run(LABEL_NEIGHBOR_LABELS, cid=self.cid, label=label)
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

    async def get_chunked_internal_rel_types(self, label: str, chunk_size: int) -> dict[int, dict[str, int]]:
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

    @staticmethod
    def build_sub_clusters(
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
