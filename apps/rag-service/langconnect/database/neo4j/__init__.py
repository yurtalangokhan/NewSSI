"""Neo4j database layer — Repository + DTO pattern.

This package provides a structured, enterprise-grade architecture for all
Neo4j / knowledge-graph operations:

- **connection** — Async driver lifecycle (singleton, health check).
- **queries/**   — All Cypher query strings as named constants.
- **repositories/** — Domain-specific repository classes with typed I/O.
- **graph_store** — High-level facade that delegates to the repositories.
"""

from langconnect.database.neo4j.connection import (
    check_neo4j_health,
    close_neo4j_driver,
    get_neo4j_driver,
)
from langconnect.database.neo4j.graph_store import GraphStore

__all__ = [
    "GraphStore",
    "check_neo4j_health",
    "close_neo4j_driver",
    "get_neo4j_driver",
]
