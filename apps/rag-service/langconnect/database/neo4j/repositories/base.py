"""Base repository — shared Neo4j session management and record helpers.

All domain-specific repositories inherit from ``Neo4jRepository`` so that
session acquisition, property sanitisation and common mapping logic live
in exactly one place.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date, datetime, time, timedelta
from typing import Any

from neo4j import AsyncDriver, AsyncSession
from neo4j.time import (
    Date as Neo4jDate,
)
from neo4j.time import (
    DateTime as Neo4jDateTime,
)
from neo4j.time import (
    Duration as Neo4jDuration,
)
from neo4j.time import (
    Time as Neo4jTime,
)

from langconnect.database.neo4j.connection import get_neo4j_driver
from langconnect.models.graph import GraphEdge, GraphNode

logger = logging.getLogger(__name__)


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
        driver = await self._driver()
        async with driver.session(**kwargs) as session:
            yield session

    # ------------------------------------------------------------------
    # Record → DTO mapping
    # ------------------------------------------------------------------

    @staticmethod
    def _sanitize_props(props: dict[str, Any]) -> dict[str, Any]:
        """Convert Neo4j-specific temporal types to JSON-serialisable values."""
        clean: dict[str, Any] = {}
        for k, v in props.items():
            if (
                isinstance(v, Neo4jDateTime)
                or isinstance(v, Neo4jDate)
                or isinstance(v, Neo4jTime)
            ):
                clean[k] = v.to_native().isoformat()
            elif isinstance(v, Neo4jDuration):
                clean[k] = str(v)
            elif isinstance(v, (datetime, date, time)):
                clean[k] = v.isoformat()
            elif isinstance(v, timedelta):
                clean[k] = str(v)
            elif isinstance(v, list):
                clean[k] = [
                    Neo4jRepository._sanitize_props({"_": item})["_"]
                    if isinstance(item, dict)
                    else item
                    for item in v
                ]
            else:
                clean[k] = v
        return clean

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
    def _map_edge(cls, record: Any) -> GraphEdge:
        """Map a Cypher result record to a ``GraphEdge`` DTO."""
        return GraphEdge(
            id=record["id"],
            source=record["src"],
            target=record["tgt"],
            type=record["rtype"],
            properties=cls._clean_edge_props(record["props"]),
        )
