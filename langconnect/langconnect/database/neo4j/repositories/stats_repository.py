"""Repository — Graph statistics (counts, paginated labels, rel types)."""

from __future__ import annotations

import logging

from langconnect.database.neo4j.queries.stats import (
    LABELS_PAGINATED_SCOPED,
    LABELS_PAGINATED_UNSCOPED,
    LABEL_COUNTS,
    LIST_GRAPH_COLLECTION_IDS,
    RELATIONSHIP_TYPE_COUNTS,
    RELATIONSHIP_TYPES_PAGINATED_SCOPED,
    RELATIONSHIP_TYPES_PAGINATED_UNSCOPED,
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

    async def get_stats(self) -> GraphStats:
        """Collect statistics about this collection's graph."""
        async with self._session() as session:
            # Node count + label breakdown
            label_result = await session.run(LABEL_COUNTS, cid=self.cid)
            label_counts: dict[str, int] = {}
            node_count = 0
            async for record in label_result:
                lbl = record["label"] or "Entity"
                cnt = record["cnt"]
                label_counts[lbl] = cnt
                node_count += cnt

            # Edge count + type breakdown
            rel_result = await session.run(RELATIONSHIP_TYPE_COUNTS, cid=self.cid)
            rel_counts: dict[str, int] = {}
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
    ) -> PaginatedCounts:
        """Return entity labels with counts (paginated, searchable)."""
        async with self._session() as session:
            if scope_label:
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
    ) -> PaginatedCounts:
        """Return relationship types with counts (paginated, searchable)."""
        async with self._session() as session:
            if scope_label:
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
