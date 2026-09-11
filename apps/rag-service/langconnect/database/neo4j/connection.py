"""Neo4j async driver connection management (singleton pattern).

Provides a single shared ``AsyncDriver`` instance for the entire application.
Repositories obtain sessions from this driver to execute Cypher queries.
"""

from __future__ import annotations

from neo4j import AsyncDriver, AsyncGraphDatabase

from langconnect import config
from langconnect.observability import get_logger

logger = get_logger(__name__)

_driver: AsyncDriver | None = None


async def get_neo4j_driver() -> AsyncDriver:
    """Get or create the Neo4j async driver (singleton)."""
    global _driver
    if _driver is None:
        _driver = AsyncGraphDatabase.driver(
            config.NEO4J_URI,
            auth=(config.NEO4J_USERNAME, config.NEO4J_PASSWORD),
        )
        try:
            await _driver.verify_connectivity()
            logger.info("Neo4j connection established to %s", config.NEO4J_URI)
        except Exception:
            logger.exception("Failed to connect to Neo4j at %s", config.NEO4J_URI)
            raise
    return _driver


async def close_neo4j_driver() -> None:
    """Close the Neo4j async driver."""
    global _driver
    if _driver is not None:
        await _driver.close()
        _driver = None
        logger.info("Neo4j driver closed.")


async def check_neo4j_health() -> bool:
    """Check if Neo4j is reachable."""
    try:
        driver = await get_neo4j_driver()
        await driver.verify_connectivity()
        return True
    except Exception:
        logger.exception("Neo4j health check failed")
        return False
