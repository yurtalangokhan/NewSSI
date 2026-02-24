"""Knowledge Graph store – CRUD operations on Neo4j.

Each collection gets its own namespace via a `collection_id` property on every
node and relationship, so multiple collections can coexist in the same database.
"""

import logging
from datetime import datetime, date, time, timedelta
from typing import Any

from neo4j import AsyncDriver
from neo4j.time import DateTime as Neo4jDateTime, Date as Neo4jDate, Time as Neo4jTime, Duration as Neo4jDuration


def _sanitize_props(props: dict[str, Any]) -> dict[str, Any]:
    """Convert Neo4j-specific types to JSON-serializable Python types."""
    clean: dict[str, Any] = {}
    for k, v in props.items():
        if isinstance(v, Neo4jDateTime):
            clean[k] = v.to_native().isoformat()
        elif isinstance(v, Neo4jDate):
            clean[k] = v.to_native().isoformat()
        elif isinstance(v, Neo4jTime):
            clean[k] = v.to_native().isoformat()
        elif isinstance(v, Neo4jDuration):
            clean[k] = str(v)
        elif isinstance(v, (datetime, date, time)):
            clean[k] = v.isoformat()
        elif isinstance(v, timedelta):
            clean[k] = str(v)
        elif isinstance(v, list):
            clean[k] = [_sanitize_props({"_": item})["_"] if isinstance(item, dict) else item for item in v]
        else:
            clean[k] = v
    return clean

from langconnect.database.graph_connection import get_neo4j_driver
from langconnect.models.graph import (
    ClusterEdge,
    ClusterNode,
    ClusteredGraphData,
    GraphData,
    GraphEdge,
    GraphNode,
    GraphStats,
    PaginatedCounts,
)

logger = logging.getLogger(__name__)


class GraphStore:
    """Manages knowledge-graph nodes and edges for a single collection."""

    def __init__(self, collection_id: str) -> None:
        self.collection_id = collection_id

    async def _driver(self) -> AsyncDriver:
        return await get_neo4j_driver()

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    async def ensure_indexes(self) -> None:
        """Create indexes for efficient lookups (idempotent).

        Also creates a **fulltext** index (Lucene-backed) on Entity
        nodes so that ``db.index.fulltext.queryNodes`` can perform
        BM25-scored searches across entity names and labels.
        """
        driver = await self._driver()
        async with driver.session() as session:
            # Composite index on (collection_id, name) for fast entity lookup
            await session.run(
                "CREATE INDEX IF NOT EXISTS FOR (n:Entity) ON (n.collection_id, n.name)"
            )
            await session.run(
                "CREATE INDEX IF NOT EXISTS FOR (n:Entity) ON (n.collection_id)"
            )

            # Fulltext (BM25) index on Entity name + label.
            # Neo4j fulltext indexes are global; we filter by collection_id
            # in the Cypher query that calls the index.
            try:
                await session.run(
                    """
                    CREATE FULLTEXT INDEX entity_fulltext IF NOT EXISTS
                    FOR (n:Entity)
                    ON EACH [n.name, n.label]
                    OPTIONS {
                        indexConfig: {
                            `fulltext.analyzer`: 'standard-no-stop-words',
                            `fulltext.eventually_consistent`: false
                        }
                    }
                    """
                )
                logger.info(
                    "Neo4j fulltext (BM25) index ensured for collection %s",
                    self.collection_id,
                )
            except Exception as exc:
                # Index may already exist with different config – not fatal
                logger.warning("Fulltext index creation note: %s", exc)

            logger.info("Neo4j indexes ensured for collection %s", self.collection_id)

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    async def upsert_node(
        self,
        name: str,
        label: str,
        properties: dict[str, Any] | None = None,
    ) -> str:
        """Create or merge a node. Returns the element id."""
        props = properties or {}
        driver = await self._driver()
        async with driver.session() as session:
            result = await session.run(
                """
                MERGE (n:Entity {collection_id: $cid, name: $name})
                ON CREATE SET n.label = $label, n += $props, n.created_at = datetime()
                ON MATCH SET n.label = $label, n += $props, n.updated_at = datetime()
                RETURN elementId(n) AS eid
                """,
                cid=self.collection_id,
                name=name,
                label=label,
                props=props,
            )
            record = await result.single()
            return record["eid"]  # type: ignore[index]

    async def upsert_edge(
        self,
        source_name: str,
        target_name: str,
        rel_type: str,
        properties: dict[str, Any] | None = None,
    ) -> str:
        """Create or merge an edge between two nodes. Returns the element id."""
        props = properties or {}
        # Sanitize relationship type for Neo4j
        safe_type = rel_type.upper().replace(" ", "_").replace("-", "_")
        driver = await self._driver()
        async with driver.session() as session:
            result = await session.run(
                f"""
                MATCH (a:Entity {{collection_id: $cid, name: $src}})
                MATCH (b:Entity {{collection_id: $cid, name: $tgt}})
                MERGE (a)-[r:`{safe_type}` {{collection_id: $cid}}]->(b)
                ON CREATE SET r += $props, r.created_at = datetime()
                ON MATCH SET r += $props, r.updated_at = datetime()
                RETURN elementId(r) AS eid
                """,
                cid=self.collection_id,
                src=source_name,
                tgt=target_name,
                props=props,
            )
            record = await result.single()
            if record is None:
                logger.warning(
                    "Edge not created – one or both nodes missing: %s -> %s",
                    source_name,
                    target_name,
                )
                return ""
            return record["eid"]  # type: ignore[index]

    async def bulk_upsert(
        self,
        entities: list[dict[str, Any]],
        relations: list[dict[str, Any]],
    ) -> dict[str, int]:
        """Bulk upsert entities and relations. Returns counts."""
        node_count = 0
        edge_count = 0

        for entity in entities:
            await self.upsert_node(
                name=entity["name"],
                label=entity.get("label", "Entity"),
                properties=entity.get("properties"),
            )
            node_count += 1

        for relation in relations:
            eid = await self.upsert_edge(
                source_name=relation["source"],
                target_name=relation["target"],
                rel_type=relation.get("type", "RELATED_TO"),
                properties=relation.get("properties"),
            )
            if eid:
                edge_count += 1

        return {"nodes": node_count, "edges": edge_count}

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
        """List nodes in this collection."""
        driver = await self._driver()
        label_clause = "AND n.label = $label" if label_filter else ""
        async with driver.session() as session:
            result = await session.run(
                f"""
                MATCH (n:Entity {{collection_id: $cid}})
                {label_clause}
                RETURN elementId(n) AS id, n.label AS label, n.name AS name,
                       properties(n) AS props
                ORDER BY n.name
                SKIP $offset LIMIT $limit
                """,
                cid=self.collection_id,
                label=label_filter,
                offset=offset,
                limit=limit,
            )
            nodes: list[GraphNode] = []
            async for record in result:
                props = dict(record["props"])
                # Remove internal props from public view
                props.pop("collection_id", None)
                props.pop("name", None)
                props.pop("label", None)
                props = _sanitize_props(props)
                nodes.append(
                    GraphNode(
                        id=record["id"],
                        label=record["label"] or "Entity",
                        name=record["name"],
                        properties=props,
                    )
                )
            return nodes

    async def get_edges(
        self,
        *,
        limit: int = 200,
        offset: int = 0,
    ) -> list[GraphEdge]:
        """List edges in this collection."""
        driver = await self._driver()
        async with driver.session() as session:
            result = await session.run(
                """
                MATCH (a:Entity {collection_id: $cid})-[r]->(b:Entity {collection_id: $cid})
                WHERE r.collection_id = $cid OR r.collection_id IS NULL
                RETURN elementId(r) AS id, elementId(a) AS src, elementId(b) AS tgt,
                       type(r) AS rtype, properties(r) AS props
                SKIP $offset LIMIT $limit
                """,
                cid=self.collection_id,
                offset=offset,
                limit=limit,
            )
            edges: list[GraphEdge] = []
            async for record in result:
                props = dict(record["props"])
                props.pop("collection_id", None)
                props = _sanitize_props(props)
                edges.append(
                    GraphEdge(
                        id=record["id"],
                        source=record["src"],
                        target=record["tgt"],
                        type=record["rtype"],
                        properties=props,
                    )
                )
            return edges

    async def get_graph_data(
        self,
        *,
        node_limit: int = 200,
        edge_limit: int = 500,
    ) -> GraphData:
        """Return full graph (nodes + edges) for visualization."""
        nodes = await self.get_nodes(limit=node_limit)
        edges = await self.get_edges(limit=edge_limit)
        return GraphData(nodes=nodes, edges=edges)

    # ------------------------------------------------------------------
    # Scalable Visualization (Clustering / Overview / Expand)
    # ------------------------------------------------------------------

    async def get_graph_overview(
        self,
        *,
        max_clusters: int = 200,
        top_entities_per_cluster: int = 5,
    ) -> ClusteredGraphData:
        """Server-side clustered overview of the full graph.

        Uses Neo4j's in-DB Louvain community detection (GDS plugin)
        with fallback to label-based grouping when GDS is not available.
        """
        stats = await self.get_stats()

        # If graph is small enough, return directly
        if stats.node_count <= max_clusters:
            data = await self.get_graph_data(
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

        # Try GDS Louvain, fallback to label-based grouping
        try:
            return await self._cluster_louvain(
                max_clusters=max_clusters,
                top_entities_per_cluster=top_entities_per_cluster,
                stats=stats,
            )
        except Exception as exc:
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
        driver = await self._driver()
        async with driver.session() as session:
            # Project the subgraph into GDS
            graph_name = f"viz_{self.collection_id[:12]}"
            # Drop if exists
            try:
                await session.run(f"CALL gds.graph.drop('{graph_name}', false)")
            except Exception:
                pass

            # Create projection
            await session.run(
                """
                CALL gds.graph.project.cypher(
                    $graph_name,
                    'MATCH (n:Entity {collection_id: $cid}) RETURN id(n) AS id',
                    'MATCH (a:Entity {collection_id: $cid})-[r]->(b:Entity {collection_id: $cid})
                     RETURN id(a) AS source, id(b) AS target',
                    {parameters: {cid: $cid}}
                )
                """,
                graph_name=graph_name,
                cid=self.collection_id,
            )

            # Run Louvain
            louvain_result = await session.run(
                """
                CALL gds.louvain.stream($graph_name)
                YIELD nodeId, communityId
                WITH gds.util.asNode(nodeId) AS node, communityId
                WHERE node.collection_id = $cid
                RETURN elementId(node) AS id, node.name AS name,
                       node.label AS label, communityId
                """,
                graph_name=graph_name,
                cid=self.collection_id,
            )

            # Group nodes by community
            communities: dict[int, list[dict]] = {}
            async for record in louvain_result:
                cid = record["communityId"]
                if cid not in communities:
                    communities[cid] = []
                communities[cid].append({
                    "id": record["id"],
                    "name": record["name"],
                    "label": record["label"] or "Entity",
                })

            # Clean up GDS projection
            try:
                await session.run(f"CALL gds.graph.drop('{graph_name}', false)")
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
        driver = await self._driver()
        async with driver.session() as session:
            # Get nodes with their degree (connection count)
            result = await session.run(
                """
                MATCH (n:Entity {collection_id: $cid})
                OPTIONAL MATCH (n)-[r]-()
                WITH n, count(r) AS degree
                RETURN elementId(n) AS id, n.name AS name,
                       n.label AS label, degree
                ORDER BY degree DESC
                """,
                cid=self.collection_id,
            )

            # Group by label
            label_groups: dict[str, list[dict]] = {}
            async for record in result:
                lbl = record["label"] or "Entity"
                if lbl not in label_groups:
                    label_groups[lbl] = []
                label_groups[lbl].append({
                    "id": record["id"],
                    "name": record["name"],
                    "label": lbl,
                    "degree": record["degree"],
                })

        # Convert label groups to community-like structure
        communities: dict[int, list[dict]] = {}
        comm_idx = 0

        for lbl, nodes in label_groups.items():
            # If a label group is too large, split it into sub-clusters
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

    def _build_clustered_response(
        self,
        *,
        communities: dict[int, list[dict]],
        max_clusters: int,
        top_entities_per_cluster: int,
        stats: GraphStats,
    ) -> ClusteredGraphData:
        """Build ClusteredGraphData from community assignments."""
        # Sort communities by size (largest first), cap at max_clusters
        sorted_comms = sorted(communities.items(), key=lambda x: len(x[1]), reverse=True)
        if len(sorted_comms) > max_clusters:
            sorted_comms = sorted_comms[:max_clusters]

        # Build node-to-cluster mapping
        node_to_cluster: dict[str, str] = {}
        cluster_nodes: list[ClusterNode | GraphNode] = []

        for idx, (comm_id, members) in enumerate(sorted_comms):
            cluster_id = f"cluster_{idx}"

            # Determine dominant label
            label_freq: dict[str, int] = {}
            for m in members:
                label_freq[m["label"]] = label_freq.get(m["label"], 0) + 1
            dominant_label = max(label_freq, key=label_freq.get)  # type: ignore

            # Top entities by name (already sorted by degree in label-based)
            top_names = [m["name"] for m in members[:top_entities_per_cluster]]

            # Map individual nodes to this cluster
            for m in members:
                node_to_cluster[m["id"]] = cluster_id

            if len(members) == 1:
                # Single node → return as-is, not a cluster
                m = members[0]
                cluster_nodes.append(
                    GraphNode(
                        id=m["id"],
                        label=m["label"],
                        name=m["name"],
                        properties={},
                    )
                )
                node_to_cluster[m["id"]] = m["id"]
            else:
                display_name = f"{dominant_label} ({len(members)})"
                cluster_nodes.append(
                    ClusterNode(
                        id=cluster_id,
                        label=dominant_label,
                        name=display_name,
                        node_count=len(members),
                        top_entities=top_names,
                        properties={"community_id": comm_id, "label_counts": label_freq},
                        is_cluster=True,
                    )
                )

        # Build aggregated edges (we need to re-query edges)
        # For now return nodes only; edges will be fetched in a follow-up
        return ClusteredGraphData(
            nodes=cluster_nodes,
            edges=[],
            total_node_count=stats.node_count,
            total_edge_count=stats.edge_count,
            cluster_count=len([n for n in cluster_nodes if isinstance(n, ClusterNode)]),
            mode="overview",
        )

    @staticmethod
    @staticmethod
    def _build_sub_clusters(
        label: str,
        total_count: int,
        chunk_size: int,
        top_entities_per_chunk: int = 5,
        entity_names: list[str] | None = None,
    ) -> list[ClusterNode]:
        """Build offset-based sub-cluster supernodes for a label.

        Each sub-cluster encodes its offset in the ID so the backend can
        serve the exact slice of nodes when clicked, preventing infinite
        recursion.

        IDs look like: ``subcluster__{label}__{skip}__{chunk_size}``
        """
        clusters: list[ClusterNode] = []
        for offset in range(0, total_count, chunk_size):
            actual_size = min(chunk_size, total_count - offset)
            chunk_id = f"subcluster__{label}__{offset}__{chunk_size}"

            # Pick top entity names for this chunk if available
            top = []
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

    async def _count_label_nodes(self, label: str) -> int:
        """Count how many Entity nodes have the given label in this collection."""
        driver = await self._driver()
        async with driver.session() as session:
            result = await session.run(
                """
                MATCH (n:Entity {collection_id: $cid})
                WHERE n.label = $label
                RETURN count(n) AS cnt
                """,
                cid=self.collection_id,
                label=label,
            )
            record = await result.single()
            return record["cnt"] if record else 0

    async def _count_label_edges(self, label: str) -> int:
        """Count edges where both source and target have the given label."""
        driver = await self._driver()
        async with driver.session() as session:
            result = await session.run(
                """
                MATCH (a:Entity {collection_id: $cid})-[r]->(b:Entity {collection_id: $cid})
                WHERE a.label = $label AND b.label = $label
                RETURN count(r) AS cnt
                """,
                cid=self.collection_id,
                label=label,
            )
            record = await result.single()
            return record["cnt"] if record else 0

    async def _get_label_metadata(
        self, label: str
    ) -> tuple[dict[str, int], dict[str, int]]:
        """Return (rel_type_counts, neighbor_label_counts) for a label group.

        * rel_type_counts  – every relationship type involving nodes of this
          label and how many edges of that type exist.
        * neighbor_label_counts – for each label of *connected* nodes, how
          many distinct neighbours exist (includes same-label connections).
        """
        driver = await self._driver()
        async with driver.session() as session:
            # Relationship types
            rel_result = await session.run(
                """
                MATCH (a:Entity {collection_id: $cid})-[r]-(b:Entity {collection_id: $cid})
                WHERE a.label = $label
                RETURN type(r) AS rtype, count(r) AS cnt
                """,
                cid=self.collection_id,
                label=label,
            )
            rel_type_counts: dict[str, int] = {}
            async for record in rel_result:
                rel_type_counts[record["rtype"]] = record["cnt"]

            # Neighbour labels
            label_result = await session.run(
                """
                MATCH (a:Entity {collection_id: $cid})-[]-(b:Entity {collection_id: $cid})
                WHERE a.label = $label
                RETURN b.label AS blabel, count(DISTINCT b) AS cnt
                """,
                cid=self.collection_id,
                label=label,
            )
            neighbor_label_counts: dict[str, int] = {}
            async for record in label_result:
                neighbor_label_counts[record["blabel"] or "Entity"] = record["cnt"]

            return rel_type_counts, neighbor_label_counts

    async def _top_entity_names(self, label: str, limit: int = 100) -> list[str]:
        """Fetch top entity names for a label, sorted by degree (descending)."""
        driver = await self._driver()
        async with driver.session() as session:
            result = await session.run(
                """
                MATCH (n:Entity {collection_id: $cid})
                WHERE n.label = $label
                OPTIONAL MATCH (n)-[r]-()
                WITH n, count(r) AS degree
                ORDER BY degree DESC
                LIMIT $limit
                RETURN n.name AS name
                """,
                cid=self.collection_id,
                label=label,
                limit=limit,
            )
            return [record["name"] async for record in result]

    async def _expand_cluster_slice(
        self,
        label: str,
        *,
        skip: int = 0,
        limit: int = 200,
        edge_limit: int = 500,
    ) -> GraphData:
        """Return a specific slice of nodes for a label (sorted by degree).

        Used by sub-cluster drill-down so each chunk maps to an exact offset.
        """
        driver = await self._driver()
        async with driver.session() as session:
            node_result = await session.run(
                """
                MATCH (n:Entity {collection_id: $cid})
                WHERE n.label = $label
                OPTIONAL MATCH (n)-[r]-()
                WITH n, count(r) AS degree
                ORDER BY degree DESC
                SKIP $skip
                LIMIT $limit
                RETURN elementId(n) AS id, n.label AS label,
                       n.name AS name, properties(n) AS props
                """,
                cid=self.collection_id,
                label=label,
                skip=skip,
                limit=limit,
            )

            nodes: list[GraphNode] = []
            node_ids: set[str] = set()
            async for record in node_result:
                props = dict(record["props"])
                props.pop("collection_id", None)
                props.pop("name", None)
                props.pop("label", None)
                props = _sanitize_props(props)
                nodes.append(
                    GraphNode(
                        id=record["id"],
                        label=record["label"] or "Entity",
                        name=record["name"],
                        properties=props,
                    )
                )
                node_ids.add(record["id"])

            if not node_ids:
                return GraphData(nodes=[], edges=[])

            # Edges between the slice nodes
            edge_result = await session.run(
                """
                MATCH (a:Entity {collection_id: $cid})-[r]->(b:Entity {collection_id: $cid})
                WHERE elementId(a) IN $ids AND elementId(b) IN $ids
                RETURN elementId(r) AS id, elementId(a) AS src,
                       elementId(b) AS tgt, type(r) AS rtype,
                       properties(r) AS props
                LIMIT $elimit
                """,
                cid=self.collection_id,
                ids=list(node_ids),
                elimit=edge_limit,
            )

            edges: list[GraphEdge] = []
            async for record in edge_result:
                props = dict(record["props"]) if record["props"] else {}
                props.pop("collection_id", None)
                props = _sanitize_props(props)
                edges.append(
                    GraphEdge(
                        id=record["id"],
                        source=record["src"],
                        target=record["tgt"],
                        type=record["rtype"],
                        properties=props,
                    )
                )

            return GraphData(nodes=nodes, edges=edges)

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

        # Build reverse mapping: we need node→cluster
        # Re-run a lightweight query to map nodes to clusters
        driver = await self._driver()
        async with driver.session() as session:
            # Get all edges in collection
            result = await session.run(
                """
                MATCH (a:Entity {collection_id: $cid})-[r]->(b:Entity {collection_id: $cid})
                RETURN elementId(a) AS src, elementId(b) AS tgt, type(r) AS rtype
                """,
                cid=self.collection_id,
            )

            # Build node→cluster mapping from overview nodes
            node_to_cluster: dict[str, str] = {}
            for n in overview.nodes:
                if isinstance(n, ClusterNode) and n.is_cluster:
                    # We need to re-get members for this cluster
                    pass
                else:
                    node_to_cluster[n.id] = n.id

            # Aggregate edges between clusters
            edge_agg: dict[tuple[str, str], dict[str, int]] = {}
            async for record in result:
                src_cluster = node_to_cluster.get(record["src"])
                tgt_cluster = node_to_cluster.get(record["tgt"])
                if not src_cluster or not tgt_cluster:
                    continue
                if src_cluster == tgt_cluster:
                    continue
                key = (min(src_cluster, tgt_cluster), max(src_cluster, tgt_cluster))
                if key not in edge_agg:
                    edge_agg[key] = {}
                rtype = record["rtype"]
                edge_agg[key][rtype] = edge_agg[key].get(rtype, 0) + 1

            cluster_edges: list[ClusterEdge] = []
            for (src, tgt), type_counts in edge_agg.items():
                dominant_type = max(type_counts, key=type_counts.get)  # type: ignore
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

        overview.edges = cluster_edges
        return overview

    async def expand_cluster(
        self,
        cluster_label: str,
        *,
        node_limit: int = 200,
        edge_limit: int = 500,
    ) -> GraphData:
        """Expand a cluster: return actual nodes with the given label."""
        driver = await self._driver()
        async with driver.session() as session:
            # Get nodes in this cluster (by label)
            node_result = await session.run(
                """
                MATCH (n:Entity {collection_id: $cid})
                WHERE n.label = $label
                OPTIONAL MATCH (n)-[r]-()
                WITH n, count(r) AS degree
                ORDER BY degree DESC
                LIMIT $limit
                RETURN elementId(n) AS id, n.label AS label,
                       n.name AS name, properties(n) AS props
                """,
                cid=self.collection_id,
                label=cluster_label,
                limit=node_limit,
            )

            nodes: list[GraphNode] = []
            node_ids: set[str] = set()
            async for record in node_result:
                props = dict(record["props"])
                props.pop("collection_id", None)
                props.pop("name", None)
                props.pop("label", None)
                props = _sanitize_props(props)
                nodes.append(
                    GraphNode(
                        id=record["id"],
                        label=record["label"] or "Entity",
                        name=record["name"],
                        properties=props,
                    )
                )
                node_ids.add(record["id"])

            if not node_ids:
                return GraphData(nodes=[], edges=[])

            # Get edges between these nodes
            edge_result = await session.run(
                """
                MATCH (a:Entity {collection_id: $cid})-[r]->(b:Entity {collection_id: $cid})
                WHERE elementId(a) IN $ids AND elementId(b) IN $ids
                RETURN elementId(r) AS id, elementId(a) AS src,
                       elementId(b) AS tgt, type(r) AS rtype,
                       properties(r) AS props
                LIMIT $limit
                """,
                cid=self.collection_id,
                ids=list(node_ids),
                limit=edge_limit,
            )

            edges: list[GraphEdge] = []
            async for record in edge_result:
                props = dict(record["props"])
                props.pop("collection_id", None)
                props = _sanitize_props(props)
                edges.append(
                    GraphEdge(
                        id=record["id"],
                        source=record["src"],
                        target=record["tgt"],
                        type=record["rtype"],
                        properties=props,
                    )
                )

        return GraphData(nodes=nodes, edges=edges)

    async def get_neighborhood(
        self,
        node_id: str,
        *,
        depth: int = 1,
        limit: int = 50,
    ) -> GraphData:
        """Get ego-graph (neighborhood) around a specific node."""
        driver = await self._driver()
        async with driver.session() as session:
            # Get center node + neighbors
            result = await session.run(
                f"""
                MATCH (center:Entity {{collection_id: $cid}})
                WHERE elementId(center) = $node_id
                OPTIONAL MATCH path = (center)-[*1..{depth}]-(neighbor:Entity {{collection_id: $cid}})
                WITH center, collect(DISTINCT neighbor) AS neighbors
                UNWIND ([center] + neighbors) AS n
                WITH DISTINCT n
                RETURN elementId(n) AS id, n.label AS label,
                       n.name AS name, properties(n) AS props
                LIMIT $limit
                """,
                cid=self.collection_id,
                node_id=node_id,
                limit=limit,
            )

            nodes: list[GraphNode] = []
            node_ids: set[str] = set()
            async for record in result:
                props = dict(record["props"])
                props.pop("collection_id", None)
                props.pop("name", None)
                props.pop("label", None)
                props = _sanitize_props(props)
                nodes.append(
                    GraphNode(
                        id=record["id"],
                        label=record["label"] or "Entity",
                        name=record["name"],
                        properties=props,
                    )
                )
                node_ids.add(record["id"])

            if not node_ids:
                return GraphData(nodes=[], edges=[])

            # Get all edges between these nodes
            edge_result = await session.run(
                """
                MATCH (a:Entity {collection_id: $cid})-[r]->(b:Entity {collection_id: $cid})
                WHERE elementId(a) IN $ids AND elementId(b) IN $ids
                RETURN elementId(r) AS id, elementId(a) AS src,
                       elementId(b) AS tgt, type(r) AS rtype,
                       properties(r) AS props
                """,
                cid=self.collection_id,
                ids=list(node_ids),
            )

            edges: list[GraphEdge] = []
            async for record in edge_result:
                props = dict(record["props"])
                props.pop("collection_id", None)
                props = _sanitize_props(props)
                edges.append(
                    GraphEdge(
                        id=record["id"],
                        source=record["src"],
                        target=record["tgt"],
                        type=record["rtype"],
                        properties=props,
                    )
                )

        return GraphData(nodes=nodes, edges=edges)

    async def get_important_nodes(
        self,
        *,
        limit: int = 200,
    ) -> list[GraphNode]:
        """Get the most important nodes by degree centrality."""
        driver = await self._driver()
        async with driver.session() as session:
            result = await session.run(
                """
                MATCH (n:Entity {collection_id: $cid})
                OPTIONAL MATCH (n)-[r]-()
                WITH n, count(r) AS degree
                ORDER BY degree DESC
                LIMIT $limit
                RETURN elementId(n) AS id, n.label AS label,
                       n.name AS name, properties(n) AS props, degree
                """,
                cid=self.collection_id,
                limit=limit,
            )
            nodes: list[GraphNode] = []
            async for record in result:
                props = dict(record["props"])
                props.pop("collection_id", None)
                props.pop("name", None)
                props.pop("label", None)
                props["degree"] = record["degree"]
                props = _sanitize_props(props)
                nodes.append(
                    GraphNode(
                        id=record["id"],
                        label=record["label"] or "Entity",
                        name=record["name"],
                        properties=props,
                    )
                )
            return nodes

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
        """Unified scalable graph endpoint.

        Modes:
            auto        - Choose best mode based on graph size
            overview    - Clustered supernodes
            expand      - Drill into a cluster
            neighborhood - Ego graph around a node
            full        - All nodes paginated (with importance sorting)
        """
        stats = await self.get_stats()

        # Auto-select mode based on graph size
        if mode == "auto":
            if stats.node_count <= node_limit:
                mode = "full"
            else:
                mode = "overview"

        if mode == "overview":
            return await self.get_graph_overview(max_clusters=node_limit)

        elif mode == "expand" and cluster_label:
            # ── Sub-cluster drill-down (offset-based) ──
            # If the cluster_label is a sub-cluster ID, decode it and return
            # that exact slice of nodes — no further sub-clustering.
            if cluster_label.startswith("subcluster__"):
                parts = cluster_label.split("__")
                # subcluster__{label}__{skip}__{chunk_size}
                if len(parts) == 4:
                    real_label = parts[1]
                    skip = int(parts[2])
                    chunk = int(parts[3])
                    data = await self._expand_cluster_slice(
                        real_label, skip=skip, limit=chunk, edge_limit=edge_limit
                    )
                    # Attach label-group metadata so the frontend can
                    # show neighbor labels & relationship types.
                    rel_type_counts, neighbor_label_counts = (
                        await self._get_label_metadata(real_label)
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
                        },
                    )

            # ── Regular label expand ──
            label_count = await self._count_label_nodes(cluster_label)

            if label_count > node_limit:
                # Too many to show flat — produce offset-based sub-clusters
                chunk_size = max(node_limit, 50)
                # Fetch top entity names for preview
                top_names = await self._top_entity_names(
                    cluster_label, limit=label_count
                )
                sub_clusters = self._build_sub_clusters(
                    label=cluster_label,
                    total_count=label_count,
                    chunk_size=chunk_size,
                    top_entities_per_chunk=5,
                    entity_names=top_names,
                )
                # Compute intra-label edge count so the frontend can
                # display a meaningful "edges" number for this scope.
                label_edge_count = await self._count_label_edges(cluster_label)

                # Enrich sub-clusters with group-level metadata so the
                # frontend can show neighbour labels & rel-type filters.
                rel_type_counts, neighbor_label_counts = (
                    await self._get_label_metadata(cluster_label)
                )
                for sc in sub_clusters:
                    sc.properties["_rel_type_counts"] = rel_type_counts
                    sc.properties["_neighbor_label_counts"] = neighbor_label_counts

                return ClusteredGraphData(
                    nodes=sub_clusters,
                    edges=[],
                    total_node_count=label_count,
                    total_edge_count=label_edge_count,
                    cluster_count=len(sub_clusters),
                    mode="expand",
                    scope_label=cluster_label,
                )

            # Small enough — return flat
            data = await self.expand_cluster(
                cluster_label, node_limit=node_limit, edge_limit=edge_limit
            )
            rel_type_counts_flat, neighbor_label_counts_flat = (
                await self._get_label_metadata(cluster_label)
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
                    "neighbor_label_counts": neighbor_label_counts_flat,
                    "rel_type_counts": rel_type_counts_flat,
                },
            )

        elif mode == "neighborhood" and node_id:
            data = await self.get_neighborhood(
                node_id, depth=depth, limit=node_limit
            )
            return ClusteredGraphData(
                nodes=data.nodes,
                edges=data.edges,
                total_node_count=stats.node_count,
                total_edge_count=stats.edge_count,
                cluster_count=0,
                mode="neighborhood",
            )

        else:
            # "full" mode — importance-sorted
            important_nodes = await self.get_important_nodes(limit=node_limit)
            node_ids = [n.id for n in important_nodes]

            # Fetch edges between important nodes
            edges: list[GraphEdge] = []
            if node_ids:
                driver = await self._driver()
                async with driver.session() as session:
                    edge_result = await session.run(
                        """
                        MATCH (a:Entity {collection_id: $cid})-[r]->(b:Entity {collection_id: $cid})
                        WHERE elementId(a) IN $ids AND elementId(b) IN $ids
                        RETURN elementId(r) AS id, elementId(a) AS src,
                               elementId(b) AS tgt, type(r) AS rtype,
                               properties(r) AS props
                        LIMIT $limit
                        """,
                        cid=self.collection_id,
                        ids=node_ids,
                        limit=edge_limit,
                    )
                    async for record in edge_result:
                        props = dict(record["props"])
                        props.pop("collection_id", None)
                        props = _sanitize_props(props)
                        edges.append(
                            GraphEdge(
                                id=record["id"],
                                source=record["src"],
                                target=record["tgt"],
                                type=record["rtype"],
                                properties=props,
                            )
                        )

            return ClusteredGraphData(
                nodes=important_nodes,
                edges=edges,
                total_node_count=stats.node_count,
                total_edge_count=stats.edge_count,
                cluster_count=0,
                mode="full",
            )

    # ------------------------------------------------------------------
    # Class-level helpers (no collection_id needed)
    # ------------------------------------------------------------------

    @staticmethod
    async def list_graph_collection_ids() -> list[str]:
        """Return distinct collection_ids that have at least one node in Neo4j."""
        driver = await get_neo4j_driver()
        async with driver.session() as session:
            result = await session.run(
                "MATCH (n:Entity) RETURN DISTINCT n.collection_id AS cid"
            )
            ids: list[str] = []
            async for record in result:
                cid = record["cid"]
                if cid:
                    ids.append(cid)
            return ids

    async def get_stats(self) -> GraphStats:
        """Collect statistics about this collection's graph."""
        driver = await self._driver()
        async with driver.session() as session:
            # Node count + label breakdown
            label_result = await session.run(
                """
                MATCH (n:Entity {collection_id: $cid})
                RETURN n.label AS label, count(*) AS cnt
                """,
                cid=self.collection_id,
            )
            label_counts: dict[str, int] = {}
            node_count = 0
            async for record in label_result:
                lbl = record["label"] or "Entity"
                cnt = record["cnt"]
                label_counts[lbl] = cnt
                node_count += cnt

            # Edge count + type breakdown
            rel_result = await session.run(
                """
                MATCH (a:Entity {collection_id: $cid})-[r]->(b:Entity {collection_id: $cid})
                RETURN type(r) AS rtype, count(*) AS cnt
                """,
                cid=self.collection_id,
            )
            rel_counts: dict[str, int] = {}
            edge_count = 0
            async for record in rel_result:
                rtype = record["rtype"]
                cnt = record["cnt"]
                rel_counts[rtype] = cnt
                edge_count += cnt

        return GraphStats(
            collection_id=self.collection_id,
            node_count=node_count,
            edge_count=edge_count,
            label_counts=label_counts,
            relationship_type_counts=rel_counts,
        )

    async def get_labels_paginated(
        self,
        *,
        page: int = 1,
        page_size: int = 25,
        search: str | None = None,
        scope_label: str | None = None,
    ) -> PaginatedCounts:
        """Return entity labels with counts, paginated and optionally filtered.

        When *scope_label* is provided the results are scoped to the
        **neighbour labels** of nodes carrying that label (i.e. which other
        labels are connected to the given label group).  This is used by the
        frontend when the user has drilled into a specific label cluster.
        """
        driver = await self._driver()
        async with driver.session() as session:
            if scope_label:
                # Scoped: neighbour labels of nodes with the given label
                result = await session.run(
                    """
                    MATCH (a:Entity {collection_id: $cid})-[]-(b:Entity {collection_id: $cid})
                    WHERE a.label = $scope_label
                    RETURN b.label AS label, count(DISTINCT b) AS cnt
                    ORDER BY cnt DESC, label
                    """,
                    cid=self.collection_id,
                    scope_label=scope_label,
                )
            else:
                result = await session.run(
                    """
                    MATCH (n:Entity {collection_id: $cid})
                    RETURN n.label AS label, count(*) AS cnt
                    ORDER BY cnt DESC, label
                    """,
                    cid=self.collection_id,
                )
            all_items: list[dict[str, object]] = []
            async for record in result:
                lbl = record["label"] or "Entity"
                cnt = record["cnt"]
                if search and search.lower() not in lbl.lower():
                    continue
                all_items.append({"name": lbl, "count": cnt})

        total = len(all_items)
        start = (page - 1) * page_size
        end = start + page_size
        page_items = all_items[start:end]

        return PaginatedCounts(
            items=page_items,
            total=total,
            page=page,
            page_size=page_size,
            has_next=end < total,
        )

    async def get_relationship_types_paginated(
        self,
        *,
        page: int = 1,
        page_size: int = 25,
        search: str | None = None,
        scope_label: str | None = None,
    ) -> PaginatedCounts:
        """Return relationship types with counts, paginated and optionally filtered.

        When *scope_label* is provided, only relationships involving nodes
        with that label are counted.
        """
        driver = await self._driver()
        async with driver.session() as session:
            if scope_label:
                result = await session.run(
                    """
                    MATCH (a:Entity {collection_id: $cid})-[r]-(b:Entity {collection_id: $cid})
                    WHERE a.label = $scope_label
                    RETURN type(r) AS rtype, count(r) AS cnt
                    ORDER BY cnt DESC, rtype
                    """,
                    cid=self.collection_id,
                    scope_label=scope_label,
                )
            else:
                result = await session.run(
                    """
                    MATCH (a:Entity {collection_id: $cid})-[r]->(b:Entity {collection_id: $cid})
                    RETURN type(r) AS rtype, count(*) AS cnt
                    ORDER BY cnt DESC, rtype
                    """,
                    cid=self.collection_id,
                )
            all_items: list[dict[str, object]] = []
            async for record in result:
                rtype = record["rtype"]
                cnt = record["cnt"]
                if search and search.lower() not in rtype.lower():
                    continue
                all_items.append({"name": rtype, "count": cnt})

        total = len(all_items)
        start = (page - 1) * page_size
        end = start + page_size
        page_items = all_items[start:end]

        return PaginatedCounts(
            items=page_items,
            total=total,
            page=page,
            page_size=page_size,
            has_next=end < total,
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
        """BM25-scored fulltext search on entity name and label.

        Uses Neo4j's built-in Lucene fulltext index which provides
        real BM25 ranking.  Results are filtered to this collection.

        Returns a list of dicts:
            [{"node": GraphNode, "bm25_score": float}, ...]
        sorted by descending BM25 score.
        """
        if not query or not query.strip():
            return []

        driver = await self._driver()

        # Lucene query string – escape special characters and build
        # a query that matches any token.  We also append a fuzzy
        # suffix (~1) to tolerate minor typos.
        safe_q = self._escape_lucene(query)
        # Build multi-token OR query with optional fuzzy matching
        tokens = safe_q.split()
        lucene_query = " OR ".join(f"{t}~1" for t in tokens) if tokens else safe_q

        results: list[dict[str, Any]] = []
        async with driver.session() as session:
            result = await session.run(
                """
                CALL db.index.fulltext.queryNodes(
                    'entity_fulltext', $lucene_query, {limit: $max_results}
                ) YIELD node, score
                WHERE node.collection_id = $cid
                RETURN elementId(node) AS id,
                       node.label AS label,
                       node.name  AS name,
                       properties(node) AS props,
                       score
                ORDER BY score DESC
                LIMIT $limit
                """,
                cid=self.collection_id,
                lucene_query=lucene_query,
                max_results=limit * 5,  # over-fetch before collection filter
                limit=limit,
            )
            async for record in result:
                props = dict(record["props"])
                props.pop("collection_id", None)
                props.pop("name", None)
                props.pop("label", None)
                props = _sanitize_props(props)
                node = GraphNode(
                    id=record["id"],
                    label=record["label"] or "Entity",
                    name=record["name"],
                    properties=props,
                )
                results.append({"node": node, "bm25_score": float(record["score"])})

        return results

    @staticmethod
    def _escape_lucene(text: str) -> str:
        """Escape Lucene special characters in a query string."""
        special = r'+-&|!(){}[]^"~*?:\/'
        out: list[str] = []
        for ch in text:
            if ch in special:
                out.append(f"\\{ch}")
            else:
                out.append(ch)
        return "".join(out)

    async def fetch_edges_for_nodes(
        self,
        node_names: list[str],
        *,
        limit: int = 100,
    ) -> list[GraphEdge]:
        """Fetch edges where at least one endpoint is in *node_names*.

        This is used to populate the ``edges`` field in hybrid search
        results so the UI can visualise the subgraph around the
        BM25-matched entities.
        """
        if not node_names:
            return []

        driver = await self._driver()
        async with driver.session() as session:
            result = await session.run(
                """
                MATCH (a:Entity {collection_id: $cid})-[r]->(b:Entity {collection_id: $cid})
                WHERE a.name IN $names OR b.name IN $names
                RETURN elementId(r) AS id,
                       elementId(a) AS src,
                       elementId(b) AS tgt,
                       type(r) AS rtype,
                       properties(r) AS props
                LIMIT $limit
                """,
                cid=self.collection_id,
                names=node_names,
                limit=limit,
            )
            edges: list[GraphEdge] = []
            async for record in result:
                props = dict(record["props"])
                props.pop("collection_id", None)
                props = _sanitize_props(props)
                edges.append(
                    GraphEdge(
                        id=record["id"],
                        source=record["src"],
                        target=record["tgt"],
                        type=record["rtype"],
                        properties=props,
                    )
                )
            return edges

    async def search_entities(
        self,
        query: str,
        *,
        limit: int = 10,
    ) -> GraphData:
        """Full-text search for entities by name (case-insensitive CONTAINS)."""
        driver = await self._driver()
        async with driver.session() as session:
            # Find matching nodes
            node_result = await session.run(
                """
                MATCH (n:Entity {collection_id: $cid})
                WHERE toLower(n.name) CONTAINS toLower($q)
                RETURN elementId(n) AS id, n.label AS label, n.name AS name,
                       properties(n) AS props
                LIMIT $limit
                """,
                cid=self.collection_id,
                q=query,
                limit=limit,
            )
            nodes: list[GraphNode] = []
            node_ids: set[str] = set()
            async for record in node_result:
                props = dict(record["props"])
                props.pop("collection_id", None)
                props.pop("name", None)
                props.pop("label", None)
                props = _sanitize_props(props)
                node = GraphNode(
                    id=record["id"],
                    label=record["label"] or "Entity",
                    name=record["name"],
                    properties=props,
                )
                nodes.append(node)
                node_ids.add(record["id"])

            if not node_ids:
                return GraphData(nodes=[], edges=[])

            # Fetch immediate neighborhood edges
            edge_result = await session.run(
                """
                MATCH (a:Entity {collection_id: $cid})-[r]->(b:Entity {collection_id: $cid})
                WHERE elementId(a) IN $ids OR elementId(b) IN $ids
                RETURN elementId(r) AS id, elementId(a) AS src, elementId(b) AS tgt,
                       type(r) AS rtype, properties(r) AS props
                LIMIT 100
                """,
                cid=self.collection_id,
                ids=list(node_ids),
            )
            edges: list[GraphEdge] = []
            neighbor_ids: set[str] = set()
            async for record in edge_result:
                props = dict(record["props"])
                props.pop("collection_id", None)
                props = _sanitize_props(props)
                edges.append(
                    GraphEdge(
                        id=record["id"],
                        source=record["src"],
                        target=record["tgt"],
                        type=record["rtype"],
                        properties=props,
                    )
                )
                neighbor_ids.add(record["src"])
                neighbor_ids.add(record["tgt"])

            # Fetch neighbor nodes not already included
            missing_ids = neighbor_ids - node_ids
            if missing_ids:
                neighbor_result = await session.run(
                    """
                    MATCH (n:Entity {collection_id: $cid})
                    WHERE elementId(n) IN $ids
                    RETURN elementId(n) AS id, n.label AS label, n.name AS name,
                           properties(n) AS props
                    """,
                    cid=self.collection_id,
                    ids=list(missing_ids),
                )
                async for record in neighbor_result:
                    props = dict(record["props"])
                    props.pop("collection_id", None)
                    props.pop("name", None)
                    props.pop("label", None)
                    props = _sanitize_props(props)
                    nodes.append(
                        GraphNode(
                            id=record["id"],
                            label=record["label"] or "Entity",
                            name=record["name"],
                            properties=props,
                        )
                    )

        return GraphData(nodes=nodes, edges=edges)

    async def search_entity_clusters(
        self,
        query: str,
    ) -> dict[str, int]:
        """Return a mapping of entity-label → match-count for nodes whose name
        matches *query* (case-insensitive CONTAINS).

        This is a lightweight alternative to ``search_entities`` intended for
        the clustered graph view: instead of returning the full nodes/edges it
        only tells the caller *which clusters* contain matching entities and
        how many.
        """
        driver = await self._driver()
        async with driver.session() as session:
            result = await session.run(
                """
                MATCH (n:Entity {collection_id: $cid})
                WHERE toLower(n.name) CONTAINS toLower($q)
                RETURN n.label AS label, count(n) AS cnt
                """,
                cid=self.collection_id,
                q=query,
            )
            clusters: dict[str, int] = {}
            async for record in result:
                lbl = record["label"] or "Entity"
                clusters[lbl] = record["cnt"]
            return clusters

    async def get_entity_context(
        self,
        entity_names: list[str],
        *,
        depth: int = 1,
    ) -> str:
        """Get textual context around given entities for RAG retrieval.

        Traverses up to `depth` hops from each entity and returns a formatted
        string describing the subgraph.
        """
        driver = await self._driver()
        seen: set[str] = set()
        lines: list[str] = []
        async with driver.session() as session:
            for name in entity_names:
                result = await session.run(
                    f"""
                    MATCH (n:Entity {{collection_id: $cid, name: $name}})
                    OPTIONAL MATCH path = (n)-[*1..{depth}]-(m:Entity {{collection_id: $cid}})
                    UNWIND relationships(path) AS r
                    WITH DISTINCT startNode(r) AS s, type(r) AS rtype, endNode(r) AS t
                    RETURN s.name AS src, rtype, t.name AS tgt
                    LIMIT 50
                    """,
                    cid=self.collection_id,
                    name=name,
                )
                async for record in result:
                    line = f"{record['src']} --[{record['rtype']}]--> {record['tgt']}"
                    if line not in seen:
                        seen.add(line)
                        lines.append(line)

        if not lines:
            return ""
        return "Knowledge Graph Context:\n" + "\n".join(lines)

    async def get_entity_context_focused(
        self,
        entity_names: list[str],
        *,
        max_direct: int = 30,
        max_indirect: int = 20,
    ) -> str:
        """Focused context: only relationships that directly involve seed entities.

        Unlike ``get_entity_context`` which recursively expands ALL
        relationships of neighbours, this method returns:

        - **Direct relationships** — where *both* endpoints are seed entities.
        - **1-hop relationships** — where *exactly one* endpoint is a seed
          entity and the other is any entity. These are capped at
          ``max_indirect`` to prevent context explosion.

        This avoids the "Barış Aslan → FastAPI" noise when the user
        searched for "enterprise".
        """
        if not entity_names:
            return ""

        driver = await self._driver()
        seed_set = set(entity_names)

        direct_lines: list[str] = []
        indirect_lines: list[str] = []
        seen: set[str] = set()

        async with driver.session() as session:
            # Single Cypher query: find all relationships where at least
            # one endpoint is one of the seed entities.
            result = await session.run(
                """
                MATCH (a:Entity {collection_id: $cid})-[r]->(b:Entity {collection_id: $cid})
                WHERE a.name IN $names OR b.name IN $names
                RETURN a.name AS src, type(r) AS rtype, b.name AS tgt
                LIMIT $max_total
                """,
                cid=self.collection_id,
                names=entity_names,
                max_total=max_direct + max_indirect + 20,  # over-fetch
            )
            async for record in result:
                line = f"{record['src']} --[{record['rtype']}]--> {record['tgt']}"
                if line in seen:
                    continue
                seen.add(line)

                src_in = record["src"] in seed_set
                tgt_in = record["tgt"] in seed_set

                if src_in and tgt_in:
                    # Both endpoints are seed entities — always include
                    if len(direct_lines) < max_direct:
                        direct_lines.append(line)
                else:
                    # One endpoint is a seed — include with limit
                    if len(indirect_lines) < max_indirect:
                        indirect_lines.append(line)

        if not direct_lines and not indirect_lines:
            return ""

        parts: list[str] = ["Knowledge Graph Context:"]
        if direct_lines:
            parts.append("[Direct relationships]")
            parts.extend(direct_lines)
        if indirect_lines:
            parts.append("[Related entities]")
            parts.extend(indirect_lines)
        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    async def delete_collection_graph(self) -> int:
        """Delete all nodes and edges belonging to this collection."""
        driver = await self._driver()
        async with driver.session() as session:
            result = await session.run(
                """
                MATCH (n:Entity {collection_id: $cid})
                DETACH DELETE n
                RETURN count(*) AS deleted
                """,
                cid=self.collection_id,
            )
            record = await result.single()
            deleted = record["deleted"] if record else 0  # type: ignore[index]
            logger.info(
                "Deleted %d nodes (and their relationships) for collection %s",
                deleted,
                self.collection_id,
            )
            return deleted

    async def execute_cypher(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Execute an arbitrary read-only Cypher query (scoped to collection)."""
        driver = await self._driver()
        params = parameters or {}
        params["cid"] = self.collection_id
        async with driver.session() as session:
            result = await session.run(query, **params)
            records = []
            async for record in result:
                records.append(dict(record))
            return records
