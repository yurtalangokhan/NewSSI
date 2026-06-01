"""Repository for user_memory table — pure CRUD, no business logic."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, func, select, text, update

from core.db.models.user_memory import UserMemoryModel
from core.db.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class UserMemoryRepository(BaseRepository):
    """CRUD operations on the ``user_memory`` table."""

    @staticmethod
    def _to_dict(row: UserMemoryModel) -> dict[str, Any]:
        return {
            "id": str(row.id),
            "user_id": row.user_id,
            "content": row.content,
            "source": row.source,
            "time_created": row.time_created.isoformat() if row.time_created else None,
            "time_updated": row.time_updated.isoformat() if row.time_updated else None,
        }

    async def list_by_user(
        self,
        user_id: str,
        limit: int | None = None,
        source: str | None = None,
    ) -> list[UserMemoryModel]:
        """Return memories for a user ordered by recency descending."""
        async with self._session() as session:
            stmt = (
                select(UserMemoryModel)
                .where(UserMemoryModel.user_id == user_id)
                .order_by(UserMemoryModel.time_created.desc())
            )
            if source:
                stmt = stmt.where(UserMemoryModel.source == source)
            if limit is not None:
                stmt = stmt.limit(limit)
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def get(self, memory_id: str, user_id: str) -> UserMemoryModel | None:
        """Return a single memory by id, scoped to user."""
        async with self._session() as session:
            stmt = select(UserMemoryModel).where(
                UserMemoryModel.id == memory_id,
                UserMemoryModel.user_id == user_id,
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def create(
        self, user_id: str, content: str, source: str = "manual"
    ) -> UserMemoryModel:
        """Insert a single memory row. Raises IntegrityError on duplicate."""
        async with self._session() as session:
            row = UserMemoryModel(
                id=uuid.uuid4(),
                user_id=user_id,
                content=content,
                source=source,
                time_created=datetime.now(UTC),
                time_updated=datetime.now(UTC),
            )
            session.add(row)
            await session.flush()
            await session.refresh(row)
            return row

    async def bulk_create(
        self, user_id: str, items: list[tuple[str, str]]
    ) -> list[UserMemoryModel]:
        """
        Insert multiple (content, source) pairs using ON CONFLICT DO NOTHING.
        Returns rows that were actually inserted.
        """
        if not items:
            return []
        async with self._session() as session:
            created: list[UserMemoryModel] = []
            for content, source in items:
                stmt = (
                    text(
                        "INSERT INTO user_memory (id, user_id, content, source, time_created, time_updated) "
                        "VALUES (:id, :user_id, :content, :source, now(), now()) "
                        "ON CONFLICT (user_id, lower(content)) DO NOTHING "
                        "RETURNING id, user_id, content, source, time_created, time_updated"
                    )
                )
                result = await session.execute(
                    stmt,
                    {
                        "id": str(uuid.uuid4()),
                        "user_id": user_id,
                        "content": content,
                        "source": source,
                    },
                )
                row_data = result.fetchone()
                if row_data:
                    # Re-fetch as ORM object
                    fetch = await session.execute(
                        select(UserMemoryModel).where(
                            UserMemoryModel.id == row_data[0]
                        )
                    )
                    orm_row = fetch.scalar_one_or_none()
                    if orm_row:
                        created.append(orm_row)
            return created

    async def update(
        self, memory_id: str, user_id: str, content: str
    ) -> UserMemoryModel | None:
        """Update content of a memory. Returns None if not found."""
        async with self._session() as session:
            stmt = (
                update(UserMemoryModel)
                .where(
                    UserMemoryModel.id == memory_id,
                    UserMemoryModel.user_id == user_id,
                )
                .values(content=content, time_updated=datetime.now(UTC))
                .returning(UserMemoryModel)
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def delete(self, memory_id: str, user_id: str) -> bool:
        """Delete a single memory. Returns True if deleted."""
        async with self._session() as session:
            stmt = delete(UserMemoryModel).where(
                UserMemoryModel.id == memory_id,
                UserMemoryModel.user_id == user_id,
            )
            result = await session.execute(stmt)
            return result.rowcount > 0

    async def delete_all(self, user_id: str) -> int:
        """Delete all memories for a user. Returns count deleted."""
        async with self._session() as session:
            stmt = delete(UserMemoryModel).where(
                UserMemoryModel.user_id == user_id,
            )
            result = await session.execute(stmt)
            return result.rowcount

    async def count(self, user_id: str) -> int:
        """Return the number of memories for a user."""
        async with self._session() as session:
            stmt = select(func.count()).where(UserMemoryModel.user_id == user_id)
            result = await session.execute(stmt)
            return result.scalar_one()
