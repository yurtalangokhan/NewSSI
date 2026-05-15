import uuid
from datetime import datetime

from sqlalchemy import delete, func, or_, select

from src.core.database.models import UserModel

from .base_repository import BaseRepository


class UserRepository(BaseRepository):
    async def create(self, **kwargs) -> UserModel:
        async with self._session() as session:
            user = UserModel(**kwargs)
            session.add(user)
            await session.flush()
            await session.refresh(user)
            return user

    async def get_by_id(self, user_id: uuid.UUID) -> UserModel | None:
        async with self._session() as session:
            result = await session.execute(select(UserModel).where(UserModel.id == user_id))
            return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> UserModel | None:
        async with self._session() as session:
            result = await session.execute(select(UserModel).where(func.lower(UserModel.email) == func.lower(email)))
            return result.scalar_one_or_none()

    async def get_by_keycloak_id(self, keycloak_id: str) -> UserModel | None:
        async with self._session() as session:
            result = await session.execute(select(UserModel).where(UserModel.keycloak_id == keycloak_id))
            return result.scalar_one_or_none()

    async def get_by_username(self, username: str) -> UserModel | None:
        async with self._session() as session:
            result = await session.execute(select(UserModel).where(UserModel.username == username))
            return result.scalar_one_or_none()

    async def update(self, user_id: uuid.UUID, **kwargs) -> UserModel | None:
        async with self._session() as session:
            result = await session.execute(select(UserModel).where(UserModel.id == user_id))
            user = result.scalar_one_or_none()
            if not user:
                return None
            for key, value in kwargs.items():
                if value is not None and hasattr(user, key):
                    setattr(user, key, value)
            user.updated_at = datetime.utcnow()
            await session.flush()
            await session.refresh(user)
            return user

    async def delete(self, user_id: uuid.UUID) -> bool:
        async with self._session() as session:
            result = await session.execute(delete(UserModel).where(UserModel.id == user_id))
            return result.rowcount > 0

    async def list_paginated(
        self,
        skip: int = 0,
        limit: int = 20,
        query: str | None = None,
        role: str | None = None,
        is_active: bool | None = None,
        invited: bool | None = None,
    ) -> tuple[list[UserModel], int]:
        async with self._session() as session:
            stmt = select(UserModel)
            count_stmt = select(func.count(UserModel.id))

            if query:
                search = f"%{query.lower()}%"
                stmt = stmt.where(or_(
                    func.lower(UserModel.email).like(search),
                    func.lower(UserModel.first_name).like(search),
                    func.lower(UserModel.last_name).like(search),
                    func.lower(UserModel.username).like(search),
                ))
                count_stmt = count_stmt.where(or_(
                    func.lower(UserModel.email).like(search),
                    func.lower(UserModel.first_name).like(search),
                    func.lower(UserModel.last_name).like(search),
                    func.lower(UserModel.username).like(search),
                ))

            if role:
                stmt = stmt.where(UserModel.role == role)
                count_stmt = count_stmt.where(UserModel.role == role)

            if is_active is not None:
                stmt = stmt.where(UserModel.is_active == is_active)
                count_stmt = count_stmt.where(UserModel.is_active == is_active)

            if invited is not None:
                stmt = stmt.where(UserModel.invited == invited)
                count_stmt = count_stmt.where(UserModel.invited == invited)

            count_result = await session.execute(count_stmt)
            total = count_result.scalar_one()

            stmt = stmt.order_by(UserModel.created_at.desc()).offset(skip).limit(limit)
            result = await session.execute(stmt)
            return list(result.scalars().all()), total

    async def get_all(self) -> list[UserModel]:
        async with self._session() as session:
            result = await session.execute(select(UserModel).order_by(UserModel.created_at.desc()))
            return list(result.scalars().all())

    async def exists_by_email(self, email: str) -> bool:
        async with self._session() as session:
            result = await session.execute(
                select(func.count(UserModel.id)).where(func.lower(UserModel.email) == func.lower(email))
            )
            return result.scalar_one() > 0

    async def exists_by_keycloak_id(self, keycloak_id: str) -> bool:
        async with self._session() as session:
            result = await session.execute(
                select(func.count(UserModel.id)).where(UserModel.keycloak_id == keycloak_id)
            )
            return result.scalar_one() > 0

    async def upsert_by_keycloak_id(self, keycloak_id: str, **kwargs) -> UserModel:
        async with self._session() as session:
            result = await session.execute(select(UserModel).where(UserModel.keycloak_id == keycloak_id))
            user = result.scalar_one_or_none()
            if user:
                for key, value in kwargs.items():
                    if value is not None and hasattr(user, key):
                        setattr(user, key, value)
                user.updated_at = datetime.utcnow()
            else:
                kwargs["keycloak_id"] = keycloak_id
                user = UserModel(**kwargs)
                session.add(user)
            await session.flush()
            await session.refresh(user)
            return user
