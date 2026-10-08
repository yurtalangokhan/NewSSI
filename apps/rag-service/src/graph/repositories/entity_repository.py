"""Repository — Entity CRUD (upsert, read, delete) and index management."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterator
from typing import Any

from error_contract import BadRequestError
from neo4j import READ_ACCESS, WRITE_ACCESS, Query
from neo4j.exceptions import ClientError

from src.graph.queries.entity import (
    BULK_UPSERT_EDGES_TEMPLATE,
    BULK_UPSERT_NODES,
    CREATE_COLLECTION_INDEX,
    CREATE_COMPOSITE_INDEX,
    CREATE_FULLTEXT_INDEX,
    DELETE_COLLECTION_GRAPH,
    GET_EDGES,
    GET_NODES,
    UPSERT_EDGE_TEMPLATE,
    UPSERT_NODE,
    normalize_relationship_type,
)
from src.graph.repositories.base import Neo4jRepository
from src.graph.schemas import GraphData, GraphEdge, GraphNode
from src.shared.observability import get_logger

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


#: Rows per statement. A whole extracted graph in one transaction would
#: hold a single lock set for its entire duration and buffer the whole list
#: server-side; chunking keeps each transaction short without giving up the
#: round-trip saving.
_BULK_CHUNK_SIZE = 1000


def _chunked(rows: list[dict[str, Any]]) -> Iterator[list[dict[str, Any]]]:
    """Yield successive _BULK_CHUNK_SIZE-sized slices of *rows*."""
    for start in range(0, len(rows), _BULK_CHUNK_SIZE):
        yield rows[start : start + _BULK_CHUNK_SIZE]


async def _upserted(result: Any) -> int:
    """Return the count a bulk statement reported, tolerating an empty result."""
    record = await result.single()
    return int(record["upserted"]) if record else 0


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
            except ClientError as exc:
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
        safe_type = normalize_relationship_type(rel_type)
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
                    "Edge not created - one or both nodes missing: %s -> %s",
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
        """Bulk upsert entities and relations. Returns counts.

        Sends one statement per chunk of nodes and one per relationship type
        per chunk, all on a single session. The previous implementation
        looped in Python over upsert_node/upsert_edge, so a document that
        extracted 200 entities and 400 relations opened 600 sessions and
        paid 600 sequential round-trips while the ingestion request waited.

        Nodes are written before edges because the edge statement MATCHes
        both endpoints -- the same ordering the loop relied on.
        """
        node_rows = [
            {
                "name": _normalize_name(entity["name"]),
                "label": entity.get("label", "Entity"),
                "props": entity.get("properties") or {},
            }
            for entity in entities
        ]

        # Relationship types cannot be parameterised in Cypher, so rows are
        # grouped by their (sanitised) type and each group gets its own
        # statement -- typically a small number of distinct types.
        edge_rows_by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for relation in relations:
            rel_type = normalize_relationship_type(relation.get("type", "RELATED_TO"))
            edge_rows_by_type[rel_type].append(
                {
                    "src": _normalize_name(relation["source"]),
                    "tgt": _normalize_name(relation["target"]),
                    "props": relation.get("properties") or {},
                }
            )

        if not node_rows and not edge_rows_by_type:
            return {"nodes": 0, "edges": 0}

        node_count = 0
        edge_count = 0
        async with self._session() as session:
            for chunk in _chunked(node_rows):
                result = await session.run(BULK_UPSERT_NODES, cid=self.cid, rows=chunk)
                node_count += await _upserted(result)

            for rel_type, rows in edge_rows_by_type.items():
                query = BULK_UPSERT_EDGES_TEMPLATE.format(rel_type=rel_type)
                for chunk in _chunked(rows):
                    result = await session.run(query, cid=self.cid, rows=chunk)
                    edge_count += await _upserted(result)

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
        *,
        read_only: bool = True,
        timeout_s: float = 30.0,
    ) -> list[dict[str, Any]]:
        """Execute an arbitrary Cypher query scoped to this collection.

        Defaults to a READ_ACCESS session so that a query reaching this
        method cannot write -- even for an administrator -- and bounds it
        with a server-side timeout so a pathological pattern cannot hold a
        connection open indefinitely. Access control (admin-only,
        collection ownership) is enforced by the caller (graph/router.py);
        this is the query-execution boundary, not the authorization one.
        """
        params = dict(parameters) if parameters else {}
        params["cid"] = self.cid
        access_mode = READ_ACCESS if read_only else WRITE_ACCESS
        async with self._session(default_access_mode=access_mode) as session:
            try:
                result = await session.run(Query(query, timeout=timeout_s), **params)
                return [dict(record) async for record in result]
            except ClientError as exc:
                if exc.code in {
                    "Neo.ClientError.Statement.SyntaxError",
                    "Neo.ClientError.Statement.ParameterMissing",
                    "Neo.ClientError.Statement.ParameterTypeError",
                    "Neo.ClientError.Statement.TypeError",
                }:
                    raise BadRequestError(code="graph.query_invalid") from exc
                raise
