"""Repository — Search (BM25, CONTAINS, entity clusters, context for RAG)."""

from __future__ import annotations

import logging
from typing import Any

from langconnect.database.neo4j.queries.search import (
    BM25_SEARCH,
    ENTITY_CONTEXT_FOCUSED,
    ENTITY_CONTEXT_TEMPLATE,
    FETCH_EDGES_FOR_NAMES,
    FETCH_NODES_BY_IDS,
    SEARCH_ENTITIES_CONTAINS,
    SEARCH_ENTITY_CLUSTERS,
    SEARCH_SUBCLUSTERS,
    SEARCH_NEIGHBORHOOD_EDGES,
)
from langconnect.database.neo4j.repositories.base import Neo4jRepository
from langconnect.models.graph import GraphData, GraphEdge, GraphNode

logger = logging.getLogger(__name__)


class SearchRepository(Neo4jRepository):
    """Full-text and graph-based entity search operations."""

    # ------------------------------------------------------------------
    # BM25 (Lucene fulltext)
    # ------------------------------------------------------------------

    async def search_entities_bm25(
        self,
        query: str,
        *,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """BM25-scored fulltext search on entity name and label.

        Returns ``[{"node": GraphNode, "bm25_score": float}, ...]``
        sorted by descending BM25 score.
        """
        if not query or not query.strip():
            return []

        safe_q = self._escape_lucene(query)
        tokens = safe_q.split()
        lucene_query = " OR ".join(f"{t}~1" for t in tokens) if tokens else safe_q

        results: list[dict[str, Any]] = []
        async with self._session() as session:
            result = await session.run(
                BM25_SEARCH,
                cid=self.cid,
                lucene_query=lucene_query,
                max_results=limit * 5,
                limit=limit,
            )
            async for record in result:
                node = self._map_node(record)
                results.append({"node": node, "bm25_score": float(record["score"])})
        return results

    # ------------------------------------------------------------------
    # Case-insensitive CONTAINS search
    # ------------------------------------------------------------------

    async def search_entities(
        self,
        query: str,
        *,
        limit: int = 10,
    ) -> GraphData:
        """Full-text search for entities by name (case-insensitive CONTAINS)."""
        async with self._session() as session:
            node_result = await session.run(
                SEARCH_ENTITIES_CONTAINS,
                cid=self.cid,
                q=query,
                limit=limit,
            )
            nodes: list[GraphNode] = []
            node_ids: set[str] = set()
            async for record in node_result:
                node = self._map_node(record)
                nodes.append(node)
                node_ids.add(record["id"])

            if not node_ids:
                return GraphData(nodes=[], edges=[])

            # Fetch immediate neighbourhood edges
            edge_result = await session.run(
                SEARCH_NEIGHBORHOOD_EDGES,
                cid=self.cid,
                ids=list(node_ids),
            )
            edges: list[GraphEdge] = []
            neighbor_ids: set[str] = set()
            async for record in edge_result:
                edges.append(self._map_edge(record))
                neighbor_ids.add(record["src"])
                neighbor_ids.add(record["tgt"])

            # Fetch neighbour nodes not already included
            missing_ids = neighbor_ids - node_ids
            if missing_ids:
                neighbor_result = await session.run(
                    FETCH_NODES_BY_IDS,
                    cid=self.cid,
                    ids=list(missing_ids),
                )
                async for record in neighbor_result:
                    nodes.append(self._map_node(record))

        return GraphData(nodes=nodes, edges=edges)

    # ------------------------------------------------------------------
    # Edges for named nodes
    # ------------------------------------------------------------------

    async def fetch_edges_for_nodes(
        self,
        node_names: list[str],
        *,
        limit: int = 100,
    ) -> list[GraphEdge]:
        """Fetch edges where at least one endpoint is in *node_names*."""
        if not node_names:
            return []
        async with self._session() as session:
            result = await session.run(
                FETCH_EDGES_FOR_NAMES,
                cid=self.cid,
                names=node_names,
                limit=limit,
            )
            return [self._map_edge(record) async for record in result]

    # ------------------------------------------------------------------
    # Entity cluster search (label → count)
    # ------------------------------------------------------------------

    async def search_entity_clusters(
        self, query: str, scope_label: str | None = None, chunk_size: int = 200
    ) -> dict[str, int]:
        """Return counts for clusters matching *query*.
        If scope_label is provided, returns counts per sub-cluster chunk matching the expand logic.
        """
        async with self._session() as session:
            if scope_label:
                result = await session.run(
                    SEARCH_SUBCLUSTERS,
                    cid=self.cid,
                    q=query,
                    scope_label=scope_label,
                    chunk_size=chunk_size,
                )
                clusters: dict[str, int] = {}
                async for record in result:
                    offset = record["offset"]
                    cnt = record["cnt"]
                    chunk_id = f"subcluster__{scope_label}__{offset}__{chunk_size}"
                    clusters[chunk_id] = cnt
                return clusters
            else:
                result = await session.run(
                    SEARCH_ENTITY_CLUSTERS,
                    cid=self.cid,
                    q=query,
                )
                clusters: dict[str, int] = {}
                async for record in result:
                    clusters[record["label"] or "Entity"] = record["cnt"]
                return clusters

    # ------------------------------------------------------------------
    # Entity context for RAG
    # ------------------------------------------------------------------

    async def get_entity_context(
        self,
        entity_names: list[str],
        *,
        depth: int = 1,
    ) -> str:
        """Textual context around given entities (recursive traversal)."""
        seen: set[str] = set()
        lines: list[str] = []
        async with self._session() as session:
            for name in entity_names:
                query = ENTITY_CONTEXT_TEMPLATE.format(depth=depth)
                result = await session.run(
                    query,
                    cid=self.cid,
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
        """Focused context: only relationships directly involving seed entities.

        Separates direct relationships (both endpoints are seeds) from
        1-hop relationships (one endpoint is a seed) and caps the latter
        to prevent context explosion.
        """
        if not entity_names:
            return ""

        seed_set = set(entity_names)
        direct_lines: list[str] = []
        indirect_lines: list[str] = []
        seen: set[str] = set()

        async with self._session() as session:
            result = await session.run(
                ENTITY_CONTEXT_FOCUSED,
                cid=self.cid,
                names=entity_names,
                max_total=max_direct + max_indirect + 20,
            )
            async for record in result:
                line = f"{record['src']} --[{record['rtype']}]--> {record['tgt']}"
                if line in seen:
                    continue
                seen.add(line)

                src_in = record["src"] in seed_set
                tgt_in = record["tgt"] in seed_set

                if src_in and tgt_in:
                    if len(direct_lines) < max_direct:
                        direct_lines.append(line)
                else:
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
    # Helpers
    # ------------------------------------------------------------------

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
