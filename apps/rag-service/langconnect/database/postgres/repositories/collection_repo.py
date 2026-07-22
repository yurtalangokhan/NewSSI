"""Collection repository — typed CRUD for ``langchain_pg_collection``."""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from sqlalchemy import delete, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from langconnect import config
from langconnect.database.postgres.models import PgCollection
from langconnect.database.postgres.repositories.base import BaseRepository
from langconnect.models.collection import CollectionDetails

logger = logging.getLogger(__name__)


class CollectionRepository(BaseRepository):
    """CRUD operations on the ``langchain_pg_collection`` table."""

    def __init__(self, user_id: str) -> None:
        self.user_id = user_id

    # ---- helpers --------------------------------------------------------

    @property
    def _is_internal(self) -> bool:
        return self.user_id == "internal-service"

    @staticmethod
    def _parse_metadata(raw: Any) -> dict[str, Any]:
        """Normalise cmetadata from the DB into a plain ``dict``."""
        if raw is None:
            return {}
        if isinstance(raw, str):
            try:
                return json.loads(raw) or {}
            except (json.JSONDecodeError, TypeError):
                return {}
        if isinstance(raw, dict):
            return raw.copy()
        try:
            return dict(raw) if raw else {}
        except (TypeError, ValueError):
            return {}

    @staticmethod
    def _to_details(
        row: PgCollection, *, include_table_id: bool = False
    ) -> CollectionDetails:
        """Convert an ORM row to the ``CollectionDetails`` TypedDict."""
        metadata = CollectionRepository._parse_metadata(row.cmetadata)
        name = metadata.pop("name", "Unnamed")
        result: CollectionDetails = {
            "uuid": str(row.uuid),
            "name": name,
            "metadata": metadata,
        }
        if include_table_id:
            result["table_id"] = row.name
        return result

    # ---- read -----------------------------------------------------------

    async def list_collections(self) -> list[CollectionDetails]:
        """List collections owned by the user (or all, for internal)."""
        async with self._session() as session:
            stmt = select(PgCollection)

            if not self._is_internal:
                # JSON operator ->> returns text. Include internal/legacy rows so
                # collections created by ingestion jobs remain visible in the UI.
                stmt = stmt.where(
                    or_(
                        PgCollection.cmetadata["owner_id"].as_string() == self.user_id,
                        PgCollection.cmetadata["owner_id"].as_string()
                        == "internal-service",
                        PgCollection.cmetadata["owner_id"].as_string().is_(None),
                    )
                )

            stmt = stmt.order_by(PgCollection.cmetadata["name"].as_string())
            result = await session.execute(stmt)
            rows = result.scalars().all()

        return [self._to_details(r) for r in rows]

    async def get_collection(self, collection_id: str) -> CollectionDetails | None:
        """Fetch a single collection by UUID, enforcing ownership."""
        async with self._session() as session:
            stmt = select(PgCollection).where(PgCollection.uuid == collection_id)
            if not self._is_internal:
                stmt = stmt.where(
                    or_(
                        PgCollection.cmetadata["owner_id"].as_string() == self.user_id,
                        PgCollection.cmetadata["owner_id"].as_string()
                        == "internal-service",
                        PgCollection.cmetadata["owner_id"].as_string().is_(None),
                    )
                )

            result = await session.execute(stmt)
            row = result.scalar_one_or_none()

        if row is None:
            return None
        return self._to_details(row, include_table_id=True)

    # ---- write ----------------------------------------------------------

    async def create_collection(
        self,
        collection_name: str,
        metadata: dict[str, Any] | None = None,
    ) -> CollectionDetails | None:
        """Create a new collection row.

        Delegates table/index creation to ``get_vectorstore()`` and
        returns the resulting row as typed output.
        """
        # Build metadata payload
        meta = (metadata or {}).copy()
        meta["owner_id"] = self.user_id
        meta["name"] = collection_name

        table_id = str(uuid.uuid4())

        if config.VECTOR_DB_PROVIDER.lower() == "pgvector":
            # PGVector path: calling get_vectorstore bootstraps the PG tables and
            # inserts a row into langchain_pg_collection as a side effect.
            from langconnect.database.connection import get_vectorstore

            get_vectorstore(table_id, collection_metadata=meta)
        else:
            # Milvus path: Milvus collection is created lazily on first upsert.
            # We only need to insert the metadata row into langchain_pg_collection.
            async with self._session() as session:
                stmt = pg_insert(PgCollection).values(
                    uuid=uuid.UUID(table_id),
                    name=table_id,
                    cmetadata=meta,
                )
                await session.execute(stmt)
                await session.commit()

        async with self._session() as session:
            stmt = (
                select(PgCollection)
                .where(PgCollection.name == table_id)
                .where(PgCollection.cmetadata["owner_id"].as_string() == self.user_id)
            )
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()

        if row is None:
            return None
        return self._to_details(row)

    async def update_collection(
        self,
        collection_id: str,
        *,
        name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> CollectionDetails | None:
        """Update collection metadata / friendly name.

        Four cases handled:
        1. metadata only → merge, keep old name
        2. metadata + name → merge including new name
        3. name only → patch name key inside cmetadata
        4. neither → caller should not invoke this
        """
        if metadata is not None:
            merged = metadata.copy()
            merged["owner_id"] = self.user_id

            if name is not None:
                merged["name"] = name
            else:
                existing = await self.get_collection(collection_id)
                if existing is None:
                    return None
                merged["name"] = existing["name"]

            async with self._session() as session:
                stmt = (
                    update(PgCollection)
                    .where(PgCollection.uuid == collection_id)
                    .where(
                        PgCollection.cmetadata["owner_id"].as_string() == self.user_id
                    )
                    .values(cmetadata=merged)
                    .returning(PgCollection)
                )
                result = await session.execute(stmt)
                row = result.scalar_one_or_none()
        else:
            # name-only update: patch the JSON key
            async with self._session() as session:
                # Fetch current metadata, patch, write back
                sel = (
                    select(PgCollection)
                    .where(PgCollection.uuid == collection_id)
                    .where(
                        PgCollection.cmetadata["owner_id"].as_string() == self.user_id
                    )
                )
                result = await session.execute(sel)
                row = result.scalar_one_or_none()
                if row is None:
                    return None

                current_meta = self._parse_metadata(row.cmetadata)
                current_meta["name"] = name
                row.cmetadata = current_meta
                await session.flush()

        if row is None:
            return None
        return self._to_details(row)

    async def delete_collection(self, collection_id: str) -> int:
        """Delete a collection by UUID.  Returns rows deleted (0 or 1)."""
        async with self._session() as session:
            stmt = (
                delete(PgCollection)
                .where(PgCollection.uuid == collection_id)
                .where(PgCollection.cmetadata["owner_id"].as_string() == self.user_id)
            )
            result = await session.execute(stmt)
            return result.rowcount
