import uuid
from datetime import datetime

from sqlalchemy import delete, select, update

from src.core.database.models import ApiKeyModel

from .base_repository import BaseRepository


class ApiKeyRepository(BaseRepository):
    async def create(self, **kwargs) -> ApiKeyModel:
        async with self._session() as session:
            key = ApiKeyModel(**kwargs)
            session.add(key)
            await session.flush()
            await session.refresh(key)
            return key

    async def get_by_id(self, key_id: uuid.UUID) -> ApiKeyModel | None:
        async with self._session() as session:
            result = await session.execute(select(ApiKeyModel).where(ApiKeyModel.id == key_id))
            return result.scalar_one_or_none()

    async def get_by_hash(self, key_hash: str) -> ApiKeyModel | None:
        async with self._session() as session:
            result = await session.execute(select(ApiKeyModel).where(ApiKeyModel.key_hash == key_hash))
            return result.scalar_one_or_none()

    async def find_by_prefix_and_active(self, key_prefix: str) -> list[ApiKeyModel]:
        async with self._session() as session:
            result = await session.execute(
                select(ApiKeyModel).where(ApiKeyModel.key_prefix == key_prefix, ApiKeyModel.is_active)
            )
            return list(result.scalars().all())

    async def list_by_user(self, user_id: uuid.UUID) -> list[ApiKeyModel]:
        async with self._session() as session:
            result = await session.execute(
                select(ApiKeyModel).where(ApiKeyModel.user_id == user_id).order_by(ApiKeyModel.created_at.desc())
            )
            return list(result.scalars().all())

    async def update(self, key_id: uuid.UUID, **updates) -> ApiKeyModel | None:
        async with self._session() as session:
            result = await session.execute(select(ApiKeyModel).where(ApiKeyModel.id == key_id))
            key = result.scalar_one_or_none()
            if not key:
                return None
            for k, v in updates.items():
                if v is not None and hasattr(key, k):
                    setattr(key, k, v)
            await session.flush()
            await session.refresh(key)
            return key

    async def revoke(self, key_id: uuid.UUID) -> bool:
        async with self._session() as session:
            result = await session.execute(
                update(ApiKeyModel).where(ApiKeyModel.id == key_id).values(is_active=False)
            )
            return result.rowcount > 0

    async def update_last_used(self, key_id: uuid.UUID) -> None:
        async with self._session() as session:
            await session.execute(
                update(ApiKeyModel).where(ApiKeyModel.id == key_id).values(last_used_at=datetime.utcnow())
            )

    async def delete(self, key_id: uuid.UUID) -> bool:
        async with self._session() as session:
            result = await session.execute(delete(ApiKeyModel).where(ApiKeyModel.id == key_id))
            return result.rowcount > 0

    async def delete_by_user(self, user_id: uuid.UUID) -> int:
        async with self._session() as session:
            result = await session.execute(delete(ApiKeyModel).where(ApiKeyModel.user_id == user_id))
            return result.rowcount
