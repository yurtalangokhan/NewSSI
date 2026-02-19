"""Graph RAG orchestration service.

Coordinates the pipeline:
  1. Fetch document chunks from a PGVector collection.
  2. Run entity extraction (LLMGraphTransformer).
  3. Upsert extracted entities/relations into Neo4j.
  4. Provide hybrid search (vector + graph) with RRF scoring.
"""

import asyncio
import json
import logging
from typing import Any

from langconnect.database.collections import Collection, CollectionsManager
from langconnect.database.connection import get_db_connection, get_vectorstore
from langconnect.database.graph_store import GraphStore
from langconnect.models.graph import (
    BuildProgress,
    BuildStatus,
    ExtractionResult,
    GraphSearchResult,
)
from langconnect.services.entity_extractor import EntityExtractor

logger = logging.getLogger(__name__)

# In-memory build progress tracking (per collection)
_build_progress: dict[str, BuildProgress] = {}


def get_build_progress(collection_id: str) -> BuildProgress | None:
    """Get current build progress for a collection."""
    return _build_progress.get(collection_id)


class GraphRAGService:
    """Orchestrates the Graph RAG pipeline for a collection."""

    def __init__(self, collection_id: str, user_id: str = "internal-service") -> None:
        self.collection_id = collection_id
        self.user_id = user_id
        self.graph_store = GraphStore(collection_id)

    # ------------------------------------------------------------------
    # Build Pipeline
    # ------------------------------------------------------------------

    async def build_graph(
        self,
        entity_types: list[str] | None = None,
        relationship_types: list[str] | None = None,
    ) -> BuildProgress:
        """Build (or rebuild) the knowledge graph for the collection.

        Steps:
            1. Fetch all document chunks from PGVector.
            2. Extract entities/relations with LLMGraphTransformer.
            3. Upsert into Neo4j.
        """
        progress = BuildProgress(
            collection_id=self.collection_id,
            status=BuildStatus.PENDING,
        )
        _build_progress[self.collection_id] = progress

        try:
            # Ensure Neo4j indexes exist
            await self.graph_store.ensure_indexes()

            # 1. Fetch chunks
            progress.status = BuildStatus.EXTRACTING
            chunks = await self._fetch_all_chunks()
            progress.total_chunks = len(chunks)

            if not chunks:
                progress.status = BuildStatus.COMPLETED
                return progress

            # 2. Extract entities/relations
            extractor = EntityExtractor(
                allowed_nodes=entity_types,
                allowed_relationships=relationship_types,
            )

            all_entities: list[dict[str, Any]] = []
            all_relations: list[dict[str, Any]] = []

            for chunk in chunks:
                result: ExtractionResult = await extractor.extract_from_text(
                    text=chunk["content"],
                    chunk_id=chunk.get("id"),
                )
                for entity in result.entities:
                    all_entities.append(entity.model_dump())
                for relation in result.relations:
                    all_relations.append(relation.model_dump())

                progress.processed_chunks += 1
                progress.extracted_entities = len(all_entities)
                progress.extracted_relations = len(all_relations)

            # 3. Upsert into Neo4j
            progress.status = BuildStatus.BUILDING
            counts = await self.graph_store.bulk_upsert(all_entities, all_relations)
            logger.info(
                "Graph build complete for %s: %d nodes, %d edges",
                self.collection_id,
                counts["nodes"],
                counts["edges"],
            )

            progress.status = BuildStatus.COMPLETED

        except Exception as exc:
            logger.exception("Graph build failed for %s", self.collection_id)
            progress.status = BuildStatus.FAILED
            progress.error = str(exc)

        return progress

    async def _fetch_all_chunks(self) -> list[dict[str, Any]]:
        """Fetch all document chunks from the PGVector collection."""
        chunks: list[dict[str, Any]] = []
        async with get_db_connection() as conn:
            # Get the PGVector table name for this collection
            row = await conn.fetchrow(
                """
                SELECT name FROM langchain_pg_collection WHERE uuid = $1
                """,
                self.collection_id,
            )
            if not row:
                logger.warning("Collection %s not found in PGVector", self.collection_id)
                return []

            # Fetch all embedding documents
            records = await conn.fetch(
                """
                SELECT id, document, cmetadata
                FROM langchain_pg_embedding
                WHERE collection_id = $1
                ORDER BY id
                """,
                self.collection_id,
            )
            for r in records:
                metadata = json.loads(r["cmetadata"]) if r["cmetadata"] else {}
                chunks.append(
                    {
                        "id": str(r["id"]),
                        "content": r["document"] or "",
                        "metadata": metadata,
                    }
                )
        logger.info(
            "Fetched %d chunks from collection %s", len(chunks), self.collection_id
        )
        return chunks

    # ------------------------------------------------------------------
    # Hybrid Search (RRF + Cosine + BM25-style)
    # ------------------------------------------------------------------

    async def hybrid_search(
        self,
        query: str,
        *,
        limit: int = 10,
        vector_weight: float = 0.5,
        graph_weight: float = 0.5,
    ) -> GraphSearchResult:
        """Perform hybrid retrieval: vector similarity + graph traversal.

        Uses Reciprocal Rank Fusion (RRF) to combine results from both
        sources into a single ranked list.
        """
        # Run both searches concurrently
        vector_task = asyncio.create_task(self._vector_search(query, limit=limit))
        graph_task = asyncio.create_task(self._graph_search(query, limit=limit))

        vector_results, graph_results = await asyncio.gather(vector_task, graph_task)

        # RRF fusion — used only for RANKING (not for the displayed score)
        rrf_scores: dict[str, float] = {}
        rrf_k = 60  # standard RRF constant

        # Score vector results
        for rank, item in enumerate(vector_results):
            key = item.get("id", f"v_{rank}")
            rrf_scores[key] = rrf_scores.get(key, 0) + vector_weight / (rrf_k + rank + 1)

        # Score graph results (entity names as keys)
        for rank, node in enumerate(graph_results.nodes):
            key = node.name
            rrf_scores[key] = rrf_scores.get(key, 0) + graph_weight / (rrf_k + rank + 1)

        # Build combined context
        context_parts: list[str] = []

        # Vector context (cosine similarity results)
        if vector_results:
            context_parts.append("== Vector Search Results ==")
            for item in vector_results[:limit]:
                content = item.get("content", "")
                if content:
                    context_parts.append(content)

        # Graph context
        if graph_results.nodes:
            entity_names = [n.name for n in graph_results.nodes[:limit]]
            graph_context = await self.graph_store.get_entity_context(entity_names)
            if graph_context:
                context_parts.append("\n== Knowledge Graph Context ==")
                context_parts.append(graph_context)

        # Relevance score: use cosine similarity from vector search (true
        # semantic relevance, 0-1) weighted with a graph-presence bonus.
        # - vector_score: best cosine similarity from PGVector (0-1)
        # - graph_bonus:  1.0 if graph found matching entities, else 0.0
        # Final = vector_weight * vector_score + graph_weight * graph_bonus
        best_vector_score = max(
            (item.get("score", 0) for item in vector_results), default=0.0
        )
        graph_bonus = 1.0 if graph_results.nodes else 0.0
        relevance = vector_weight * best_vector_score + graph_weight * graph_bonus

        return GraphSearchResult(
            nodes=graph_results.nodes[:limit],
            edges=graph_results.edges,
            context="\n\n".join(context_parts),
            score=round(min(relevance, 1.0), 4),
        )

    async def _vector_search(
        self,
        query: str,
        *,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Cosine similarity search via PGVector."""
        try:
            collection = Collection(
                collection_id=self.collection_id,
                user_id=self.user_id,
            )
            results = await collection.search(query, limit=limit)
            return [
                {
                    "id": r.get("id", ""),
                    "content": r.get("page_content", ""),
                    "score": r.get("score", 0),
                }
                for r in results
            ]
        except Exception:
            logger.exception("Vector search failed for %s", self.collection_id)
            return []

    async def _graph_search(self, query: str, *, limit: int = 10):
        """Entity-based search in Neo4j."""
        try:
            return await self.graph_store.search_entities(query, limit=limit)
        except Exception:
            logger.exception("Graph search failed for %s", self.collection_id)
            from langconnect.models.graph import GraphData

            return GraphData(nodes=[], edges=[])
