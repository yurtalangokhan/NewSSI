"""Repository — Graph statistics (counts, paginated labels, rel types)."""

from __future__ import annotations

import logging

from langconnect.database.neo4j.queries.stats import (
    EDGE_COUNT_SCOPED,
    LABELS_FILTERED_BY_REL_TYPES,
    LABELS_PAGINATED_SCOPED,
    LABELS_PAGINATED_UNSCOPED,
    LABELS_SCOPED_FILTERED_BY_REL_TYPES,
    LABEL_COUNTS,
    LABEL_COUNTS_SCOPED,
    LIST_GRAPH_COLLECTION_IDS,
    NODE_COUNT_SCOPED,
    RELATIONSHIP_TYPE_COUNTS,
    RELATIONSHIP_TYPE_COUNTS_SCOPED,
    RELATIONSHIP_TYPES_CHUNK_SCOPED,
    RELATIONSHIP_TYPES_PAGINATED_SCOPED,
    RELATIONSHIP_TYPES_PAGINATED_UNSCOPED,
    REL_TYPES_FILTERED_BY_LABELS,
    REL_TYPES_SCOPED_FILTERED_BY_LABELS,
)
from langconnect.database.neo4j.repositories.base import Neo4jRepository
from langconnect.models.graph import GraphStats, PaginatedCounts

logger = logging.getLogger(__name__)


class StatsRepository(Neo4jRepository):
    """Read-only statistics and metadata queries."""

    # ------------------------------------------------------------------
    # Collection list (class-level — no collection_id needed)
    # ------------------------------------------------------------------

    @staticmethod
    async def list_graph_collection_ids() -> list[str]:
        """Return distinct collection_ids that have at least one node."""
        from langconnect.database.neo4j.connection import get_neo4j_driver

        driver = await get_neo4j_driver()
        async with driver.session() as session:
            result = await session.run(LIST_GRAPH_COLLECTION_IDS)
            ids: list[str] = []
            async for record in result:
                cid = record["cid"]
                if cid:
                    ids.append(cid)
            return ids

    # ------------------------------------------------------------------
    # Per-collection stats
    # ------------------------------------------------------------------

    async def get_stats(self, *, scope_label: str | None = None) -> GraphStats:
        """Collect statistics about this collection's graph.

        When *scope_label* is provided, counts are scoped to that label
        group: node_count = nodes with that label, edge_count = edges
        involving that label, label_counts = neighbour labels,
        relationship_type_counts = rel types involving that label.
        """
        async with self._session() as session:
            if scope_label:
                # Scoped node count
                nc_result = await session.run(
                    NODE_COUNT_SCOPED, cid=self.cid, scope_label=scope_label,
                )
                nc_record = await nc_result.single()
                node_count = nc_record["cnt"] if nc_record else 0

                # Scoped edge count
                ec_result = await session.run(
                    EDGE_COUNT_SCOPED, cid=self.cid, scope_label=scope_label,
                )
                ec_record = await ec_result.single()
                edge_count = ec_record["cnt"] if ec_record else 0

                # Scoped label breakdown (neighbour labels)
                label_result = await session.run(
                    LABEL_COUNTS_SCOPED, cid=self.cid, scope_label=scope_label,
                )
                label_counts: dict[str, int] = {}
                async for record in label_result:
                    lbl = record["label"] or "Entity"
                    label_counts[lbl] = record["cnt"]

                # Scoped relationship type breakdown
                rel_result = await session.run(
                    RELATIONSHIP_TYPE_COUNTS_SCOPED,
                    cid=self.cid,
                    scope_label=scope_label,
                )
                rel_counts: dict[str, int] = {}
                async for record in rel_result:
                    rel_counts[record["rtype"]] = record["cnt"]
            else:
                # Global stats
                label_result = await session.run(LABEL_COUNTS, cid=self.cid)
                label_counts = {}
                node_count = 0
                async for record in label_result:
                    lbl = record["label"] or "Entity"
                    cnt = record["cnt"]
                    label_counts[lbl] = cnt
                    node_count += cnt

                rel_result = await session.run(
                    RELATIONSHIP_TYPE_COUNTS, cid=self.cid,
                )
                rel_counts = {}
                edge_count = 0
                async for record in rel_result:
                    rtype = record["rtype"]
                    cnt = record["cnt"]
                    rel_counts[rtype] = cnt
                    edge_count += cnt

        return GraphStats(
            collection_id=self.cid,
            node_count=node_count,
            edge_count=edge_count,
            label_counts=label_counts,
            relationship_type_counts=rel_counts,
        )

    # ------------------------------------------------------------------
    # Paginated labels
    # ------------------------------------------------------------------

    async def get_labels_paginated(
        self,
        *,
        page: int = 1,
        page_size: int = 25,
        search: str | None = None,
        scope_label: str | None = None,
        rel_type_filter: list[str] | None = None,
    ) -> PaginatedCounts:
        """Return entity labels with counts (paginated, searchable).

        When *rel_type_filter* is provided, only labels of nodes
        participating in those relationship types are returned.
        """
        async with self._session() as session:
            if rel_type_filter:
                # Cross-filtered by relationship types
                if scope_label:
                    result = await session.run(
                        LABELS_SCOPED_FILTERED_BY_REL_TYPES,
                        cid=self.cid,
                        scope_label=scope_label,
                        rel_types=rel_type_filter,
                    )
                else:
                    result = await session.run(
                        LABELS_FILTERED_BY_REL_TYPES,
                        cid=self.cid,
                        rel_types=rel_type_filter,
                    )
            elif scope_label:
                result = await session.run(
                    LABELS_PAGINATED_SCOPED,
                    cid=self.cid,
                    scope_label=scope_label,
                )
            else:
                result = await session.run(
                    LABELS_PAGINATED_UNSCOPED,
                    cid=self.cid,
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

    # ------------------------------------------------------------------
    # Paginated relationship types
    # ------------------------------------------------------------------

    async def get_relationship_types_paginated(
        self,
        *,
        page: int = 1,
        page_size: int = 25,
        search: str | None = None,
        scope_label: str | None = None,
        scope_skip: int | None = None,
        scope_limit: int | None = None,
        label_filter: list[str] | None = None,
    ) -> PaginatedCounts:
        """Return relationship types with counts (paginated, searchable).

        When *scope_skip* and *scope_limit* are provided alongside
        *scope_label*, counts are scoped to the specific chunk of nodes
        (ordered by degree desc) rather than the entire label group.

        When *label_filter* is provided, only relationship types
        involving nodes with those labels are returned.
        """
        async with self._session() as session:
            if scope_label and scope_skip is not None and scope_limit is not None:
                # Chunk-scoped: only edges within the node chunk
                result = await session.run(
                    RELATIONSHIP_TYPES_CHUNK_SCOPED,
                    cid=self.cid,
                    scope_label=scope_label,
                    scope_skip=scope_skip,
                    scope_end=scope_skip + scope_limit,
                )
            elif label_filter:
                # Cross-filtered by labels
                if scope_label:
                    result = await session.run(
                        REL_TYPES_SCOPED_FILTERED_BY_LABELS,
                        cid=self.cid,
                        scope_label=scope_label,
                        labels=label_filter,
                    )
                else:
                    result = await session.run(
                        REL_TYPES_FILTERED_BY_LABELS,
                        cid=self.cid,
                        labels=label_filter,
                    )
            elif scope_label:
                result = await session.run(
                    RELATIONSHIP_TYPES_PAGINATED_SCOPED,
                    cid=self.cid,
                    scope_label=scope_label,
                )
            else:
                result = await session.run(
                    RELATIONSHIP_TYPES_PAGINATED_UNSCOPED,
                    cid=self.cid,
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
