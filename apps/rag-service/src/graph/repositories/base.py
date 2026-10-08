"""Base repository — shared Neo4j session management and record helpers.

All domain-specific repositories inherit from ``Neo4jRepository`` so that
session acquisition, property sanitisation and common mapping logic live
in exactly one place.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date, datetime, time, timedelta
from typing import Any

from neo4j import AsyncDriver, AsyncSession
from neo4j.time import (
    Date as Neo4jDate,
    DateTime as Neo4jDateTime,
    Duration as Neo4jDuration,
    Time as Neo4jTime,
)

from src.graph.connection import get_neo4j_driver
from src.graph.schemas import GraphEdge, GraphNode
from src.shared.errors import database_errors
from src.shared.observability import get_logger

logger = get_logger(__name__)


def sanitize_neo4j_value(value: Any) -> Any:
    """Convert any Neo4j driver value into a JSON-serialisable Python value.

    The single canonical conversion for every place that hands a raw Neo4j
    record or property value back over HTTP: node/edge properties (via
    ``Neo4jRepository._sanitize_props``) and arbitrary admin-Cypher result
    rows (``graph/router.py``'s ``execute_cypher``) used to each carry their
    own copy, and had drifted -- the admin-Cypher path fell back to
    ``str()`` for a Neo4j temporal value instead of converting it, so the
    same timestamp came back formatted differently depending on which
    endpoint returned it. Recurses into lists/tuples/dicts so a temporal
    value nested inside either is converted too, not just top-level ones.
    """
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, Neo4jDateTime | Neo4jDate | Neo4jTime):
        return value.to_native().isoformat()
    if isinstance(value, Neo4jDuration):
        return str(value)
    if isinstance(value, datetime | date | time):
        return value.isoformat()
    if isinstance(value, timedelta):
        return str(value)
    if isinstance(value, list | tuple):
        return [sanitize_neo4j_value(v) for v in value]
    if isinstance(value, dict):
        return {k: sanitize_neo4j_value(v) for k, v in value.items()}
    # Fallback: anything not covered above (e.g. a raw Node/Relationship
    # from an admin query that didn't project properties()) becomes its
    # string representation rather than failing the response.
    return str(value)


class Neo4jRepository:
    """Lightweight base providing driver access and record mapping utilities.

    Subclasses receive a ``collection_id`` at construction time and use
    the helper methods below to run Cypher without touching the driver
    or session lifecycle directly.

    Usage in subclass::

        async def get_something(self) -> list[GraphNode]:
            async with self._session() as session:
                result = await session.run(MY_QUERY, cid=self.cid)
                return [self._map_node(r) async for r in result]
    """

    def __init__(self, collection_id: str) -> None:
        self.cid = collection_id

    # ------------------------------------------------------------------
    # Driver / Session helpers
    # ------------------------------------------------------------------

    async def _driver(self) -> AsyncDriver:
        """Return the shared singleton driver."""
        return await get_neo4j_driver()

    @asynccontextmanager
    async def _session(self, **kwargs: Any) -> AsyncIterator[AsyncSession]:
        """Yield an ``AsyncSession`` as a proper async context manager.

        Usage::

            async with self._session() as session:
                result = await session.run(...)
        """
        with database_errors():
            driver = await self._driver()
            async with driver.session(**kwargs) as session:
                yield session

    # ------------------------------------------------------------------
    # Record → DTO mapping
    # ------------------------------------------------------------------

    @staticmethod
    def _sanitize_props(props: dict[str, Any]) -> dict[str, Any]:
        """Convert Neo4j-specific temporal types to JSON-serialisable values."""
        return {k: sanitize_neo4j_value(v) for k, v in props.items()}

    @classmethod
    def _clean_node_props(cls, raw_props: dict[str, Any]) -> dict[str, Any]:
        """Remove internal bookkeeping keys and sanitise temporal types."""
        props = dict(raw_props)
        props.pop("collection_id", None)
        props.pop("name", None)
        props.pop("label", None)
        return cls._sanitize_props(props)

    @classmethod
    def _clean_edge_props(cls, raw_props: dict[str, Any] | None) -> dict[str, Any]:
        """Remove internal bookkeeping keys and sanitise temporal types."""
        props = dict(raw_props) if raw_props else {}
        props.pop("collection_id", None)
        return cls._sanitize_props(props)

    @classmethod
    def _map_node(cls, record: Any) -> GraphNode:
        """Map a Cypher result record to a ``GraphNode`` DTO."""
        return GraphNode(
            id=record["id"],
            label=record["label"] or "Entity",
            name=record["name"],
            properties=cls._clean_node_props(record["props"]),
        )

    @classmethod
    def _map_edge(cls, record: Any, *, source_key: str = "src", target_key: str = "tgt") -> GraphEdge:
        """Map a Cypher result record to a ``GraphEdge`` DTO.

        ``source_key`` and ``target_key`` name the record columns that hold the
        endpoint ids.
        """
        return GraphEdge(
            id=record["id"],
            source=record[source_key],
            target=record[target_key],
            type=record["rtype"],
            properties=cls._clean_edge_props(record["props"]),
        )
