"""
Datasource–Airbyte Mapping Database Manager.

Manages the ``datasource_airbyte_mapping`` table which links local
datasource IDs to their Airbyte source/connection/destination IDs.

Replaces the old ``sync_schedules`` table.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from psycopg.rows import dict_row

from service.store import get_store

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# SQL – table creation
# ------------------------------------------------------------------

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS datasource_airbyte_mapping (
    datasource_id           UUID PRIMARY KEY,
    airbyte_source_id       VARCHAR NOT NULL,
    airbyte_connection_id   VARCHAR NOT NULL,
    airbyte_destination_id  VARCHAR NOT NULL,
    update_graph_rag        BOOLEAN NOT NULL DEFAULT FALSE,
    last_processed_job_id   BIGINT NOT NULL DEFAULT 0,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT fk_datasource_mapping
        FOREIGN KEY (datasource_id)
        REFERENCES langchain_pg_collection(uuid)
        ON DELETE CASCADE
);
"""


# ------------------------------------------------------------------
# Manager class
# ------------------------------------------------------------------


class AirbyteMappingDB:
    """Encapsulates all datasource_airbyte_mapping DB operations."""

    @staticmethod
    async def ensure_table() -> None:
        """Create the mapping table if it does not exist."""
        store = get_store()
        if not store or not store.pool:
            logger.warning("Store not ready – skipping mapping table creation")
            return
        async with store.pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(CREATE_TABLE_SQL)
        logger.info("datasource_airbyte_mapping table ensured")

    @staticmethod
    def _row_to_dict(row: dict[str, Any]) -> dict[str, Any]:
        """Normalise a DB row to a JSON-friendly dict."""
        out: dict[str, Any] = {}
        for k, v in row.items():
            if isinstance(v, datetime):
                out[k] = v.isoformat()
            else:
                out[k] = v
        if "datasource_id" in out and out["datasource_id"] is not None:
            out["datasource_id"] = str(out["datasource_id"])
        return out

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
        store = get_store()
        now = datetime.now(timezone.utc)

        async with store.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    INSERT INTO datasource_airbyte_mapping
                        (datasource_id, airbyte_source_id, airbyte_connection_id,
                         airbyte_destination_id, update_graph_rag, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (datasource_id) DO UPDATE SET
                        airbyte_source_id = EXCLUDED.airbyte_source_id,
                        airbyte_connection_id = EXCLUDED.airbyte_connection_id,
                        airbyte_destination_id = EXCLUDED.airbyte_destination_id,
                        update_graph_rag = EXCLUDED.update_graph_rag,
                        updated_at = EXCLUDED.updated_at
                    RETURNING *
                    """,
                    (
                        datasource_id,
                        airbyte_source_id,
                        airbyte_connection_id,
                        airbyte_destination_id,
                        update_graph_rag,
                        now,
                        now,
                    ),
                )
                row = await cur.fetchone()
                return AirbyteMappingDB._row_to_dict(row)

    @staticmethod
    async def get(datasource_id: str) -> Optional[dict[str, Any]]:
        """Return the mapping for a datasource."""
        store = get_store()
        if not store or not store.pool:
            return None
        async with store.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    "SELECT * FROM datasource_airbyte_mapping WHERE datasource_id = %s",
                    (datasource_id,),
                )
                row = await cur.fetchone()
                return AirbyteMappingDB._row_to_dict(row) if row else None

    @staticmethod
    async def list_all() -> list[dict[str, Any]]:
        """Return all mappings."""
        store = get_store()
        if not store or not store.pool:
            return []
        async with store.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    "SELECT * FROM datasource_airbyte_mapping ORDER BY created_at"
                )
                rows = await cur.fetchall()
                return [AirbyteMappingDB._row_to_dict(r) for r in rows]

    @staticmethod
    async def update(datasource_id: str, **fields: Any) -> Optional[dict[str, Any]]:
        """Update fields on a mapping row."""
        store = get_store()
        allowed = {
            "airbyte_source_id",
            "airbyte_connection_id",
            "airbyte_destination_id",
            "update_graph_rag",
            "last_processed_job_id",
        }
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return await AirbyteMappingDB.get(datasource_id)

        updates["updated_at"] = datetime.now(timezone.utc)
        set_clause = ", ".join(f"{k} = %s" for k in updates)
        values = list(updates.values()) + [datasource_id]

        async with store.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    f"UPDATE datasource_airbyte_mapping SET {set_clause} WHERE datasource_id = %s RETURNING *",
                    values,
                )
                row = await cur.fetchone()
                return AirbyteMappingDB._row_to_dict(row) if row else None

    @staticmethod
    async def delete(datasource_id: str) -> bool:
        """Delete a mapping. Returns True if a row was removed."""
        store = get_store()
        async with store.pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "DELETE FROM datasource_airbyte_mapping WHERE datasource_id = %s",
                    (datasource_id,),
                )
                return cur.rowcount > 0
