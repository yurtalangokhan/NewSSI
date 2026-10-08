"""Neo4j async driver connection management (singleton pattern).

Provides a single shared ``AsyncDriver`` instance for the entire application.
Repositories obtain sessions from this driver to execute Cypher queries.
"""

from __future__ import annotations

from config_manager import env
from error_contract import DatabaseConnectionError, DatabaseOperationError
from neo4j import AsyncDriver, AsyncGraphDatabase
from neo4j.exceptions import DriverError, Neo4jError

from src.shared.errors import database_errors
from src.shared.observability import get_logger

logger = get_logger(__name__)

# What a Neo4j call raises when the database is unreachable or rejects the
# query, as opposed to a programming error.
GRAPH_STORE_ERRORS: tuple[type[Exception], ...] = (DriverError, Neo4jError, OSError)

_driver: AsyncDriver | None = None


async def get_neo4j_driver() -> AsyncDriver:
    """Get or create the Neo4j async driver (singleton)."""
    global _driver
    if _driver is None:
        with database_errors():
            driver = AsyncGraphDatabase.driver(
                env.NEO4J_URI,
                auth=(env.NEO4J_USERNAME, env.NEO4J_PASSWORD),
            )
            try:
                await driver.verify_connectivity()
            except Exception:  # Release a failed candidate before propagating.
                await driver.close()
                raise
            _driver = driver
            logger.info("Neo4j connection established to %s", env.NEO4J_URI)
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
        with database_errors():
            driver = await get_neo4j_driver()
            await driver.verify_connectivity()
        return True
    except (DatabaseConnectionError, DatabaseOperationError):
        logger.exception("Neo4j health check failed")
        return False
