import uuid
from datetime import datetime

from sqlalchemy import delete, select

from src.core.database.models import SessionModel

from .base_repository import BaseRepository


class SessionRepository(BaseRepository):
    async def create(self, **kwargs) -> SessionModel:
        async with self._session() as session:
            session_obj = SessionModel(**kwargs)
            session.add(session_obj)
            await session.flush()
            await session.refresh(session_obj)
            return session_obj

    async def get_by_token_hash(self, token_hash: str) -> SessionModel | None:
        async with self._session() as session:
            result = await session.execute(
                select(SessionModel).where(SessionModel.token_hash == token_hash)
            )
            return result.scalar_one_or_none()

    async def get_by_refresh_token_hash(self, refresh_token_hash: str) -> SessionModel | None:
        async with self._session() as session:
            result = await session.execute(
                select(SessionModel).where(SessionModel.refresh_token_hash == refresh_token_hash)
            )
            return result.scalar_one_or_none()

    async def list_by_user(self, user_id: uuid.UUID) -> list[SessionModel]:
        async with self._session() as session:
            result = await session.execute(
                select(SessionModel)
                .where(SessionModel.user_id == user_id)
                .order_by(SessionModel.created_at.desc())
            )
            return list(result.scalars().all())

    async def delete_by_token_hash(self, token_hash: str) -> bool:
        async with self._session() as session:
            result = await session.execute(
                delete(SessionModel).where(SessionModel.token_hash == token_hash)
            )
            return result.rowcount > 0

    async def delete_by_refresh_token_hash(self, refresh_token_hash: str) -> bool:
        async with self._session() as session:
            result = await session.execute(
                delete(SessionModel).where(SessionModel.refresh_token_hash == refresh_token_hash)
            )
            return result.rowcount > 0

    async def delete_by_user(self, user_id: uuid.UUID) -> int:
        async with self._session() as session:
            result = await session.execute(
                delete(SessionModel).where(SessionModel.user_id == user_id)
            )
            return result.rowcount

    async def delete_expired(self) -> int:
        async with self._session() as session:
            result = await session.execute(
                delete(SessionModel).where(SessionModel.expires_at < datetime.utcnow())
            )
            return result.rowcount
