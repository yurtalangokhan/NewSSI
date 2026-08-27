"""Airbyte mapping repository facade.

Canonical location for the ``AirbyteMappingDB`` facade that delegates to
:class:`~core.db.repositories.AirbyteMappingRepository`.

Manages the ``datasource_airbyte_mapping`` table which links local
datasource IDs to their Airbyte source/connection/destination IDs.
"""

from __future__ import annotations

from typing import Any

from core.db import AirbyteMappingRepository
from core.logger import get_logger

logger = get_logger(__name__)


def _repo() -> AirbyteMappingRepository:
    return AirbyteMappingRepository()


class AirbyteMappingDB:
    """Encapsulates all datasource_airbyte_mapping DB operations."""

    @staticmethod
    async def ensure_table() -> None:
        """No-op — table creation is managed by Alembic migrations."""
        logger.info("datasource_airbyte_mapping table managed by Alembic – skipping ensure_table")

    # ---- CRUD ------------------------------------------------------------

    @staticmethod
    async def create(
        datasource_id: str,
        airbyte_source_id: str,
        airbyte_connection_id: str,
        airbyte_destination_id: str,
        update_graph_rag: bool = False,
    ) -> dict[str, Any]:
        """Insert a new mapping row and return it."""
        return await _repo().create(
            datasource_id=datasource_id,
            airbyte_source_id=airbyte_source_id,
            airbyte_connection_id=airbyte_connection_id,
            airbyte_destination_id=airbyte_destination_id,
            update_graph_rag=update_graph_rag,
        )

    @staticmethod
    async def get(datasource_id: str) -> dict[str, Any] | None:
        """Return the mapping for a datasource."""
        return await _repo().get(datasource_id)

    @staticmethod
    async def list_all() -> list[dict[str, Any]]:
        """Return all mappings."""
        return await _repo().list_all()

    @staticmethod
    async def update(datasource_id: str, **fields: Any) -> dict[str, Any] | None:
        """Update fields on a mapping row."""
        return await _repo().update(datasource_id, **fields)

    @staticmethod
    async def delete(datasource_id: str) -> bool:
        """Delete a mapping. Returns True if a row was removed."""
        return await _repo().delete(datasource_id)
