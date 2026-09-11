"""Repository — Entity CRUD (upsert, read, delete) and index management."""

from __future__ import annotations

from typing import Any

from langconnect.database.neo4j.queries.entity import (
    CREATE_COLLECTION_INDEX,
    CREATE_COMPOSITE_INDEX,
    CREATE_FULLTEXT_INDEX,
    DELETE_COLLECTION_GRAPH,
    GET_EDGES,
    GET_NODES,
    UPSERT_EDGE_TEMPLATE,
    UPSERT_NODE,
)
from langconnect.database.neo4j.repositories.base import Neo4jRepository
from langconnect.models.graph import GraphData, GraphEdge, GraphNode
from langconnect.observability import get_logger

logger = get_logger(__name__)


def _normalize_name(name: str) -> str:
    """Normalise entity names for consistent Neo4j matching.

    Strips whitespace, collapses inner whitespace, and applies Title Case
    so that 'iran\'s missile arsenal' and 'Iran\'S Missile Arsenal' resolve
    to the same node.
    """
    import re

    name = name.strip()
    name = re.sub(r"\s+", " ", name)
    # Title-case but preserve apostrophe contractions:
    # "Iran's" → "Iran's" not "Iran'S"
    parts = name.split(" ")
    normalised: list[str] = []
    for part in parts:
        if "'" in part:
            # Capitalise only the first letter; lowercase after apostrophe
            idx = part.index("'")
            part = part[:idx].capitalize() + "'" + part[idx + 1 :].lower()
        else:
            part = part.capitalize()
        normalised.append(part)
    return " ".join(normalised)


class EntityRepository(Neo4jRepository):
    """CRUD operations for Entity nodes and their relationships."""

    # ------------------------------------------------------------------
    # Index management
    # ------------------------------------------------------------------

    async def ensure_indexes(self) -> None:
        """Create composite + fulltext indexes (idempotent)."""
        async with self._session() as session:
            await session.run(CREATE_COMPOSITE_INDEX)
            await session.run(CREATE_COLLECTION_INDEX)
            try:
                await session.run(CREATE_FULLTEXT_INDEX)
                logger.info(
                    "Neo4j fulltext (BM25) index ensured for collection %s",
                    self.cid,
                )
            except Exception as exc:
                logger.warning("Fulltext index creation note: %s", exc)
            logger.info("Neo4j indexes ensured for collection %s", self.cid)

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
        name = _normalize_name(name)
        props = properties or {}
        async with self._session() as session:
            result = await session.run(
                UPSERT_NODE,
                cid=self.cid,
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
        source_name = _normalize_name(source_name)
        target_name = _normalize_name(target_name)
        props = properties or {}
        safe_type = rel_type.upper().replace(" ", "_").replace("-", "_")
        query = UPSERT_EDGE_TEMPLATE.format(rel_type=safe_type)
        async with self._session() as session:
            result = await session.run(
                query,
                cid=self.cid,
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
        label_clause = "WHERE n.label = $label" if label_filter else ""
        query = GET_NODES.format(label_clause=label_clause)
        async with self._session() as session:
            result = await session.run(
                query,
                cid=self.cid,
                label=label_filter,
                offset=offset,
                limit=limit,
            )
            return [self._map_node(record) async for record in result]

    async def get_edges(
        self,
        *,
        limit: int = 200,
        offset: int = 0,
    ) -> list[GraphEdge]:
        """List edges in this collection."""
        async with self._session() as session:
            result = await session.run(
                GET_EDGES,
                cid=self.cid,
                offset=offset,
                limit=limit,
            )
            return [self._map_edge(record) async for record in result]

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
    # Delete
    # ------------------------------------------------------------------

    async def delete_collection_graph(self) -> int:
        """Delete all nodes and edges belonging to this collection."""
        async with self._session() as session:
            result = await session.run(DELETE_COLLECTION_GRAPH, cid=self.cid)
            record = await result.single()
            deleted = record["deleted"] if record else 0  # type: ignore[index]
            logger.info(
                "Deleted %d nodes (and their relationships) for collection %s",
                deleted,
                self.cid,
            )
            return deleted

    # ------------------------------------------------------------------
    # Arbitrary Cypher
    # ------------------------------------------------------------------

    async def execute_cypher(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Execute an arbitrary Cypher query scoped to this collection."""
        params = dict(parameters) if parameters else {}
        params["cid"] = self.cid
        async with self._session() as session:
            result = await session.run(query, **params)
            records: list[dict[str, Any]] = []
            async for record in result:
                records.append(dict(record))
            return records
