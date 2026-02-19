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
        """Create indexes for efficient lookups (idempotent)."""
        driver = await self._driver()
        async with driver.session() as session:
            # Composite index on (collection_id, name) for fast entity lookup
            await session.run(
                "CREATE INDEX IF NOT EXISTS FOR (n:Entity) ON (n.collection_id, n.name)"
            )
            await session.run(
                "CREATE INDEX IF NOT EXISTS FOR (n:Entity) ON (n.collection_id)"
            )
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
    ) -> PaginatedCounts:
        """Return entity labels with counts, paginated and optionally filtered."""
        driver = await self._driver()
        async with driver.session() as session:
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
    ) -> PaginatedCounts:
        """Return relationship types with counts, paginated and optionally filtered."""
        driver = await self._driver()
        async with driver.session() as session:
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
