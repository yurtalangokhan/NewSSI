"""Graph RAG orchestration service.

Coordinates the pipeline:
  1. Fetch document chunks from a Milvus-backed vector collection.
  2. Run entity extraction (LLMGraphTransformer).
  3. Upsert extracted entities/relations into Neo4j.
  4. Provide hybrid search (vector + graph) with RRF scoring.
"""

import asyncio
import logging
from typing import Any

from fastapi import status

from langconnect.database.collections import Collection
from langconnect.database.neo4j import GraphStore
from langconnect.models.graph import (
    BuildProgress,
    BuildStatus,
    ExtractionResult,
    GraphData,
    GraphEdge,
    GraphNode,
    GraphSearchResult,
)
from langconnect.services.entity_extractor import EntityExtractor

logger = logging.getLogger(__name__)

# In-memory build progress tracking (per collection)
_build_progress: dict[str, BuildProgress] = {}


class _BuildControl:
    """In-memory cooperative control state for a running build."""

    def __init__(self) -> None:
        self.pause_event = asyncio.Event()
        self.pause_event.set()
        self.cancel_requested = False


_build_controls: dict[str, _BuildControl] = {}

_ACTIVE_BUILD_STATUSES: frozenset[BuildStatus] = frozenset(
    {
        BuildStatus.PENDING,
        BuildStatus.EXTRACTING,
        BuildStatus.BUILDING,
    }
)


def get_build_progress(collection_id: str) -> BuildProgress | None:
    """Get current build progress for a collection."""
    return _build_progress.get(collection_id)


def initialize_build_progress(collection_id: str) -> BuildProgress:
    """Pre-register a pending build record before the background task starts.

    This eliminates the race window where status polls return a stale
    'failed' record because the background task has not yet executed.
    """
    progress = BuildProgress(
        collection_id=collection_id,
        status=BuildStatus.PENDING,
    )
    _build_progress[collection_id] = progress
    return progress


def _get_active_build(collection_id: str) -> tuple[BuildProgress, _BuildControl] | None:
    """Return (progress, control) if a build is currently active, else None."""
    progress = _build_progress.get(collection_id)
    control = _build_controls.get(collection_id)
    if (
        progress is None
        or control is None
        or progress.status not in _ACTIVE_BUILD_STATUSES
    ):
        return None
    return progress, control


def request_pause_build(collection_id: str) -> BuildProgress | None:
    """Pause a running build for the given collection."""
    result = _get_active_build(collection_id)
    if result is None:
        return None
    progress, control = result
    control.pause_event.clear()
    progress.is_paused = True
    return progress


def request_resume_build(collection_id: str) -> BuildProgress | None:
    """Resume a paused running build for the given collection."""
    result = _get_active_build(collection_id)
    if result is None:
        return None
    progress, control = result
    control.pause_event.set()
    progress.is_paused = False
    return progress


def request_stop_build(collection_id: str) -> BuildProgress | None:
    """Request cancellation for a running build."""
    result = _get_active_build(collection_id)
    if result is None:
        return None
    progress, control = result
    control.cancel_requested = True
    control.pause_event.set()
    progress.is_paused = False
    return progress


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
            1. Fetch all document chunks from the vector store.
            2. Extract entities/relations with LLMGraphTransformer.
            3. Upsert into Neo4j.
        """
        # Re-use the record pre-registered by initialize_build_progress()
        # (called in the API endpoint before launching this background task).
        # If somehow not present, create a fresh record as a safety fallback.
        progress = _build_progress.get(self.collection_id) or BuildProgress(
            collection_id=self.collection_id,
            status=BuildStatus.PENDING,
        )
        _build_progress[self.collection_id] = progress
        control = _BuildControl()
        _build_controls[self.collection_id] = control

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
                await self._wait_if_paused_or_stopped(control)
                result: ExtractionResult = await extractor.extract_from_text(
                    text=chunk["content"],
                    chunk_id=chunk.get("id"),
                )
                all_entities.extend(entity.model_dump() for entity in result.entities)
                all_relations.extend(
                    relation.model_dump() for relation in result.relations
                )

                progress.processed_chunks += 1
                progress.extracted_entities = len(all_entities)
                progress.extracted_relations = len(all_relations)

            # 3. Upsert into Neo4j
            await self._wait_if_paused_or_stopped(control)
            progress.status = BuildStatus.BUILDING
            counts = await self.graph_store.bulk_upsert(all_entities, all_relations)
            logger.info(
                "Graph build complete for %s: %d nodes, %d edges",
                self.collection_id,
                counts["nodes"],
                counts["edges"],
            )

            progress.status = BuildStatus.COMPLETED

        except asyncio.CancelledError:
            logger.info("Graph build cancelled for %s", self.collection_id)
            progress.status = BuildStatus.FAILED
            progress.error = "Build was cancelled by user."

        except Exception as exc:
            logger.exception("Graph build failed for %s", self.collection_id)
            progress.status = BuildStatus.FAILED
            progress.error = str(exc)

        finally:
            _build_controls.pop(self.collection_id, None)

        return progress

    async def _wait_if_paused_or_stopped(self, control: _BuildControl) -> None:
        """Cooperative checkpoint for pause/resume/stop controls."""
        if control.cancel_requested:
            raise asyncio.CancelledError
        if not control.pause_event.is_set():
            await control.pause_event.wait()
        if control.cancel_requested:
            raise asyncio.CancelledError

    async def _fetch_all_chunks(self) -> list[dict[str, Any]]:
        """Fetch all document chunks from Milvus."""
        collection = Collection(collection_id=self.collection_id, user_id=self.user_id)
        return await collection.fetch_all_chunks()

    # ------------------------------------------------------------------
    # Hybrid Search (RRF: Vector Cosine + Graph BM25)
    # ------------------------------------------------------------------

    async def hybrid_search(
        self,
        query: str,
        *,
        limit: int = 10,
        vector_weight: float = 0.4,
        graph_weight: float = 0.6,
        include_vector_context: bool = False,
    ) -> GraphSearchResult:
        """Perform graph retrieval with optional vector-assisted RRF fusion.

        Retrieval signals:

        1. **Graph BM25** — Neo4j fulltext (Lucene) on entity names/labels.
        2. **Relationship type** — Neo4j relationship type intent matching.
        3. **Vector (cosine)** — optional Milvus similarity on embedded chunks.

        When vector context is enabled, RRF fusion is **entity-centric**:
        each entity receives an RRF
        contribution from *both* signals when it appears in both:
        - BM25 signal: entity rank → ``graph_weight / (k + rank + 1)``
        - Vector signal: for each ranked chunk, any BM25-matched entity
          whose name appears in the chunk content receives
          ``vector_weight / (k + chunk_rank + 1)``.

        Entities that appear in both signals accumulate a higher fused
        score than those found by only one signal.

        The final node list is **sorted by RRF score** and the overall
        relevance score is derived from the best RRF score.
        """
        # Run graph searches concurrently. Vector search is opt-in so a graph-only
        # agent does not search Milvus or return document snippets from Graph_Search.
        bm25_task = asyncio.create_task(self._graph_bm25_search(query, limit=limit))
        relationship_task = asyncio.create_task(
            self._relationship_type_search(query, limit=limit)
        )

        bm25_results, relationship_results = await asyncio.gather(
            bm25_task,
            relationship_task,
        )
        vector_results: list[dict[str, Any]] = []
        if include_vector_context:
            vector_results = await self._vector_search(query, limit=limit)

        # ----- Entity-centric RRF fusion -----
        rrf_k = 60  # standard RRF constant
        rrf_scores: dict[str, float] = {}

        # Lookup table: entity_name → {node, bm25_score}
        entity_lookup: dict[str, dict] = {}
        for hit in bm25_results:
            entity_lookup[hit["node"].name] = hit

        # Signal 1 — BM25: entities ranked by descending BM25 score
        for rank, hit in enumerate(bm25_results):
            name = hit["node"].name
            rrf_scores[name] = rrf_scores.get(name, 0) + graph_weight / (
                rrf_k + rank + 1
            )

        # Signal 2 — Vector: for each ranked chunk, find which
        # BM25-matched entity names appear in the chunk text.
        # Only the BEST (lowest) rank per entity is used to prevent
        # common entities (e.g. "RAG") from accumulating unfair scores
        # across many chunks.
        entity_names_lower = {n.lower(): n for n in entity_lookup}
        entity_best_vector_rank: dict[str, int] = {}  # name → best chunk rank
        for rank, item in enumerate(vector_results):
            content_lower = (item.get("content") or "").lower()
            if not content_lower:
                continue
            for name_lower, name in entity_names_lower.items():
                if name_lower in content_lower and (
                    name not in entity_best_vector_rank
                    or rank < entity_best_vector_rank[name]
                ):
                    entity_best_vector_rank[name] = rank

        for name, best_rank in entity_best_vector_rank.items():
            rrf_scores[name] = rrf_scores.get(name, 0) + vector_weight / (
                rrf_k + best_rank + 1
            )

        # Sort entities by fused RRF score (descending)
        sorted_entities = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)

        # Build ordered node list — attach rrf_score to properties
        merged_nodes: list = []
        seed_entity_names: list[str] = []
        for name, score in sorted_entities[:limit]:
            if name in entity_lookup:
                node = entity_lookup[name]["node"]
                merged_nodes.append(
                    GraphNode(
                        id=node.id,
                        label=node.label,
                        name=node.name,
                        properties={
                            **node.properties,
                            "rrf_score": round(score, 6),
                            "bm25_score": round(entity_lookup[name]["bm25_score"], 4),
                        },
                    )
                )
            seed_entity_names.append(name)

        # Safety: include any BM25 entities missing from RRF (shouldn't
        # happen, but guards against edge cases).
        seen_names = {n.name for n in merged_nodes}
        for hit in bm25_results:
            n = hit["node"].name
            if n not in seen_names and len(merged_nodes) < limit:
                merged_nodes.append(hit["node"])
                seed_entity_names.append(n)
                seen_names.add(n)

        seen_node_ids = {node.id for node in merged_nodes}
        for node in relationship_results.nodes:
            if node.id in seen_node_ids or len(merged_nodes) >= limit:
                continue
            merged_nodes.append(node)
            seed_entity_names.append(node.name)
            seen_node_ids.add(node.id)

        # ----- Fetch edges connecting the RRF-ranked entities -----
        matched_edges: list[GraphEdge] = []
        if seed_entity_names:
            try:
                matched_edges = await self.graph_store.fetch_edges_for_nodes(
                    seed_entity_names,
                    limit=limit * 10,
                )
            except Exception:
                logger.warning(
                    "Edge fetch failed for %s", self.collection_id, exc_info=True
                )

        seen_edge_ids = {edge.id for edge in matched_edges}
        for edge in relationship_results.edges:
            if edge.id not in seen_edge_ids:
                matched_edges.append(edge)
                seen_edge_ids.add(edge.id)

        # ----- Build combined context (RRF-ranked order) -----
        context_parts: list[str] = []

        # RRF-ranked entity summary
        if sorted_entities:
            context_parts.append("== RRF-Ranked Entities ==")
            for rank, (name, score) in enumerate(sorted_entities[:limit], 1):
                hit = entity_lookup.get(name)
                label = hit["node"].label if hit else "?"
                bm25 = hit["bm25_score"] if hit else 0
                # Show both scores: one from BM25, one from fused RRF
                in_vector = "yes" if name in entity_best_vector_rank else "no"
                context_parts.append(
                    f"  #{rank}  {label}: {name}  "
                    f"(RRF={score:.4f}  BM25={bm25:.3f}  vec={in_vector})"
                )

        relationship_context = self._format_relationship_context(relationship_results)
        if relationship_context:
            context_parts.append("== Relationship Matches ==")
            context_parts.append(relationship_context)

        # Knowledge graph context — focused on seed entities
        if seed_entity_names:
            graph_context = await self.graph_store.get_entity_context_focused(
                seed_entity_names[:limit],
            )
            if graph_context:
                context_parts.append("== Knowledge Graph Context ==")
                context_parts.append(graph_context)

        # Vector context supports graph-ranked entities, but Graph_Search must
        # not return vector-only content when no graph entity matched.
        has_graph_evidence = bool(sorted_entities or relationship_results.edges)
        if vector_results and has_graph_evidence:
            context_parts.append("== Vector Search Results ==")
            for item in vector_results[:limit]:
                content = item.get("content", "")
                if content:
                    context_parts.append(content)

        # ----- Overall relevance score from RRF -----
        # Max possible single-entity RRF = both signals at rank 0:
        #   vector_weight/(k+1) + graph_weight/(k+1) = 1/(k+1)
        max_possible_rrf = 1.0 / (rrf_k + 1)
        best_rrf = sorted_entities[0][1] if sorted_entities else 0.0
        relevance = best_rrf / max_possible_rrf if max_possible_rrf > 0 else 0.0
        if relationship_results.edges and relevance == 0:
            relevance = graph_weight

        return GraphSearchResult(
            nodes=merged_nodes,
            edges=matched_edges,
            context="\n\n".join(context_parts),
            score=round(min(relevance, 1.0), 4),
        )

    def _format_relationship_context(self, graph_data: GraphData) -> str:
        """Render matched relationship edges as graph-search context."""
        if not graph_data.edges:
            return ""

        nodes_by_id = {node.id: node for node in graph_data.nodes}
        lines: list[str] = []
        seen: set[str] = set()
        for edge in graph_data.edges:
            source = nodes_by_id.get(edge.source)
            target = nodes_by_id.get(edge.target)
            if source is None or target is None:
                continue
            line = f"{source.name} --[{edge.type}]--> {target.name}"
            if line not in seen:
                seen.add(line)
                lines.append(line)

        return "\n".join(lines)

    async def _vector_search(
        self,
        query: str,
        *,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Cosine similarity search via Milvus."""
        from fastapi.exceptions import HTTPException

        try:
            # Use "internal-service" to bypass owner_id check.
            # Datasource collections (created by agent-service) have no
            # owner_id in metadata, so a user-scoped lookup returns 404.
            # Auth is already enforced at the API endpoint layer.
            collection = Collection(
                collection_id=self.collection_id,
                user_id="internal-service",
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
        except HTTPException as exc:
            if exc.status_code == status.HTTP_404_NOT_FOUND:
                # Expected for datasource-only collections that have a
                # graph but no vector embeddings. BM25 will still work.
                logger.debug(
                    "No vector collection found for %s — graph-only mode",
                    self.collection_id,
                )
            else:
                logger.warning(
                    "Vector search HTTP error (%s) for %s",
                    exc.status_code,
                    self.collection_id,
                )
            return []
        except Exception:
            logger.exception("Vector search failed for %s", self.collection_id)
            return []

    async def _graph_bm25_search(
        self,
        query: str,
        *,
        limit: int = 10,
    ) -> list[dict]:
        """BM25-scored entity search via Neo4j fulltext index.

        Falls back to an empty list if the fulltext index hasn't been
        created yet (e.g. older graphs built before this feature).
        """
        try:
            return await self.graph_store.search_entities_bm25(query, limit=limit)
        except Exception:
            logger.warning(
                "BM25 graph search failed for %s (fulltext index may not exist yet)",
                self.collection_id,
                exc_info=True,
            )
            return []

    async def _relationship_type_search(
        self,
        query: str,
        *,
        limit: int = 10,
    ) -> GraphData:
        """Search by relationship type when the query names a relation."""
        try:
            return await self.graph_store.search_relationships_by_type(
                query,
                limit=limit,
            )
        except Exception:
            logger.warning(
                "Relationship type graph search failed for %s",
                self.collection_id,
                exc_info=True,
            )
            return GraphData(nodes=[], edges=[])
