import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, func, select, text, update

from src.core.database.models import UserMemoryModel

from .base_repository import BaseRepository


class UserMemoryRepository(BaseRepository):
    async def list_by_user(
        self,
        user_id: uuid.UUID,
        limit: int | None = None,
        source: str | None = None,
    ) -> list[UserMemoryModel]:
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

    async def get(self, memory_id: uuid.UUID, user_id: uuid.UUID) -> UserMemoryModel | None:
        async with self._session() as session:
            stmt = select(UserMemoryModel).where(
                UserMemoryModel.id == memory_id,
                UserMemoryModel.user_id == user_id,
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def create(
        self, user_id: uuid.UUID, content: str, source: str = "manual"
    ) -> UserMemoryModel:
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
        self, user_id: uuid.UUID, items: list[tuple[str, str]]
    ) -> list[UserMemoryModel]:
        if not items:
            return []
        async with self._session() as session:
            created: list[UserMemoryModel] = []
            for content, source in items:
                stmt = text(
                    "INSERT INTO user_memory (id, user_id, content, source, time_created, time_updated) "
                    "VALUES (:id, :user_id, :content, :source, now(), now()) "
                    "ON CONFLICT (user_id, lower(content)) DO NOTHING "
                    "RETURNING id, user_id, content, source, time_created, time_updated"
                )
                result = await session.execute(
                    stmt,
                    {
                        "id": str(uuid.uuid4()),
                        "user_id": str(user_id),
                        "content": content,
                        "source": source,
                    },
                )
                row_data = result.fetchone()
                if row_data:
                    fetch = await session.execute(
                        select(UserMemoryModel).where(UserMemoryModel.id == row_data[0])
                    )
                    orm_row = fetch.scalar_one_or_none()
                    if orm_row:
                        created.append(orm_row)
            return created

    async def update(
        self, memory_id: uuid.UUID, user_id: uuid.UUID, content: str
    ) -> UserMemoryModel | None:
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

    async def delete(self, memory_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        async with self._session() as session:
            stmt = delete(UserMemoryModel).where(
                UserMemoryModel.id == memory_id,
                UserMemoryModel.user_id == user_id,
            )
            result = await session.execute(stmt)
            return result.rowcount > 0

    async def delete_all(self, user_id: uuid.UUID) -> int:
        async with self._session() as session:
            stmt = delete(UserMemoryModel).where(
                UserMemoryModel.user_id == user_id,
            )
            result = await session.execute(stmt)
            return result.rowcount

    async def count(self, user_id: uuid.UUID) -> int:
        async with self._session() as session:
            stmt = select(func.count()).where(UserMemoryModel.user_id == user_id)
            result = await session.execute(stmt)
            return result.scalar_one()

    def _to_dict(self, row: UserMemoryModel) -> dict[str, Any]:
        return {
            "id": str(row.id),
            "user_id": str(row.user_id),
            "content": row.content,
            "source": row.source,
            "time_created": row.time_created.isoformat() if row.time_created else None,
            "time_updated": row.time_updated.isoformat() if row.time_updated else None,
        }
