from datetime import UTC, datetime
from typing import Any
import uuid

from error_contract import ConflictError
from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError

from src.core.database.models import UserMemoryModel

from .base_repository import BaseRepository


class UserMemoryRepository(BaseRepository):
    async def list_by_user(
        self,
        user_id: uuid.UUID,
        limit: int | None = None,
        source: str | None = None,
        offset: int = 0,
    ) -> list[UserMemoryModel]:
        async with self._session() as session:
            stmt = (
                select(UserMemoryModel)
                .where(UserMemoryModel.user_id == user_id)
                .order_by(UserMemoryModel.time_created.desc())
            )
            if source:
                stmt = stmt.where(UserMemoryModel.source == source)
            if offset:
                stmt = stmt.offset(offset)
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

    async def create(self, user_id: uuid.UUID, content: str, source: str = "manual") -> UserMemoryModel:
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
            try:
                await session.flush()
            except IntegrityError as exc:
                raise ConflictError(
                    code="memory.already_exists",
                    message="Memory already exists.",
                    message_key="errors.user_service.memory.already_exists",
                ) from exc
            await session.refresh(row)
            return row

    async def bulk_create(self, user_id: uuid.UUID, items: list[tuple[str, str, str | None]]) -> list[UserMemoryModel]:
        """Insert facts as ``(content, source, language)`` triples.

        ``language`` is the BCP-47 tag the extractor's model declared, or
        ``None`` when it declared none.
        """
        if not items:
            return []
        async with self._session() as session:
            now = datetime.now(UTC)
            values = [
                {
                    "id": uuid.uuid4(),
                    "user_id": user_id,
                    "content": content,
                    "source": source,
                    "language": language,
                    "time_created": now,
                    "time_updated": now,
                }
                for content, source, language in items
            ]
            stmt = (
                pg_insert(UserMemoryModel)
                .values(values)
                .on_conflict_do_nothing(index_elements=[UserMemoryModel.user_id, func.lower(UserMemoryModel.content)])
                .returning(UserMemoryModel)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def update(self, memory_id: uuid.UUID, user_id: uuid.UUID, content: str) -> UserMemoryModel | None:
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

    async def delete_oldest_excess(self, user_id: uuid.UUID, keep: int) -> int:
        """Delete every fact for this user beyond the `keep` most recent.

        Without this, only recall was bounded (list_for_recall's LIMIT);
        storage itself grew forever, and nothing ever removed old or
        stale facts that had already scrolled out of the recall window.
        """
        async with self._session() as session:
            keep_ids = (
                select(UserMemoryModel.id)
                .where(UserMemoryModel.user_id == user_id)
                .order_by(UserMemoryModel.time_created.desc(), UserMemoryModel.id.desc())
                .limit(keep)
            )
            stmt = delete(UserMemoryModel).where(
                UserMemoryModel.user_id == user_id,
                UserMemoryModel.id.notin_(keep_ids),
            )
            result = await session.execute(stmt)
            return result.rowcount

    def _to_dict(self, row: UserMemoryModel) -> dict[str, Any]:
        return {
            "id": str(row.id),
            "user_id": str(row.user_id),
            "content": row.content,
            "source": row.source,
            "language": row.language,
            "time_created": row.time_created.isoformat() if row.time_created else None,
            "time_updated": row.time_updated.isoformat() if row.time_updated else None,
        }
